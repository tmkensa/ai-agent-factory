import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from factory.engine import Engine, Demo, FactoryError, read_json, save_json
from factory.architecture.models import DemoBackend
from factory.architecture.memory import Store
from factory.architecture.orchestrator import Orchestrator
from factory.architecture.contracts import role_schema, error_code
from factory.platform.operations import compare
from factory.platform.workspace import safe_text

TASK={"goal":"Draft checklist","criteria":["Backup","Tests"],"language":"en","context":"Draft only","sources":[]}
class Model(DemoBackend):
    name="test-model"
    identity={"backend":"test-model"}
    def __init__(self): self.seen=[]; self.fail=True
    def call(self,role,payload):
        self.seen.append((role,payload))
        if role=="specialist":
            if payload["specialist"]["name"]=="second" and self.fail:
                self.fail=False; raise TimeoutError()
            return {"text":"Synthetic analysis"},{"model":"fixture","input_tokens":3,"output_tokens":2}
        return super().call(role,payload)
class BadReview(Model):
    def call(self,role,payload):
        v,m=super().call(role,payload)
        if role=="tester" and self.fail:
            self.fail=False; v["checks"].pop()
        return v,m
class Reliability(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.root=Path(t.name); self.store=Store(self.root,"test")
    def test_legacy_negative_calls(self):
        e=Engine(self.root,Demo()); rid=e.create({k:v for k,v in TASK.items() if k!="sources"})
        p=self.root/rid/"state.json"; s=read_json(p); s.update(calls=-50,revisions=100); save_json(p,s)
        with self.assertRaises(FactoryError): e.execute(rid)
    def test_terminal_corruption(self):
        e=Orchestrator(self.store,Model()); rid=e.create(TASK); r=e.execute(rid)
        s=self.store.load(rid); s["outputs"]["security"]={}; self.store.save(s)
        with self.assertRaises(FactoryError): e.execute(rid)
        with self.assertRaises(FactoryError): e.approve(rid,r["draft_digest"],self.root/"bad.md")
    def test_budget_contract_tamper(self):
        e=Orchestrator(self.store,Model()); rid=e.create(TASK,6)
        s=self.store.load(rid); s["limit"]=30; self.store.save(s)
        with self.assertRaises(FactoryError): e.execute(rid)
    def test_recover_missing_checks(self):
        model=BadReview(); e=Orchestrator(self.store,model,1); rid=e.create(TASK)
        r=e.execute(rid)
        self.assertEqual((r["status"],r["calls"]),( "PENDING_APPROVAL",6))
        self.assertTrue(any(x.get("error_code")=="MISSING_REVIEW_CHECKS" for x in r["events"]))
        self.assertEqual([p["output_recovery"]["error_code"] for n,p in model.seen if n=="tester" and "output_recovery" in p],["MISSING_REVIEW_CHECKS"])
    def test_retry_charged_no_bypass(self):
        e=Orchestrator(self.store,BadReview(),1); r=e.execute(e.create(TASK,4))
        self.assertEqual((r["status"],r["calls"]),("BLOCKED",4))
        self.assertIsNone(r["gate"])
    def test_specialist_resume_and_compare(self):
        model=Model(); e=Orchestrator(self.store,model)
        base=e.create(TASK); e.execute(base)
        rid=e.create(TASK,20,specialist_definitions=[{"name":"first","job":"One","depends_on":[]},{"name":"second","job":"Two","depends_on":["first"]}])
        self.assertEqual(e.execute(rid)["calls"],2)
        r=e.execute(rid)
        self.assertEqual((r["status"],r["calls"]),("PENDING_APPROVAL",9))
        self.assertEqual(sum(n=="specialist" and p["specialist"]["name"]=="first" for n,p in model.seen),1)
        self.assertEqual(compare(self.store,base,rid)["candidate"]["calls"],9)
    def test_interrupted_attempt_not_refunded(self):
        e=Orchestrator(self.store,Model()); rid=e.create(TASK)
        s=self.store.load(rid); s.update(calls=1,status="RUNNING")
        s["events"]=[{"attempt":1,"role":"planner","kind":"role","round":0,"status":"reserved"}]; self.store.save(s)
        r=e.execute(rid); self.assertEqual(r["calls"],6); self.assertEqual(r["events"][0]["status"],"interrupted")
    def test_safe_diagnostics(self):
        self.assertEqual(error_code(FactoryError("Missing review checks")),"MISSING_REVIEW_CHECKS")
        self.assertEqual(error_code(FactoryError("private response")),"FACTORY_POLICY_ERROR")
        self.assertEqual(error_code(TimeoutError("private")),"TIMEOUT")
    def test_extended_secret_patterns(self):
        for value in ("AIza"+"x"*35,"whsec_"+"x"*20,"mysql://u:p@example.invalid/db","eyJ"+"a"*10+"."+"b"*10+"."+"c"*10):
            with self.assertRaises(FactoryError): safe_text(value)
    def test_exact_review_schema(self):
        s=role_schema("tester",3)["properties"]["checks"]
        self.assertEqual((s["minItems"],s["maxItems"]),(3,3))
        self.assertEqual(s["items"]["properties"]["id"]["maximum"],2)
