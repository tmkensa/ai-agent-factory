"""Versioned artifacts and deterministic repair ownership."""
from factory.engine import require, clean_text
from .governance import validate, gate, digest, canonical, enforce_text
from .team import GATES, descendants

MAX_ARTIFACT_BYTES=64_000
MAX_CONTEXT_BYTES=320_000

def validate_artifact(node, value, task, plan):
    kind=plan["registry"][node]["kind"]
    if kind=="specialist":
        require(isinstance(value,dict) and set(value)=={"text"},"Invalid specialist output")
        clean_text(value["text"],3000)
    else:
        validate(kind,value,task)
    packed=enforce_text(canonical(value))
    require(len(packed.encode("utf-8"))<=MAX_ARTIFACT_BYTES,"Artifact byte limit exceeded")
    return value

def output_map(active, artifacts):
    return {n:artifacts[str(i)] for n,i in active.items()}

def review_record(round_no, active, artifacts, plan):
    outputs=output_map(active,artifacts)
    verdict=gate(outputs)
    details=[]; roots=set()
    for role in GATES:
        review=outputs[role]
        for c in review["checks"]:
            if not c["passed"]:
                owner=plan["owners"][c["id"]]; roots.add(owner)
                details.append({"reviewer":role,"criterion":c["id"],"owner":owner,"reason":c["reason"]})
        for issue in review["critical"]:
            # Free-text issues cannot grant a model authority to reroute an arbitrary agent.
            roots.add("executor")
            details.append({"reviewer":role,"criterion":None,"owner":"executor","reason":issue})
    invalidated=descendants(plan["graph"],roots)
    require(not roots or {"executor",*GATES}<=set(invalidated),"Repair would bypass mandatory review")
    # Exact repeated producer outputs AND same failing criteria/critical issues, not score alone.
    signature=digest({"producers":{n:digest(v) for n,v in outputs.items() if n not in GATES},
                      "failures":[[d["reviewer"],d["criterion"],d["owner"],d["reason"] if d["criterion"] is None else None] for d in details]})
    return {"round":round_no,"gate":verdict,"details":details,"roots":sorted(roots),"invalidated":invalidated,"signature":signature}

def make_payload(state,node,active,artifacts):
    plan=state["plan"]; role=plan["registry"][node]; task=state["task"]
    deps={n:active[n] for n in role["depends_on"]}
    payload={"task":task,"dependencies":output_map(deps,artifacts)}
    if role["kind"]=="specialist":
        payload["specialist"]={"name":node,"job":role["job"],"criterion_ids":[i for i,n in enumerate(plan["owners"]) if n==node]}
    if node not in GATES and state["round"]>0:
        previous=[e for e in state["events"] if e["role"]==node and e["status"]=="ok"]
        if previous:
            payload["previous_output"]=artifacts[str(previous[-1]["attempt"])]
        last=state["reviews"][-1]
        payload["repair_feedback"]=last["details"] if node=="executor" else [d for d in last["details"] if d["owner"]==node]
        payload["repair_instruction"]="Revise previous output using current dependencies and assigned feedback. Preserve correct material. Do not invent evidence."
    # Pass direct dependencies and own previous artifact only; no silent truncation.
    require(len(enforce_text(canonical(payload)).encode("utf-8"))<=MAX_CONTEXT_BYTES,"Context byte limit exceeded")
    return payload
