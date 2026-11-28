import tempfile
import unittest
import threading
from pathlib import Path
from factory.engine import FactoryError
from factory.architecture.agents import team,validate_task,role_skill
from factory.architecture.workflow import graph,layers,parallel
from factory.architecture.governance import validate,gate,Budget,export_approved
from factory.architecture.models import DemoBackend,LocalRouter
from factory.architecture.memory import Store,optimization
from factory.architecture.orchestrator import Orchestrator

TASK={"goal":"Draft checklist","criteria":["Backup","Tests"],"language":"en","context":"Draft only","sources":[{"id":"p","text":"Backup and Tests required."}]}

class Critical(DemoBackend):
    def call(self,role,payload):
        v,m=super().call(role,payload)
        if role=="security": v["critical"]=["Critical security issue"]
        return v,m

class Flaky(DemoBackend):
    def __init__(self): self.fail=True
    def call(self,role,payload):
        if role=="researcher" and self.fail:
            self.fail=False; raise TimeoutError()
        return super().call(role,payload)

class FixtureAsModel(DemoBackend):
    name="test-model"
    identity={"backend":"test-model"}
    # Test double only; never a real model.

class Architecture(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup)
        self.root=Path(d.name); self.store=Store(self.root,"one")
    def test_dynamic_team(self):
        self.assertIn("researcher",team(validate_task(TASK)))
        self.assertNotIn("researcher",team(validate_task(TASK|{"sources":[]})))
    def test_graph_layers(self):
        self.assertEqual(list(layers(graph(team(TASK)))),[["planner","researcher"],["executor"],["security","tester"],["evaluator"]])
        with self.assertRaises(FactoryError): list(layers({"a":("b",),"b":("a",)}))
    def test_parallel(self):
        barrier=threading.Barrier(2)
        def call(name): barrier.wait(timeout=3); return name
        self.assertEqual(parallel(["a","b"],call),{"a":"a","b":"b"})
    def test_demo(self):
        o=Orchestrator(self.store,DemoBackend()); rid=o.create(TASK)
        r=o.execute(rid)
        self.assertEqual((r["status"],r["calls"]),("DEMO_COMPLETE",6))
        self.assertEqual(o.execute(rid),r)
        with self.assertRaises(FactoryError): o.approve(rid,r["draft_digest"],self.root/"draft.md")
    def test_critical_veto_and_repair(self):
        o=Orchestrator(self.store,Critical()); rid=o.create(TASK)
        r=o.execute(rid)
        self.assertEqual((r["status"],r["round"],r["calls"]),("BLOCKED",2,14))
        self.assertEqual(r["gate"]["score"],100)
    def test_checkpoint_resume(self):
        o=Orchestrator(self.store,Flaky()); rid=o.create(TASK)
        self.assertEqual(o.execute(rid)["status"],"FAILED")
        self.assertEqual(o.execute(rid)["calls"],7)
        events=self.store.load(rid)["events"]
        self.assertEqual(sum(e["role"]=="planner" for e in events),1)
    def test_budget_precharged(self):
        o=Orchestrator(self.store,DemoBackend()); rid=o.create(TASK,call_limit=1)
        r=o.execute(rid); self.assertEqual((r["status"],r["calls"]),("BLOCKED",0))
    def test_fake_citation(self):
        with self.assertRaises(FactoryError):
            validate("researcher",{"findings":[{"source":"p","quote":"invented"}],"limitations":"none"},TASK)
    def test_secret(self):
        o=Orchestrator(self.store,DemoBackend())
        with self.assertRaises(FactoryError):
            o.create(TASK|{"context":"-----BEGIN PRIVATE KEY-----"})
    def test_approval_digest_and_no_overwrite(self):
        o=Orchestrator(self.store,FixtureAsModel()); rid=o.create(TASK)
        r=o.execute(rid); path=self.root/"draft.md"
        self.assertEqual(r["status"],"PENDING_APPROVAL")
        with self.assertRaises(FactoryError): o.approve(rid,"wrong",path)
        path.write_text("existing")
        with self.assertRaises(FileExistsError): o.approve(rid,r["draft_digest"],path)
        self.assertEqual(path.read_text(),"existing")
        other=self.root/"new.md"
        self.assertEqual(o.approve(rid,r["draft_digest"],other)["status"],"EXPORTED")
        self.assertIn("Backup",other.read_text())
        with self.assertRaises(FactoryError): o.approve(rid,r["draft_digest"],self.root/"duplicate.md")
    def test_project_isolation(self):
        rid=Orchestrator(self.store,DemoBackend()).create(TASK)
        with self.assertRaises(FactoryError): Store(self.root,"two").load(rid)
        with self.assertRaises(FactoryError): Store(self.root,"../escape")
    def test_skill_and_optimizer(self):
        self.assertIn("name: factory-security",role_skill("security"))
        self.assertEqual(optimization(self.store)["measured_runs"],0)
    def test_router(self):
        self.assertEqual(LocalRouter("local",{"security":"other"}).identity["per_role"]["security"],"other")
        with self.assertRaises(FactoryError): LocalRouter("local",{"unknown":"other"})
    def test_budget(self):
        b=Budget(3); b.reserve(3)
        with self.assertRaises(FactoryError): b.reserve(1)
