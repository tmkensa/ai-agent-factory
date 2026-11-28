"""Opt-in CLI. Review every external action and its scope before approval."""
import argparse
import json
import sys
import sqlite3
import subprocess
from pathlib import Path
from factory.engine import FactoryError, read_json, require
from .providers import Router
from .evidence import fetch, MCP
from .workspace import digest, stage, sandbox_test, safe_text
from .operations import Notes, custom_skill, run_specialists, dashboard, compare


def runtime(root,project,spec=None,mapping=None,cloud=False,output_retries=0):
    from factory.architecture.memory import Store
    from factory.architecture.models import DemoBackend
    from factory.architecture.orchestrator import Orchestrator
    store=Store(root,project)
    backend=Router(spec,mapping,cloud) if spec else DemoBackend()
    require(not mapping or spec,"Role mapping requires default route")
    return store,Orchestrator(store,backend,output_retries)


def main(argv=None):
    p=argparse.ArgumentParser(description="AI Agent Factory platform preview")
    p.add_argument("--root",type=Path,default=Path(".factory-runs/v2")); p.add_argument("--project",default="default")
    p.add_argument("--route",help="provider/model; omit for offline demo")
    p.add_argument("--role-route",action="append",default=[],metavar="ROLE=PROVIDER/MODEL")
    p.add_argument("--output-retries",type=int,choices=[0,1,2],default=1,help="Bounded schema recovery per role/round; all attempts charged")
    p.add_argument("--allow-cloud",action="store_true",help="Permit data transfer and potentially paid model calls for this invocation")
    sub=p.add_subparsers(dest="cmd",required=True)
    r=sub.add_parser("run"); r.add_argument("task",type=Path); r.add_argument("--calls",type=int,default=24); r.add_argument("--specialists",type=Path); r.add_argument("--source",type=Path,action="append",default=[]); r.add_argument("--memory-query"); r.add_argument("--memory-model"); r.add_argument("--team",help="auto, single, multi or path to operator-defined team JSON"); r.add_argument("--workers",type=int,choices=[1,2,3,4],default=2)
    a=sub.add_parser("team-plan"); a.add_argument("task",type=Path); a.add_argument("--team",default="auto"); a.add_argument("--workers",type=int,choices=[1,2,3,4],default=2)
    for n in ("show","resume"): sub.add_parser(n).add_argument("id")
    a=sub.add_parser("approve"); a.add_argument("id"); a.add_argument("--digest",required=True); a.add_argument("--output",type=Path,required=True)
    a=sub.add_parser("web"); a.add_argument("url"); a.add_argument("--host",required=True); a.add_argument("--approve",action="store_true")
    a=sub.add_parser("mcp"); a.add_argument("--port",type=int,required=True); a.add_argument("--tool",required=True); a.add_argument("--args",type=Path,required=True); a.add_argument("--approve",action="store_true")
    a=sub.add_parser("skill"); a.add_argument("definition",type=Path)
    sub.add_parser("digest").add_argument("plan",type=Path)
    a=sub.add_parser("contract-check"); a.add_argument("contract",type=Path); a.add_argument("references",type=Path)
    a=sub.add_parser("stage"); a.add_argument("plan",type=Path); a.add_argument("destination",type=Path); a.add_argument("--digest",required=True)
    a=sub.add_parser("sandbox-test"); a.add_argument("workspace",type=Path); a.add_argument("--image",required=True); a.add_argument("--suite",choices=["python","php-lint"],default="python"); a.add_argument("--approve",action="store_true")
    a=sub.add_parser("remember"); a.add_argument("file",type=Path); a.add_argument("--embedding-model")
    a=sub.add_parser("recall"); a.add_argument("query"); a.add_argument("--embedding-model")
    a=sub.add_parser("schedule"); a.add_argument("task",type=Path); a.add_argument("--interval",type=int,required=True); a.add_argument("--calls",type=int,default=24); a.add_argument("--approve",action="store_true")
    a=sub.add_parser("compare"); a.add_argument("baseline"); a.add_argument("candidate")
    sub.add_parser("tick"); sub.add_parser("jobs"); sub.add_parser("cancel").add_argument("id"); sub.add_parser("dashboard").add_argument("output",type=Path)
    a=p.parse_args(argv)
    try:
        cmd=a.cmd
        if cmd=="web":
            require(a.approve,"Explicit network read approval required"); result=fetch(a.url,a.host)
        elif cmd=="mcp": result=MCP(a.port,[a.tool]).call(a.tool,read_json(a.args),a.approve)
        elif cmd=="skill": print(custom_skill(read_json(a.definition))); return 0
        elif cmd=="digest": result={"digest":digest(read_json(a.plan,300000))}
        elif cmd=="team-plan":
            from factory.architecture.team import make_plan
            selection=a.team if a.team in {"auto","single","multi"} else read_json(a.team)
            result=make_plan(read_json(a.task),selection,a.workers)
        elif cmd=="contract-check":
            from factory.architecture.artifact_contract import check
            result=check(read_json(a.contract,300000),read_json(a.references,300000))
        elif cmd=="stage": result={"workspace":stage(read_json(a.plan,300000),a.destination,a.digest)}
        elif cmd=="sandbox-test": result=sandbox_test(a.workspace,a.image,a.approve,a.suite)
        else:
            mapping=dict(x.split("=",1) for x in a.role_route)
            store,engine=runtime(a.root,a.project,a.route,mapping,a.allow_cloud,a.output_retries if a.route else 0)
            if cmd=="run":
                from factory.architecture.agents import validate_task
                task=validate_task(read_json(a.task));
                task["sources"] += [read_json(path) for path in a.source]
                if a.memory_query:
                    notes=Notes(store.root/"platform.sqlite3")
                    task["sources"] += [{"id":"note:"+x["id"],"text":"OPERATOR NOTE — UNVERIFIED:\n"+x["text"][:11950]} for x in notes.search(a.memory_query,a.memory_model,limit=3)]
                task=validate_task(task); require(type(a.calls) is int and 1<=a.calls<=30,"Call budget 1–30")
                if a.team:
                    from factory.architecture.dynamic import DynamicEngine
                    require(not a.specialists,"Use team definitions or legacy specialists, not both")
                    selection=a.team if a.team in {"auto","single","multi"} else read_json(a.team)
                    engine=DynamicEngine(store,engine.backend,a.output_retries if a.route else 0)
                    rid=engine.create(task,selection,a.workers,a.calls)
                else:
                    require(not any(k.startswith("agent:") for k in mapping),"Per-agent routes require --team")
                    definitions=read_json(a.specialists) if a.specialists else None
                    rid=engine.create(task,a.calls,specialist_definitions=definitions)
                print("Run ID: "+rid,file=sys.stderr); result=engine.execute(rid)
            elif cmd=="resume":
                if store.load(a.id).get("version")==4:
                    from factory.architecture.dynamic import DynamicEngine
                    engine=DynamicEngine(store,engine.backend)
                result=engine.execute(a.id)
            elif cmd=="show":
                result=store.load(a.id)
                if result.get("version")==3:
                    from factory.architecture.state import validate_state
                    validate_state(result,a.id)
                elif result.get("version")==4:
                    from factory.architecture.dynamic import validate_dynamic
                    validate_dynamic(result,a.id)
            elif cmd=="approve":
                if store.load(a.id).get("version")==4:
                    from factory.architecture.dynamic import DynamicEngine
                    engine=DynamicEngine(store,engine.backend)
                result=engine.approve(a.id,a.digest,a.output)
            elif cmd=="compare": result=compare(store,a.baseline,a.candidate)
            else:
                notes=Notes(store.root/"platform.sqlite3")
                if cmd=="remember":
                    with a.file.open("rb") as f: data=f.read(48001)
                    require(len(data)<=48000,"Note byte limit"); result={"id":notes.remember(data.decode(),a.embedding_model)}
                elif cmd=="recall": result=notes.search(a.query,a.embedding_model)
                elif cmd=="schedule":
                    from factory.architecture.agents import validate_task
                    require(not mapping,"Scheduled role routing unsupported"); result={"id":notes.schedule({"task":validate_task(read_json(a.task)),"route":a.route,"calls":a.calls},a.interval,a.approve)}
                elif cmd=="tick":
                    def runner(spec):
                        _,e=runtime(a.root,a.project,spec["route"]); rid=e.create(spec["task"],spec["calls"]); return e.execute(rid)
                    result=notes.tick(runner)
                elif cmd=="jobs": result=notes.jobs()
                elif cmd=="cancel": notes.cancel(a.id); result={"cancelled":a.id}
                else: result={"dashboard":dashboard(store,notes,a.output)}
        # No automatic publication. User chooses how to use results.
        safe_text(json.dumps(result,ensure_ascii=False)); print(json.dumps(result,ensure_ascii=True,indent=2))
        if cmd=="sandbox-test": return 0 if result["exit_code"]==0 else 2
        if cmd=="contract-check": return 0 if result["passed"] else 2
        return 2 if cmd in {"run","resume"} and result["status"] in {"FAILED","BLOCKED"} else 0
    except (FactoryError,OSError,ValueError,KeyError,TypeError,sqlite3.Error,RuntimeError,subprocess.SubprocessError) as exc:
        # Do not echo potentially sensitive provider or OS exception details.
        print("Error: "+(str(exc) if isinstance(exc,FactoryError) else type(exc).__name__),file=sys.stderr); return 1

if __name__=="__main__": raise SystemExit(main())
