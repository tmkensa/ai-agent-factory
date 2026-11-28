"""Executive orchestration, durable precharges and bounded output recovery."""
import time
from datetime import datetime, timezone
from factory.engine import require, FactoryError
from .agents import team, validate_task
from .workflow import graph, layers, parallel
from .governance import Budget, validate, gate, digest, enforce_text, canonical, export_approved
from .contracts import error_code, RETRYABLE
from .state import validate_state, TERMINAL, contract

def now():
    return datetime.now(timezone.utc).isoformat()

class Orchestrator:
    def __init__(self,store,backend,output_retries=0):
        require(type(output_retries) is int and 0<=output_retries<=2,"Output retries must be 0–2")
        self.store=store; self.backend=backend; self.output_retries=output_retries
    def create(self,raw,call_limit=24,revisions=2,specialist_definitions=None):
        from factory.platform.operations import specialists
        task=validate_task(raw); enforce_text(canonical(task))
        require(type(revisions) is int and 0<=revisions<=2,"Revisions must be 0–2")
        Budget(call_limit)
        definitions=[] if specialist_definitions is None else specialist_definitions
        roles,_=specialists(definitions)
        require(not roles or self.backend.name!="demo","Custom specialists require a real model route")
        require(len(task["sources"])+len(roles)<=8 and sum(len(s["text"]) for s in task["sources"])+len(roles)*3050<=32000,"Insufficient source budget for specialists")
        require(not roles or call_limit>=len(roles)+6,"Insufficient call budget for specialists")
        require(not ({"specialist:"+n for n in roles} & {s["id"] for s in task["sources"]}),"Specialist source ID collision")
        rid=self.store.new()
        s={"version":3,"id":rid,"task":task,"original_task":task,"backend":self.backend.name,"identity":self.backend.identity,"graph":{n:list(d) for n,d in graph(team(task)).items()},"limit":call_limit,"revisions":revisions,"output_retries":self.output_retries,"round":0,"calls":0,"outputs":{},"events":[],"status":"READY","feedback":[],"specialists":definitions,"specialist_outputs":{}}
        s["contract_digest"]=digest(contract(s))
        self.store.save(s)
        return rid

    def execute(self,rid):
        from factory.platform.operations import specialists
        with self.store.lock(rid):
            s=self.store.load(rid)
            validate_state(s,rid)
            require(s["identity"]==self.backend.identity and s["backend"]==self.backend.name,"Checkpoint/model configuration mismatch")
            if s["status"] in TERMINAL: return self.report(s)
            for e in s["events"]:
                if e["status"]=="reserved": e.update(status="interrupted",error_code="INTERRUPTED")
            self.store.save(s)
            budget=Budget(s["limit"],s["calls"])
            roles,spec_layers=specialists(s["specialists"])
            def layer_run(names,kind,outputs,deps,task):
                pending=[n for n in names if n not in outputs]
                while pending:
                    try: budget.reserve(len(pending))
                    except FactoryError:
                        s.update(status="BLOCKED",error="Call budget exhausted")
                        self.store.save(s); return False
                    records={}
                    for n in pending:
                        e={"attempt":len(s["events"])+1,"role":n,"kind":kind,"round":s["round"],"status":"reserved","reserved_at":now()}
                        s["events"].append(e); records[n]=e
                    s.update(calls=budget.used,status="RUNNING",error=None)
                    self.store.save(s)
                    def invoke(n):
                        start=time.monotonic(); stamp=now(); metrics={}
                        try:
                            payload={"task":task,"dependencies":{d:outputs[d] for d in deps[n]}}
                            previous=[e for e in s["events"] if e["role"]==n and e["kind"]==kind and e["round"]==s["round"] and e["status"]=="failed"]
                            if previous and previous[-1].get("error_code") in RETRYABLE:
                                payload["output_recovery"]={"error_code":previous[-1]["error_code"],"instruction":"Return a complete valid output; do not invent or omit required checks."}
                            if kind=="specialist":
                                payload["specialist"]={"name":n,"job":roles[n]["job"]}
                                value,metrics=self.backend.call("specialist",payload)
                                require(isinstance(value,dict) and set(value)=={"text"},"Invalid specialist output")
                                t=value["text"]; require(isinstance(t,str) and 0<len(t.strip())<=3000,"Specialist output limit")
                                output=enforce_text(t)
                            else:
                                if n=="executor": payload["repair_feedback"]=s["feedback"]
                                if n=="evaluator": payload["source_findings"]=outputs.get("researcher")
                                value,metrics=self.backend.call(n,payload)
                                output=validate(n,value,task)
                            return output,{"status":"ok",**metrics,"started_at":stamp,"ended_at":now(),"seconds":round(time.monotonic()-start,4)}
                        except Exception as exc:
                            return None,{"status":"failed","error":type(exc).__name__,"error_code":error_code(exc),**metrics,"started_at":stamp,"ended_at":now(),"seconds":round(time.monotonic()-start,4)}
                    result=parallel(pending,invoke)
                    retry=[]; hard_failed=False
                    for n,(output,event) in result.items():
                        records[n].update(event)
                        if output is not None: outputs[n]=output
                        else:
                            failures=sum(e["role"]==n and e["kind"]==kind and e["round"]==s["round"] and e["status"]=="failed" for e in s["events"])
                            if event["error_code"] in RETRYABLE and failures<=s["output_retries"]: retry.append(n)
                            else: hard_failed=True
                    if kind=="specialist" and len(outputs)==len(roles):
                        effective=dict(s["original_task"])
                        effective["sources"]=effective["sources"]+[{"id":"specialist:"+n,"text":"UNVERIFIED GENERATED ANALYSIS:\n"+outputs[n]} for n in sorted(outputs)]
                        s["task"]=validate_task(effective); s["graph"]={n:list(d) for n,d in graph(team(s["task"])).items()}
                    s["status"]="FAILED" if hard_failed or retry else "RUNNING"
                    s["error"]="Role attempt failed; inspect event error_code" if hard_failed or retry else None
                    self.store.save(s)
                    if hard_failed: return False
                    pending=retry
                return True
            for layer in spec_layers:
                if not layer_run(layer,"specialist",s["specialist_outputs"],{n:r["depends_on"] for n,r in roles.items()},s["original_task"]): return self.report(s)
            task=s["task"]; nodes=s["graph"]
            while True:
                for layer in layers(nodes):
                    if not layer_run(layer,"role",s["outputs"],nodes,task): return self.report(s)
                review=gate(s["outputs"]); s["gate"]=review
                if review["passed"]:
                    s["draft_digest"]=digest(s["outputs"]["executor"])
                    s["status"]="DEMO_COMPLETE" if self.backend.name=="demo" else "PENDING_APPROVAL"
                    self.store.save(s); return self.report(s)
                if s["round"]>=s["revisions"]:
                    s.update(status="BLOCKED",error="Mandatory review gate failed")
                    self.store.save(s); return self.report(s)
                s["round"]+=1; s["feedback"]=review["failures"]; s["gate"]=None
                for role in ("executor","security","tester","evaluator"): s["outputs"].pop(role,None)
                self.store.save(s)

    def approve(self,rid,expected_digest,output):
        with self.store.lock(rid):
            s=self.store.load(rid); validate_state(s,rid)
            path=export_approved(s,expected_digest,output)
            s.update(status="EXPORTED",export={"path":path,"digest":expected_digest})
            self.store.save(s); return self.report(s)

    @staticmethod
    def report(s):
        events=s["events"]; totals={}; known={}
        for key in ("input_tokens","output_tokens"):
            values=[e.get(key) for e in events]
            known[key]=sum(v for v in values if type(v) is int)
            totals[key]=known[key] if values and all(type(v) is int for v in values) else None
        extras=[e for e in events if e["kind"]=="specialist"]
        return {"id":s["id"],"status":s["status"],"graph":s["graph"],"calls":s["calls"],"limit":s["limit"],"round":s["round"],"gate":s.get("gate"),"draft_digest":s.get("draft_digest"),"error":s.get("error"),"metrics":totals,"known_usage":known,"events":events,"specialist_metrics":extras,"total_calls_this_invocation":s["calls"],"export":s.get("export"),"human_review_required":True,"evaluation":"fixture only" if s["backend"]=="demo" else "Model review; not proof of correctness or security"}
