"""Project-scoped checkpoint storage and aggregate performance memory."""
import re
import uuid
from pathlib import Path
from contextlib import contextmanager
from factory.engine import require, read_json, save_json, FactoryError

PROJECT=re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}\Z")
RUN=re.compile(r"[0-9a-f]{32}\Z")

class Store:
    def __init__(self,root,project):
        require(isinstance(project,str) and PROJECT.fullmatch(project),"Invalid project ID")
        self.root=Path(root)/project
        require(not self.root.is_symlink(),"Project symlinks denied")
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
    def new(self):
        rid=uuid.uuid4().hex
        (self.root/rid).mkdir(mode=0o700)
        return rid
    def path(self,rid):
        require(isinstance(rid,str) and RUN.fullmatch(rid),"Invalid run ID")
        p=self.root/rid
        require(p.is_dir() and not p.is_symlink(),"Run not found or unsafe")
        return p
    def load(self,rid):
        return read_json(self.path(rid)/"state.json",5_000_000)
    def save(self,state):
        save_json(self.path(state["id"])/"state.json",state)
    @contextmanager
    def lock(self,rid):
        lock=self.path(rid)/".lock"
        try: lock.mkdir()
        except FileExistsError: require(False,"Run locked; inspect active process before removing stale lock")
        try: yield
        finally: lock.rmdir()
    def summaries(self):
        for path in sorted(self.root.iterdir()):
            if RUN.fullmatch(path.name) and path.is_dir() and not path.is_symlink():
                try:
                    s=self.load(path.name)
                    if s.get("version")==3:
                        from .state import validate_state
                        validate_state(s,path.name)
                    yield {"id":s["id"],"status":s["status"],"backend":s["backend"],"events":s["events"],"gate":s.get("gate")}
                except (OSError,ValueError,KeyError,TypeError,FactoryError):
                    yield {"id":path.name,"status":"CORRUPT","backend":"unknown","events":[],"gate":None}

def optimization(store):
    """Deterministic recommendation only. Does not mutate prompts or permissions."""
    aggregates={}
    runs=0
    for state in store.summaries():
        if state["backend"]=="demo": continue
        runs+=1
        for event in state["events"]:
            a=aggregates.setdefault(event["role"],{"calls":0,"failures":0,"seconds":0.0})
            a["calls"]+=1
            a["failures"]+=event["status"]!="ok"
            a["seconds"]+=event["seconds"]
    if not aggregates:
        return {"measured_runs":runs,"roles":aggregates,"proposal":"Collect real-model baseline runs first; demo runs are excluded."}
    weakest=max(aggregates,key=lambda n:(aggregates[n]["failures"]/aggregates[n]["calls"],aggregates[n]["seconds"]/aggregates[n]["calls"]))
    return {"measured_runs":runs,"roles":aggregates,"proposal":"Benchmark an alternative prompt or model for "+weakest+" on identical acceptance tests; human approval required."}
