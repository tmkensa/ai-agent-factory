"""Fail-closed output checks, bounded budget, and human approval."""
import hashlib
import json
import re
from pathlib import Path
from threading import Lock
from factory.engine import require, clean_text

from .contracts import SECRET
ROLES_WITH_REVIEW = {"security","tester","evaluator"}

def canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",",":"))

def digest(data):
    return hashlib.sha256(canonical(data).encode("utf-8")).hexdigest()

def enforce_text(text):
    require(not SECRET.search(text), "Potential secret detected; do not persist or transmit it")
    return text

def validate(role, value, task):
    require(isinstance(value,dict), "Role output must be an object")
    count=len(task["criteria"])
    if role=="planner":
        require(set(value)=={"steps"} and isinstance(value["steps"],list) and 1<=len(value["steps"])<=8,"Invalid plan")
        for x in value["steps"]: clean_text(x,1000)
    elif role=="researcher":
        require(set(value)=={"findings","limitations"} and isinstance(value["findings"],list) and len(value["findings"])<=16,"Invalid research output")
        clean_text(value["limitations"],2000)
        sources={s["id"]:s["text"] for s in task["sources"]}
        for f in value["findings"]:
            require(isinstance(f,dict) and set(f)=={"source","quote"},"Invalid finding")
            require(isinstance(f["source"],str) and f["source"] in sources,"Unknown source")
            clean_text(f["quote"],1500)
            quote=f["quote"]
            require(len(quote)<=1500 and quote in sources[f["source"]],"Unverified source quotation")
    elif role=="executor":
        require(set(value)=={"draft"},"Invalid draft")
        clean_text(value["draft"],40000)
    elif role in ROLES_WITH_REVIEW:
        from factory.engine import validate_output
        validate_output("reviewer",value,count)
    else:
        require(False,"Unregistered role")
    enforce_text(canonical(value))
    return value

def gate(outputs):
    reviews=[outputs[r] for r in ("security","tester","evaluator")]
    failures=[]
    for name,review in zip(("security","tester","evaluator"),reviews):
        failures += [{"role":name,"issue":x} for x in review["critical"]]
        failures += [{"role":name,"issue":f"Criterion {c['id']}: {c['reason']}"} for c in review["checks"] if not c["passed"]]
    checks=[c for r in reviews for c in r["checks"]]
    score=round(100*sum(c["passed"] for c in checks)/len(checks))
    return {"passed":not failures,"score":score,"failures":failures}

class Budget:
    def __init__(self, limit, used=0):
        require(type(limit) is int and 1<=limit<=30,"Call limit must be 1–30")
        require(type(used) is int and 0<=used<=limit,"Invalid previous call count")
        self.limit=limit; self.used=used; self.lock=Lock()
    def reserve(self,count):
        require(type(count) is int and count>0,"Reservation must be a positive integer")
        with self.lock:
            require(self.used+count<=self.limit,"Call budget exhausted")
            self.used+=count

def export_approved(state, expected_digest, output):
    """Explicit user approval of exact final draft; create a new file only."""
    require(state["status"]=="PENDING_APPROVAL","Run has not passed review")
    require(state["backend"]!="demo","Demo output cannot be approved for export")
    require(digest(state["outputs"]["executor"])==expected_digest==state["draft_digest"],"Approval digest mismatch")
    require(not state.get("export"),"Draft already exported")
    text=enforce_text(state["outputs"]["executor"]["draft"])
    output=Path(output)
    require(output.suffix.lower()==".md","Only Markdown draft export is allowed")
    # Exclusive open: no overwrite and no execution of content.
    with output.open("x",encoding="utf-8") as f:
        f.write(text+"\n")
    return str(output.resolve())
