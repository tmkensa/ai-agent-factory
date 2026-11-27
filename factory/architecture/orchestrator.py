"""Executive orchestrator with durable layers, bounded repair and approval."""
import time
from factory.engine import require
from .agents import team, validate_task
from .workflow import graph, layers, parallel
from .governance import Budget, validate, gate, digest, enforce_text, canonical, export_approved

class Orchestrator:
    def __init__(self,store,backend):
        self.store=store; self.backend=backend
    def create(self,raw,call_limit=24,revisions=2):
        task=validate_task(raw)
        enforce_text(canonical(task))
        require(type(revisions) is int and 0<=revisions<=2,"Revisions must be 0–2")
        Budget(call_limit)
        rid=self.store.new()
        nodes=graph(team(task))
        state={"version":2,"id":rid,"task":task,"backend":self.backend.name,"identity":self.backend.identity,"graph":nodes,"limit":call_limit,"revisions":revisions,"round":0,"calls":0,"outputs":{},"events":[],"status":"READY","feedback":[]}
        self.store.save(state)
        return rid
    def execute(self,rid):
        with self.store.lock(rid):
            state=self.store.load(rid)
            require(state["version"]==2 and state["id"]==rid and state["identity"]==self.backend.identity,"Checkpoint/model configuration mismatch")
            if state["status"] in {"PENDING_APPROVAL","DEMO_COMPLETE","BLOCKED","EXPORTED"}: return self.report(state)
            task=validate_task(state["task"]); enforce_text(canonical(task))
            nodes=graph(team(task))
            require(state["graph"]=={n:list(d) for n,d in nodes.items()},"Workflow changed")
            budget=Budget(state["limit"],state["calls"])
            while True:
                for layer in layers(nodes):
                    pending=[n for n in layer if n not in state["outputs"]]
                    if not pending: continue
                    try: budget.reserve(len(pending))
                    except Exception:
                        state.update(status="BLOCKED",error="Call budget exhausted")
                        self.store.save(state); return self.report(state)
                    # Reserve and save BEFORE calls, including when a process crashes.
                    state.update(calls=budget.used,status="RUNNING")
                    self.store.save(state)
                    dependencies={n:{d:state["outputs"][d] for d in nodes[n]} for n in pending}
                    def invoke(role):
                        start=time.monotonic()
                        try:
                            payload={"task":task,"dependencies":dependencies[role]}
                            if role=="executor": payload["repair_feedback"]=state["feedback"]
                            if role=="evaluator":
                                # Explicit evidence is supplied even when not a graph dependency.
                                payload["source_findings"]=state["outputs"].get("researcher")
                            value,metrics=self.backend.call(role,payload)
                            output=validate(role,value,task)
                            return output,{"role":role,"round":state["round"],"status":"ok","seconds":round(time.monotonic()-start,4),**metrics}
                        except Exception as e:
                            return None,{"role":role,"round":state["round"],"status":"failed","seconds":round(time.monotonic()-start,4),"error":type(e).__name__}
                    result=parallel(pending,invoke)
                    failed=False
                    for role,(output,event) in result.items():
                        state["events"].append(event)
                        if output is None: failed=True
                        else: state["outputs"][role]=output
                    state["status"]="FAILED" if failed else "RUNNING"
                    self.store.save(state)
                    if failed: return self.report(state)
                review=gate(state["outputs"]); state["gate"]=review
                if review["passed"]:
                    state["draft_digest"]=digest(state["outputs"]["executor"])
                    state["status"]="DEMO_COMPLETE" if self.backend.name=="demo" else "PENDING_APPROVAL"
                    self.store.save(state); return self.report(state)
                if state["round"]>=state["revisions"]:
                    state["status"]="BLOCKED"
                    state["error"]="Mandatory review gate failed"
                    self.store.save(state); return self.report(state)
                state["round"]+=1
                state["feedback"]=review["failures"]
                # Reuse planner/research; invalidate only the executor and its dependents.
                for role in ("executor","security","tester","evaluator"):
                    state["outputs"].pop(role,None)
                self.store.save(state)
    def approve(self,rid,expected_digest,output):
        with self.store.lock(rid):
            state=self.store.load(rid)
            path=export_approved(state,expected_digest,output)
            state.update(status="EXPORTED",export={"path":path,"digest":expected_digest})
            self.store.save(state)
            return self.report(state)
    @staticmethod
    def report(state):
        events=state["events"]
        totals={}
        for key in ("input_tokens","output_tokens"):
            values=[e.get(key) for e in events]
            totals[key]=sum(values) if values and all(type(v) is int for v in values) else None
        return {"id":state["id"],"status":state["status"],"graph":state["graph"],"calls":state["calls"],"round":state["round"],"gate":state.get("gate"),"draft_digest":state.get("draft_digest"),"error":state.get("error"),"metrics":totals,"events":events,"export":state.get("export"),"human_review_required":True,"evaluation":"fixture only" if state["backend"]=="demo" else "Model review; not proof of correctness or security"}
