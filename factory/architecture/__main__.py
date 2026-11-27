"""Preview CLI, separate from the stable v0.1 command."""
import argparse
import json
import sys
from pathlib import Path
from factory.engine import FactoryError, read_json
from .agents import role_skill
from .models import DemoBackend, LocalRouter
from .memory import Store, optimization
from .orchestrator import Orchestrator

def main():
    p=argparse.ArgumentParser(description="AI Agent Factory architecture preview")
    p.add_argument("--root",type=Path,default=Path(".factory-runs/v2"))
    p.add_argument("--project",default="default")
    p.add_argument("--model",help="Name of an installed local Ollama model; omitted for demo")
    p.add_argument("--role-model",action="append",default=[],metavar="ROLE=MODEL")
    p.add_argument("--timeout",type=int,default=120)
    sub=p.add_subparsers(dest="action",required=True)
    run=sub.add_parser("run"); run.add_argument("task",type=Path); run.add_argument("--calls",type=int,default=24); run.add_argument("--revisions",type=int,default=2)
    for name in ("resume","show"): sub.add_parser(name).add_argument("id")
    approve=sub.add_parser("approve"); approve.add_argument("id"); approve.add_argument("--digest",required=True); approve.add_argument("--output",type=Path,required=True)
    sub.add_parser("optimize")
    skill=sub.add_parser("skill"); skill.add_argument("role")
    a=p.parse_args()
    try:
        if a.action=="skill":
            print(role_skill(a.role)); return 0
        if a.role_model and not a.model: p.error("--role-model requires --model")
        mapping=dict(x.split("=",1) for x in a.role_model)
        backend=LocalRouter(a.model,mapping,a.timeout) if a.model else DemoBackend()
        store=Store(a.root,a.project); o=Orchestrator(store,backend)
        if a.action=="run":
            rid=o.create(read_json(a.task),a.calls,a.revisions)
            print("Run ID: "+rid,file=sys.stderr); result=o.execute(rid)
        elif a.action=="resume": result=o.execute(a.id)
        elif a.action=="show": result=store.load(a.id)
        elif a.action=="approve": result=o.approve(a.id,a.digest,a.output)
        else: result=optimization(store)
        print(json.dumps(result,ensure_ascii=True,indent=2))
        return 2 if a.action in {"run","resume"} and result["status"] in {"FAILED","BLOCKED"} else 0
    except (FactoryError,OSError,ValueError,KeyError,TypeError) as exc:
        print("Error: "+str(exc),file=sys.stderr); return 1

if __name__=="__main__": raise SystemExit(main())
