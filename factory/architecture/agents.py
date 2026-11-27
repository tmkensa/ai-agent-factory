"""Role contracts, dynamic team construction, and reusable skill export."""
from dataclasses import dataclass
from factory.engine import require, clean_text

@dataclass(frozen=True)
class Role:
    name: str
    job: str
    output: str

ROLES = {
    "planner": Role("planner", "Decompose the goal into a short plan; identify missing inputs and do not claim execution.", "steps"),
    "researcher": Role("researcher", "Analyze only supplied evidence. Quote exact excerpts, identify their source IDs and list uncertainty. Never invent citations or browse.", "findings"),
    "executor": Role("executor", "Produce a standalone draft based on the plan, source evidence and repair feedback. Never execute commands or claim external actions.", "draft"),
    "security": Role("security", "Review the draft for sensitive data exposure, injection, unauthorized actions, unsafe claims and other security risks.", "review"),
    "tester": Role("tester", "Review each mandatory acceptance criterion using explicit evidence. Mark unsupported criteria false. Do not claim to have executed external tests.", "review"),
    "evaluator": Role("evaluator", "Independently judge each mandatory criterion using the draft and review evidence. Do not override a failed security or test gate.", "review"),
}

def team(task):
    """Only add research when source material is supplied. Other roles are required gates."""
    names = ["planner"]
    if task["sources"]:
        names.append("researcher")
    names += ["executor", "security", "tester", "evaluator"]
    return {name: ROLES[name] for name in names}

def role_skill(name):
    require(name in ROLES, "Unknown role")
    role = ROLES[name]
    return (
        "---\nname: factory-" + name + "\n"
        "description: " + role.job + "\n---\n"
        "# " + name.title() + "\n\n"
        "## Job\n" + role.job + "\n\n"
        "## Inputs\nValidated task, assigned dependencies and repair notes.\n\n"
        "## Output\nStructured " + role.output + " JSON and verifiable evidence.\n\n"
        "## Never\nExecute commands, request secrets, invent evidence, or change permissions.\n"
        "## Done means\nAll required fields are valid; facts and limitations are explicit.\n"
        "## Ask first\nAny external transmission, publication or change to the authorized scope.\n"
    )

def validate_task(raw):
    require(isinstance(raw, dict), "Task must be an object")
    require(set(raw) <= {"goal","criteria","context","language","sources"}, "Unknown task field")
    require({"goal","criteria","context","language"} <= set(raw), "Missing task fields")
    from factory.engine import validate_task as old_validate
    task = old_validate({k: raw[k] for k in ("goal","criteria","context","language")})
    sources = raw.get("sources", [])
    require(isinstance(sources, list) and len(sources) <= 8, "At most eight supplied sources")
    ids = set()
    total = 0
    for source in sources:
        require(isinstance(source, dict) and set(source) == {"id","text"}, "Source requires id and text")
        sid = clean_text(source["id"], 80)
        require(sid not in ids and sid == source["id"], "Duplicate or invalid source ID")
        ids.add(sid)
        clean_text(source["text"], 12000)
        total += len(source["text"])
    require(total <= 32000, "Source text budget exceeded")
    return {**task, "sources": sources}
