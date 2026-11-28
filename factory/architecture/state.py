"""Checkpoint validation for local reliability; not hostile-writer authentication."""
from factory.engine import require
from .agents import validate_task, team
from .workflow import graph
from .governance import validate, gate, digest, enforce_text, canonical

TERMINAL={"PENDING_APPROVAL","DEMO_COMPLETE","BLOCKED","EXPORTED"}

def contract(s):
    return {k:s[k] for k in ("original_task","limit","revisions","output_retries","identity","specialists")}

def validate_state(s,rid):
    require(isinstance(s,dict) and s.get("version")==3 and s.get("id")==rid,"Unsupported checkpoint version or identity; start a new run")
    for k,lo,hi in (("limit",1,30),("revisions",0,2),("round",0,2),("calls",0,30),("output_retries",0,2)):
        require(type(s.get(k)) is int and lo<=s[k]<=hi,"Invalid checkpoint counter: "+k)
    require(s["calls"]<=s["limit"] and s["round"]<=s["revisions"],"Checkpoint budget or round exceeded")
    task=validate_task(s["task"]); original=validate_task(s["original_task"])
    require(digest(contract(s))==s["contract_digest"],"Checkpoint contract mismatch")
    require(s["identity"].get("backend")==s["backend"],"Checkpoint backend mismatch")
    enforce_text(canonical(task))
    require(s["status"] in TERMINAL|{"READY","RUNNING","FAILED"},"Invalid checkpoint status")
    from factory.platform.operations import specialists
    roles,_=specialists(s["specialists"])
    spec=s["specialist_outputs"]
    require(isinstance(spec,dict) and set(spec)<=set(roles),"Invalid specialist checkpoint")
    for n,t in spec.items():
        require(isinstance(t,str) and 0<len(t.strip())<=3000 and set(roles[n]["depends_on"])<=set(spec),"Invalid specialist output/dependency")
        enforce_text(t)
    expected=dict(original)
    if len(spec)==len(roles):
        expected["sources"]=original["sources"]+[{"id":"specialist:"+n,"text":"UNVERIFIED GENERATED ANALYSIS:\n"+spec[n]} for n in sorted(spec)]
    require(task==expected,"Checkpoint task/artifact mismatch")
    nodes={n:list(d) for n,d in graph(team(task)).items()}
    require(s["graph"]==nodes,"Checkpoint graph mismatch")
    out=s["outputs"]
    require(isinstance(out,dict) and set(out)<=set(nodes),"Invalid checkpoint outputs")
    if len(spec)!=len(roles): require(not out,"Main roles started before specialists completed")
    for n,v in out.items():
        require(set(nodes[n])<=set(out),"Missing output dependency")
        validate(n,v,task)
    ev=s["events"]
    require(isinstance(ev,list) and len(ev)==s["calls"],"Checkpoint attempt ledger mismatch")
    for i,e in enumerate(ev,1):
        require(isinstance(e,dict) and e.get("attempt")==i and e.get("status") in {"reserved","interrupted","ok","failed"} and type(e.get("round")) is int and 0<=e["round"]<=s["round"],"Invalid attempt record")
        require(e.get("kind") in {"role","specialist"} and e.get("role") in (roles if e["kind"]=="specialist" else nodes),"Unknown attempt role")
    for n,v in spec.items():
        matches=[e for e in ev if e["kind"]=="specialist" and e["role"]==n and e["status"]=="ok"]
        require(bool(matches) and matches[-1].get("output_digest")==digest(v),"Specialist output digest mismatch")
    for n,v in out.items():
        matches=[e for e in ev if e["kind"]=="role" and e["role"]==n and e["status"]=="ok" and (n in {"planner","researcher"} or e["round"]==s["round"])]
        require(bool(matches) and matches[-1].get("output_digest")==digest(v),"Role output digest mismatch")
    feedback=s["feedback"]
    require(isinstance(feedback,list) and len(feedback)<=54 and all(isinstance(f,dict) and set(f)=={"role","issue"} and f["role"] in {"security","tester","evaluator"} and isinstance(f["issue"],str) and len(f["issue"])<=2100 for f in feedback),"Invalid checkpoint feedback")
    require(s["round"]>0 or not feedback,"Unexpected initial repair feedback")
    enforce_text(canonical(feedback))
    if s["status"] in TERMINAL: require(not any(e["status"]=="reserved" for e in ev),"Terminal state has pending attempts")
    if s["status"] in {"PENDING_APPROVAL","DEMO_COMPLETE","EXPORTED"}:
        require(set(out)==set(nodes),"Incomplete terminal output")
        require(gate(out)==s.get("gate") and s["gate"]["passed"],"Terminal gate mismatch")
        require(digest(out["executor"])==s.get("draft_digest"),"Terminal draft mismatch")
        require((s["backend"]=="demo")== (s["status"]=="DEMO_COMPLETE"),"Terminal backend mismatch")
        if s["status"]=="EXPORTED": require(isinstance(s.get("export"),dict) and s["export"].get("digest")==s["draft_digest"],"Export digest mismatch")
    elif s.get("gate") is not None:
        require(set(out)==set(nodes) and gate(out)==s["gate"] and not s["gate"]["passed"],"Stale review gate")
    return task
