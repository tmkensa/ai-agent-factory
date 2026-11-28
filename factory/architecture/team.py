"""Deterministic, inspectable team factory. No model-generated tools or privileges."""
import re
from factory.engine import require, clean_text
from .agents import validate_task
from .governance import canonical, enforce_text
from .workflow import layers

NAME=re.compile(r"[a-z][a-z0-9-]{0,31}\Z")
RESERVED={"planner","researcher","executor","security","tester","evaluator","specialist"}
GATES=("security","tester","evaluator")

def analyze(raw):
    task=validate_task(raw)
    signals={"criteria":len(task["criteria"]),"sources":len(task["sources"]),"context_chars":len(task["context"])}
    # Heuristic, not a trained complexity classifier or proof that a team is better.
    team=signals["criteria"]>=4 or signals["sources"]>=3 or signals["context_chars"]>=4000
    return {"suggested":"multi" if team else "single","signals":signals,"method":"fixed thresholds; operator override available"}

def make_plan(raw, selection="auto", workers=2):
    task=validate_task(raw); count=len(task["criteria"])
    require(type(workers) is int and 1<=workers<=4,"Workers must be 1–4")
    info=analyze(task)
    if isinstance(selection,str):
        require(selection in {"auto","single","multi"},"Invalid team strategy")
        mode=info["suggested"] if selection=="auto" else selection
        agents=[]; owners=["executor"]*count
        if mode=="multi":
            # At most four grouped drafting assignments, all criteria assigned once.
            slots=min(count,4)
            for i in range(slots):
                ids=list(range(i,count,slots))
                name="criterion-"+str(i+1)
                agents.append({"name":name,"job":"Develop concrete draft material for the assigned mandatory criteria, including evidence and limitations.","depends_on":[]})
                for j in ids: owners[j]=name
    else:
        require(isinstance(selection,dict) and set(selection)=={"agents","owners"},"Team definition requires agents and owners")
        agents=selection["agents"]; owners=selection["owners"]; mode="custom"
    require(isinstance(agents,list) and len(agents)<=8,"At most eight custom agents")
    registry={}
    for item in agents:
        require(isinstance(item,dict) and set(item)=={"name","job","depends_on"},"Invalid agent definition")
        n=item["name"]; d=item["depends_on"]
        require(isinstance(n,str) and NAME.fullmatch(n) and n not in RESERVED and n not in registry,"Invalid or duplicate agent name")
        job=clean_text(item["job"],1500); enforce_text(job)
        require(isinstance(d,list) and all(isinstance(x,str) for x in d) and len(d)==len(set(d)),"Invalid agent dependencies")
        registry[n]={"kind":"specialist","job":job,"depends_on":list(d)}
    require(all(d in registry for a in registry.values() for d in a["depends_on"]),"Custom agents may depend only on registered custom agents")
    require(isinstance(owners,list) and len(owners)==count and all(isinstance(n,str) and (n=="executor" or n in registry) for n in owners),"Exactly one registered owner per criterion")
    registry["executor"]={"kind":"executor","job":"Integrate the artifacts into a standalone draft.","depends_on":sorted(registry)}
    registry["security"]={"kind":"security","job":"Review draft for security and mandatory criteria.","depends_on":["executor"]}
    registry["tester"]={"kind":"tester","job":"Review every mandatory acceptance criterion.","depends_on":["executor"]}
    registry["evaluator"]={"kind":"evaluator","job":"Evaluate draft and preserve reviewer vetoes.","depends_on":["executor","security","tester"]}
    graph={n:a["depends_on"] for n,a in registry.items()}
    order=list(layers(graph))
    plan={"mode":mode,"analysis":info,"workers":workers,"registry":registry,"owners":list(owners),"graph":graph,"layers":order}
    enforce_text(canonical(plan))
    return plan

def validate_plan(task, plan):
    require(isinstance(plan,dict) and plan.get("mode") in {"single","multi","custom"},"Invalid saved team plan")
    registry=plan["registry"]
    if plan["mode"]=="custom":
        selection={"agents":[{"name":n,"job":a["job"],"depends_on":a["depends_on"]} for n,a in registry.items() if n not in {"executor",*GATES}],"owners":plan["owners"]}
    else: selection=plan["mode"]
    require(make_plan(task,selection,plan["workers"])==plan,"Saved team plan mismatch")
    return plan

def descendants(graph, roots):
    affected=set(roots)
    require(affected<=set(graph),"Unknown repair owner")
    while True:
        more={n for n,deps in graph.items() if set(deps)&affected}
        if more<=affected: return sorted(affected)
        affected.update(more)
