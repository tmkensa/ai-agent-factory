"""Validated dependency graph and bounded parallel scheduling."""
from concurrent.futures import ThreadPoolExecutor
from factory.engine import require

def graph(roles):
    nodes = {"planner": ()}
    if "researcher" in roles:
        nodes["researcher"] = ()
    nodes["executor"] = tuple(nodes)
    nodes["security"] = ("executor",)
    nodes["tester"] = ("executor",)
    nodes["evaluator"] = ("executor","security","tester")
    return nodes

def layers(nodes):
    require(all(dep in nodes for deps in nodes.values() for dep in deps), "Unknown dependency")
    completed = set()
    pending = set(nodes)
    while pending:
        ready = sorted(n for n in pending if set(nodes[n]) <= completed)
        require(bool(ready), "Dependency cycle")
        yield ready
        pending.difference_update(ready)
        completed.update(ready)

def parallel(names, callback, workers=2):
    """Return results in stable order. Callers must not write shared state in workers."""
    if len(names) == 1:
        return {names[0]: callback(names[0])}
    with ThreadPoolExecutor(max_workers=min(workers,len(names))) as pool:
        futures = {n: pool.submit(callback,n) for n in names}
        return {n: f.result() for n,f in futures.items()}
