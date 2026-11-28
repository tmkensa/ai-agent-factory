"""Opt-in v0.5 dynamic drafting runtime with an auditable attempt/artifact ledger."""
import time
from factory.engine import require, FactoryError
from .agents import validate_task
from .team import make_plan, validate_plan, GATES
from .artifacts import validate_artifact, output_map, review_record, make_payload, MAX_CONTEXT_BYTES
from .governance import Budget, digest, canonical, enforce_text, export_approved
from .contracts import error_code, RETRYABLE
from .orchestrator import now
from .workflow import parallel
from .state import TERMINAL

def contract(s):
    return {k:s[k] for k in ("task","plan","identity","backend","limit","revisions","output_retries")}

def check_routes(identity,plan):
    mapped=identity.get("roles",{})
    require(isinstance(mapped,dict) and all(isinstance(k,str) for k in mapped),"Invalid route mapping")
    allowed={"agent:"+n for n,r in plan["registry"].items() if r["kind"]=="specialist"}
    require(all(not k.startswith("agent:") or k in allowed for k in mapped),"Mapped agent not in team")

def validate_dynamic(s,rid):
    """Replay successful artifact versions and review boundaries, fail closed on corruption."""
    require(isinstance(s,dict) and s.get("version")==4 and s.get("id")==rid,"Invalid dynamic checkpoint")
    task=validate_task(s["task"]); require(task==s["task"] and s["original_task"]==task,"Dynamic task mismatch")
    plan=validate_plan(task,s["plan"]); graph=plan["graph"]
    require(s["graph"]==graph,"Dynamic graph mismatch")
    for k,lo,hi in (("limit",1,30),("calls",0,30),("round",0,2),("revisions",0,2),("output_retries",0,2)):
        require(type(s.get(k)) is int and lo<=s[k]<=hi,"Invalid dynamic counter")
    require(len(graph)<=s["limit"] and s["calls"]<=s["limit"] and s["round"]<=s["revisions"],"Dynamic budget mismatch")
    require(isinstance(s["identity"],dict) and s["identity"].get("backend")==s["backend"],"Dynamic backend mismatch")
    require(digest(contract(s))==s["contract_digest"],"Dynamic contract mismatch")
    check_routes(s["identity"],plan)
    require(isinstance(s["status"],str) and s["status"] in TERMINAL|{"READY","RUNNING","FAILED"},"Invalid dynamic status")
    events=s["events"]; artifacts=s["artifacts"]; reviews=s["reviews"]
    require(isinstance(events,list) and len(events)==s["calls"] and isinstance(artifacts,dict) and isinstance(reviews,list) and s["round"]<=len(reviews)<=s["round"]+1,"Dynamic ledger length mismatch")
    active={}; seen=set(); cursor=0
    for rnd in range(s["round"]+1):
        while cursor<len(events):
            e=events[cursor]
            require(isinstance(e,dict) and type(e.get("round")) is int and rnd<=e["round"]<=s["round"],"Invalid dynamic event round")
            if e["round"]!=rnd: break
            i=cursor+1; node=e.get("role")
            require(type(e.get("attempt")) is int and e["attempt"]==i and isinstance(node,str) and node in graph and e.get("kind")=="dynamic" and e.get("status") in {"reserved","interrupted","ok","failed"},"Invalid dynamic attempt")
            require(node not in active and set(graph[node])<=set(active),"Invalid dynamic execution order")
            require(e.get("inputs")=={n:active[n] for n in graph[node]},"Dynamic input artifact mismatch")
            if e["status"]=="ok":
                key=str(i); require(key in artifacts,"Missing artifact")
                value=validate_artifact(node,artifacts[key],task,plan)
                require(e.get("output_digest")==digest(value),"Artifact digest mismatch")
                active[node]=i; seen.add(key)
            else:
                require(str(i) not in artifacts,"Unsuccessful attempt contains artifact")
                if e["status"]=="reserved": require(rnd==s["round"] and s["status"]=="RUNNING","Invalid outstanding reservation")
            cursor+=1
        if rnd<len(reviews):
            require(set(active)==set(graph),"Review missing required outputs")
            current=review_record(rnd,active,artifacts,plan)
            require(reviews[rnd]==current,"Dynamic review history mismatch")
            if rnd<s["round"]:
                require(not current["gate"]["passed"] and rnd<s["revisions"],"Invalid repair after terminal review")
                require(rnd==0 or current["signature"]!=reviews[rnd-1]["signature"],"Repair after non-convergence")
                for n in current["invalidated"]: active.pop(n)
    require(cursor==len(events) and seen==set(artifacts) and active==s["active"],"Dynamic artifact ledger mismatch")
    final=reviews[-1]["gate"] if len(reviews)==s["round"]+1 else None
    require(s.get("gate")==final,"Dynamic gate mismatch")
    if s["status"] in {"PENDING_APPROVAL","DEMO_COMPLETE","EXPORTED"}:
        require(final is not None and final["passed"] and s.get("draft_digest")==digest(artifacts[str(active["executor"])]),"Invalid final approval state")
        require((s["backend"]=="demo")==(s["status"]=="DEMO_COMPLETE"),"Invalid demo approval state")
        if s["status"]=="EXPORTED": require(isinstance(s.get("export"),dict) and s["export"].get("digest")==s["draft_digest"],"Invalid export state")
    elif s["status"]=="BLOCKED":
        require(final is None or not final["passed"],"Invalid blocked gate")
        require(s.get("draft_digest") is None,"Blocked draft cannot be approved")
    else:
        require(final is None and s.get("draft_digest") is None,"Active run contains terminal result")
    if s["status"] in TERMINAL:
        require(not any(e["status"]=="reserved" for e in events),"Terminal state has outstanding reservation")
    require(s["status"]=="EXPORTED" or not s.get("export"),"Unexpected export receipt")
    enforce_text(canonical(task))
    return active

