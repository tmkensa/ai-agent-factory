import copy
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch
from factory.engine import FactoryError
from factory.architecture.team import make_plan, descendants
from factory.architecture.dynamic import DynamicEngine, validate_dynamic
from factory.architecture.models import DemoBackend
from factory.architecture.memory import Store
from factory.platform.providers import Router
from factory.platform.operations import compare

TASK={"goal":"Draft checklist","criteria":["Backup","Tests","Approval"],"language":"en","context":"Draft only","sources":[]}
TEAM={"agents":[{"name":"backup","job":"Backup","depends_on":[]},{"name":"tests","job":"Tests","depends_on":[]},{"name":"approval","job":"Approval","depends_on":["backup"]}],"owners":["backup","tests","approval"]}

class Model(DemoBackend):
    name="fixture-model"
    identity={"backend":"fixture-model"}
    def __init__(self): self.calls=[]; self.fail=False; self.stuck=False
    def call(self,role,payload):
        self.calls.append((role,copy.deepcopy(payload)))
        if role=="specialist":
            n=payload["specialist"]["name"]
            if self.fail and n=="tests":
                self.fail=False
                raise TimeoutError()
            return {"text":n+(" fixed" if "previous_output" in payload and not self.stuck else " original")},{"model":"fixture","input_tokens":3,"output_tokens":2}
        value,metrics=super().call(role,payload)
        if role=="executor":
            # Initial artifact content is a fixture. Make one required criterion fail initially.
            value["draft"]="Backup Tests Approval" if "previous_output" in payload and not self.stuck else "Tests Approval"
        return value,metrics

class DynamicTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.root=Path(t.name); self.store=Store(self.root,"dynamic")
    def test_auto_and_single(self):
        self.assertEqual(make_plan(TASK)["mode"],"single")
        p=make_plan(TASK|{"criteria":TASK["criteria"]+["Audit"]})
        self.assertEqual(p["mode"],"multi"); self.assertEqual(len(set(p["owners"])),4)
        self.assertEqual(len(make_plan(TASK,"single")["graph"]),4)
    def test_cycle_reserved_and_owner(self):
        for agents,owners in [
            ([{"name":"a","job":"a","depends_on":["a"]}],["a"]*3),
            ([{"name":"security","job":"a","depends_on":[]}],["executor"]*3),
            (TEAM["agents"],["backup","tests","unknown"]),
            ([{"name":"a","job":"a","depends_on":["executor"]}],["a"]*3)
        ]:
            with self.subTest(agents=agents,owners=owners),self.assertRaises(FactoryError):
                make_plan(TASK,{"agents":agents,"owners":owners})
    def test_mandatory_gates(self):
        p=make_plan(TASK,TEAM)
        self.assertEqual(set(p["graph"]["executor"]),{"backup","tests","approval"})
        self.assertEqual(set(p["graph"]["evaluator"]),{"executor","security","tester"})
        self.assertEqual(set(descendants(p["graph"],["backup"])),{"backup","approval","executor","security","tester","evaluator"})
    def test_targeted_repair_and_versions(self):
        model=Model(); e=DynamicEngine(self.store,model); rid=e.create(TASK,TEAM)
        r=e.execute(rid); self.assertEqual((r["status"],r["round"],r["calls"]),("PENDING_APPROVAL",1,13))
        self.assertEqual(r["reviews"][0]["roots"],["backup"])
        self.assertEqual(sum(x["agent"]=="tests" for x in r["artifact_versions"]),1)
        self.assertEqual(sum(x["agent"]=="backup" for x in r["artifact_versions"]),2)
        repair=[p for n,p in model.calls if n=="specialist" and p["specialist"]["name"]=="backup"][-1]
        self.assertEqual(repair["previous_output"],{"text":"backup original"})
        executor=[p for n,p in model.calls if n=="executor"][-1]
        self.assertEqual(executor["previous_output"],{"draft":"Tests Approval"})
        self.assertEqual(executor["dependencies"]["tests"],{"text":"tests original"})
        self.assertEqual(e.execute(rid),r)
        self.assertEqual(e.approve(rid,r["draft_digest"],self.root/"approved.md")["status"],"EXPORTED")
    def test_convergence_stop(self):
        model=Model(); model.stuck=True; e=DynamicEngine(self.store,model)
        r=e.execute(e.create(TASK,TEAM))
        self.assertEqual((r["status"],r["round"]),("BLOCKED",1))
        self.assertIn("unchanged",r["error"]); self.assertIsNone(r["draft_digest"])
    def test_budget_block_during_repair(self):
        e=DynamicEngine(self.store,Model()); rid=e.create(TASK,TEAM,call_limit=7)
        r=e.execute(rid); self.assertEqual((r["status"],r["calls"]),("BLOCKED",7))
        self.assertEqual(e.execute(rid),r)
    def test_resume_partial_layer(self):
        model=Model(); model.fail=True; e=DynamicEngine(self.store,model); rid=e.create(TASK,TEAM)
        r=e.execute(rid); self.assertEqual((r["status"],r["calls"]),("FAILED",2))
        r=e.execute(rid); self.assertEqual(r["status"],"PENDING_APPROVAL")
        self.assertEqual(sum(x["agent"]=="backup" and x["round"]==0 for x in r["artifact_versions"]),1)
        self.assertEqual(sum(x["role"]=="tests" for x in r["events"]),2)
    def test_artifact_tamper_and_approval(self):
        e=DynamicEngine(self.store,Model()); rid=e.create(TASK,TEAM); r=e.execute(rid)
        s=self.store.load(rid); s["artifacts"]["1"]["text"]="modified"; self.store.save(s)
        with self.assertRaises(FactoryError): e.execute(rid)
        with self.assertRaises(FactoryError): e.approve(rid,r["draft_digest"],self.root/"bad.md")
        self.assertEqual(list(self.store.summaries())[0]["status"],"CORRUPT")
    def test_dependency_provenance_tamper(self):
        e=DynamicEngine(self.store,Model()); rid=e.create(TASK,TEAM); e.execute(rid)
        s=self.store.load(rid); next(x for x in s["events"] if x["role"]=="executor")["inputs"]["backup"]=2; self.store.save(s)
        with self.assertRaises(FactoryError): e.execute(rid)
    def test_review_history_tamper(self):
        e=DynamicEngine(self.store,Model()); rid=e.create(TASK,TEAM); e.execute(rid)
        s=self.store.load(rid); s["reviews"][0]["roots"]=["tests"]; self.store.save(s)
        with self.assertRaises(FactoryError): e.execute(rid)
    def test_demo_and_compare(self):
        e=DynamicEngine(self.store,DemoBackend())
        a=e.create(TASK,"single"); b=e.create(TASK,TEAM)
        self.assertEqual(e.execute(a)["calls"],4); self.assertEqual(e.execute(b)["calls"],7)
        self.assertEqual(compare(self.store,a,b)["candidate"]["calls"],7)
        with self.assertRaises(FactoryError): e.approve(a,e.execute(a)["draft_digest"],self.root/"demo.md")
    def test_budget_minimum_and_workers(self):
        e=DynamicEngine(self.store,DemoBackend())
        with self.assertRaises(FactoryError): e.create(TASK,TEAM,call_limit=6)
        with self.assertRaises(FactoryError): make_plan(TASK,TEAM,workers=5)
    def test_parallel_workers(self):
        barrier=threading.Barrier(2)
        class Concurrent(DemoBackend):
            name="fixture-model"; identity={"backend":"fixture-model"}
            def call(self,role,payload):
                if role=="specialist":
                    if payload["specialist"]["name"] in {"backup","tests"}: barrier.wait(timeout=3)
                    return {"text":"fixture"},{"model":"fixture"}
                return super().call(role,payload)
        e=DynamicEngine(self.store,Concurrent()); r=e.execute(e.create(TASK,TEAM,workers=2))
        self.assertEqual(r["status"],"PENDING_APPROVAL")
    def test_agent_route_and_cloud_consent(self):
        with self.assertRaises(FactoryError): Router("ollama/local",{"agent:backup":"gemini/model"})
        router=Router("ollama/local",{"agent:backup":"ollama/other"})
        with patch("factory.platform.providers.request",return_value={"done":True,"message":{"content":'{"text":"fixture"}'}}) as call:
            _,m=router.call("specialist",{"task":TASK,"specialist":{"name":"backup","job":"Backup","criterion_ids":[0]}})
            self.assertEqual(m["model"],"ollama/other"); self.assertEqual(call.call_args.args[2]["model"],"other")
        with self.assertRaises(FactoryError): DynamicEngine(self.store,router).create(TASK,"single")
    def test_cli_dynamic_and_legacy_coexist(self):
        from factory.platform.__main__ import main
        task=self.root/"task.json"; task.write_text(json.dumps(TASK),encoding="utf-8")
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["team-plan",str(task),"--team","single"]),0)
            self.assertEqual(json.loads(out.getvalue())["mode"],"single")
        args=["--root",str(self.root),"--project","cli"]
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(args+["run",str(task),"--team","multi"]),0); r=json.loads(out.getvalue())
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(args+["resume",r["id"]]),0); self.assertEqual(json.loads(out.getvalue()),r)
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(args+["show",r["id"]]),0); self.assertEqual(json.loads(out.getvalue())["version"],4)
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(args+["run",str(task)]),0); old=json.loads(out.getvalue())
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(args+["resume",old["id"]]),0); self.assertEqual(json.loads(out.getvalue()),old)

    def test_schema_recovery_charged(self):
        class Missing(DemoBackend):
            name="fixture-model"; identity={"backend":"fixture-model"}
            def __init__(self): self.failed=False; self.recovery=None
            def call(self,role,payload):
                v,m=super().call(role,payload)
                if role=="tester" and not self.failed:
                    self.failed=True; v["checks"].pop()
                elif role=="tester":
                    self.recovery=payload.get("output_recovery")
                return v,m
        model=Missing(); e=DynamicEngine(self.store,model,1)
        r=e.execute(e.create(TASK,"single",call_limit=5))
        self.assertEqual((r["status"],r["calls"]),("PENDING_APPROVAL",5))
        self.assertEqual(model.recovery["error_code"],"MISSING_REVIEW_CHECKS")
        self.assertEqual(len(r["artifact_versions"]),4)
    def test_reserved_attempt_survives_interruption(self):
        e=DynamicEngine(self.store,DemoBackend()); rid=e.create(TASK,"single",call_limit=5)
        s=self.store.load(rid); s.update(status="RUNNING",calls=1)
        s["events"]=[{"attempt":1,"role":"executor","kind":"dynamic","round":0,"status":"reserved","inputs":{}}]
        self.store.save(s)
        r=e.execute(rid); self.assertEqual((r["status"],r["calls"]),("DEMO_COMPLETE",5))
        self.assertEqual(r["events"][0]["status"],"interrupted")
    def test_critical_veto_even_at_score100(self):
        class Critical(DemoBackend):
            def call(self,role,payload):
                v,m=super().call(role,payload)
                if role=="security": v["critical"]=["Blocking issue"]
                return v,m
        e=DynamicEngine(self.store,Critical()); r=e.execute(e.create(TASK,"single"))
        self.assertEqual((r["status"],r["gate"]["score"],r["gate"]["passed"]),("BLOCKED",100,False))
        self.assertEqual(r["reviews"][0]["roots"],["executor"])
    def test_failed_schema_no_budget_bypass(self):
        class Missing(DemoBackend):
            def call(self,role,payload):
                v,m=super().call(role,payload)
                if role=="tester": v["checks"].pop()
                return v,m
        e=DynamicEngine(self.store,Missing(),2); r=e.execute(e.create(TASK,"single",call_limit=4))
        self.assertEqual((r["status"],r["calls"]),("BLOCKED",4))
        self.assertFalse(any(v["agent"]=="evaluator" for v in r["artifact_versions"]))
    def test_invalid_artifact_no_raw_secret_persistence(self):
        class Leaky(DemoBackend):
            def call(self,role,payload):
                v,m=super().call(role,payload)
                if role=="executor": v["draft"]="-----BEGIN PRIVATE KEY-----"
                return v,m
        e=DynamicEngine(self.store,Leaky(),2); rid=e.create(TASK,"single")
        r=e.execute(rid)
        self.assertEqual((r["status"],r["calls"]),("FAILED",1))
        self.assertEqual(r["events"][0]["error_code"],"SECRET_DETECTED")
        self.assertNotIn("BEGIN PRIVATE KEY",(self.store.path(rid)/"state.json").read_text(encoding="utf-8"))
    def test_context_limit_explicit_failure(self):
        from factory.architecture.artifacts import make_payload
        task=TASK|{"context":"a"*24000,"sources":[{"id":"x","text":"b"*12000}]}
        plan=make_plan(task,"single")
        s={"task":task,"plan":plan,"round":0}
        with patch("factory.architecture.artifacts.MAX_CONTEXT_BYTES",10):
            with self.assertRaisesRegex(FactoryError,"Context byte limit"):
                make_payload(s,"executor",{}, {})