class DynamicEngine:
    def __init__(self,store,backend,output_retries=1):
        require(type(output_retries) is int and 0<=output_retries<=2,"Invalid output retry cap")
        self.store=store; self.backend=backend; self.output_retries=output_retries

    def create(self,raw,selection="auto",workers=2,call_limit=24,revisions=2):
        task=validate_task(raw); enforce_text(canonical(task))
        plan=make_plan(task,selection,workers); check_routes(self.backend.identity,plan)
        Budget(call_limit)
        require(len(plan["graph"])<=call_limit,"Budget cannot cover initial mandatory DAG")
        require(type(revisions) is int and 0<=revisions<=2,"Revisions must be 0–2")
        rid=self.store.new()
        s={"version":4,"id":rid,"task":task,"original_task":task,"plan":plan,"graph":plan["graph"],"identity":self.backend.identity,"backend":self.backend.name,"limit":call_limit,"revisions":revisions,"output_retries":self.output_retries,"calls":0,"round":0,"status":"READY","events":[],"artifacts":{},"active":{},"reviews":[]}
        s["contract_digest"]=digest(contract(s))
        self.store.save(s)
        return rid

    def execute(self,rid):
        with self.store.lock(rid):
            s=self.store.load(rid); validate_dynamic(s,rid)
            require(s["identity"]==self.backend.identity and s["backend"]==self.backend.name,"Checkpoint/model configuration mismatch")
            if s["status"] in TERMINAL: return self.report(s)
            for e in s["events"]:
                if e["status"]=="reserved": e.update(status="interrupted",error_code="INTERRUPTED")
            self.store.save(s)
            budget=Budget(s["limit"],s["calls"]); plan=s["plan"]; graph=plan["graph"]; active=s["active"]; artifacts=s["artifacts"]
            def run_layer(names):
                pending=[n for n in names if n not in active]
                while pending:
                    # Precharge the whole independent layer before dispatch; no partial unaccounted calls.
                    try: budget.reserve(len(pending))
                    except FactoryError:
                        s.update(status="BLOCKED",error="Call budget exhausted")
                        self.store.save(s); return False
                    records={}
                    for n in pending:
                        e={"attempt":len(s["events"])+1,"role":n,"kind":"dynamic","round":s["round"],"status":"reserved","inputs":{d:active[d] for d in graph[n]},"reserved_at":now()}
                        records[n]=e; s["events"].append(e)
                    s.update(calls=budget.used,status="RUNNING",error=None)
                    self.store.save(s)
                    def invoke(n):
                        start=time.monotonic(); stamp=now(); metrics={}
                        try:
                            payload=make_payload(s,n,active,artifacts)
                            failures=[e for e in s["events"] if e["role"]==n and e["round"]==s["round"] and e["status"]=="failed"]
                            if failures and failures[-1].get("error_code") in RETRYABLE:
                                payload["output_recovery"]={"error_code":failures[-1]["error_code"],"instruction":"Return the full valid contract. Never invent missing checks."}
                            require(len(enforce_text(canonical(payload)).encode("utf-8"))<=MAX_CONTEXT_BYTES,"Context byte limit exceeded")
                            kind=plan["registry"][n]["kind"]
                            if self.backend.name=="demo" and kind=="specialist":
                                value={"text":"Synthetic specialist fixture; not evidence of execution."}; metrics={"model":"none","input_tokens":None,"output_tokens":None}
                            else: value,metrics=self.backend.call(kind,payload)
                            value=validate_artifact(n,value,s["task"],plan)
                            return value,{"status":"ok",**metrics,"started_at":stamp,"ended_at":now(),"seconds":round(time.monotonic()-start,4)}
                        except Exception as exc:
                            return None,{"status":"failed","error":type(exc).__name__,"error_code":error_code(exc),**metrics,"started_at":stamp,"ended_at":now(),"seconds":round(time.monotonic()-start,4)}
                    results=parallel(pending,invoke,workers=plan["workers"])
                    retry=[]; stop=False
                    for n,(v,event) in results.items():
                        e=records[n]; e.update(event)
                        if v is not None:
                            i=e["attempt"]; artifacts[str(i)]=v; active[n]=i; e["output_digest"]=digest(v)
                        else:
                            count=sum(x["role"]==n and x["round"]==s["round"] and x["status"]=="failed" for x in s["events"])
                            if event["error_code"] in RETRYABLE and count<=s["output_retries"]: retry.append(n)
                            else: stop=True
                    s.update(status="FAILED" if stop or retry else "RUNNING",error="Role attempt failed; inspect event error_code" if stop or retry else None)
                    self.store.save(s)
                    if stop: return False
                    pending=retry
                return True
            while True:
                for layer in plan["layers"]:
                    if not run_layer(layer): return self.report(s)
                review=review_record(s["round"],active,artifacts,plan); s["reviews"].append(review); s["gate"]=review["gate"]
                if review["gate"]["passed"]:
                    s.update(status="DEMO_COMPLETE" if self.backend.name=="demo" else "PENDING_APPROVAL",draft_digest=digest(artifacts[str(active["executor"])]))
                    self.store.save(s); return self.report(s)
                repeated=len(s["reviews"])>1 and review["signature"]==s["reviews"][-2]["signature"]
                if repeated or s["round"]>=s["revisions"]:
                    s.update(status="BLOCKED",error="Repeated unchanged producer artifacts and failures" if repeated else "Mandatory review gate failed")
                    self.store.save(s); return self.report(s)
                s["round"]+=1; s["gate"]=None
                for n in review["invalidated"]: active.pop(n)
                self.store.save(s)

    def approve(self,rid,expected_digest,output):
        with self.store.lock(rid):
            s=self.store.load(rid); validate_dynamic(s,rid)
            path=export_approved(dict(s,outputs=output_map(s["active"],s["artifacts"])),expected_digest,output)
            s.update(status="EXPORTED",export={"path":path,"digest":expected_digest})
            self.store.save(s); return self.report(s)

    @staticmethod
    def report(s):
        events=s["events"]; totals={}; known={}
        for key in ("input_tokens","output_tokens"):
            values=[e.get(key) for e in events]; known[key]=sum(v for v in values if type(v) is int)
            totals[key]=known[key] if values and all(type(v) is int for v in values) else None
        versions=[{"agent":e["role"],"attempt":e["attempt"],"round":e["round"],"digest":e["output_digest"],"active":s["active"].get(e["role"])==e["attempt"]} for e in events if e["status"]=="ok"]
        return {"id":s["id"],"status":s["status"],"strategy":s["plan"]["mode"],"graph":s["graph"],"owners":s["plan"]["owners"],"workers":s["plan"]["workers"],"calls":s["calls"],"limit":s["limit"],"round":s["round"],"gate":s.get("gate"),"reviews":s["reviews"],"artifact_versions":versions,"draft_digest":s.get("draft_digest"),"error":s.get("error"),"metrics":totals,"known_usage":known,"events":events,"export":s.get("export"),"human_review_required":True,"evaluation":"fixture only" if s["backend"]=="demo" else "Model review; not proof of correctness or security"}
