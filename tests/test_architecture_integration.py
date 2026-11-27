"""Additional architecture tests. HTTP fixture responses are not live model outputs."""
import http.client
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from factory.engine import FactoryError
from factory.architecture.agents import validate_task
from factory.architecture.governance import Budget, validate
from factory.architecture.memory import Store
from factory.architecture.models import DemoBackend, LocalRouter
from factory.architecture.orchestrator import Orchestrator

TASK = {"goal":"Draft a checklist", "criteria":["Backup","Tests"], "language":"en",
        "context":"Draft only", "sources":[{"id":"p","text":"Backup and Tests required."}]}


class RepairBackend(DemoBackend):
    def __init__(self):
        self.feedback = []

    def call(self, role, payload):
        out, metrics = super().call(role, payload)
        if role == "executor":
            self.feedback.append(payload["repair_feedback"])
            if len(self.feedback) == 1:
                out["draft"] = "Backup"
        return out, metrics


class LeakyBackend(DemoBackend):
    def call(self, role, payload):
        out, metrics = super().call(role, payload)
        if role == "executor":
            out["draft"] = "-----BEGIN PRIVATE KEY-----"
        return out, metrics


class Integration(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = Store(Path(tmp.name), "integration")

    def test_repair_feedback_and_convergence(self):
        backend = RepairBackend()
        engine = Orchestrator(self.store, backend)
        rid = engine.create(TASK)
        report = engine.execute(rid)
        self.assertEqual((report["status"], report["round"], report["calls"]), ("DEMO_COMPLETE", 1, 10))
        self.assertEqual(backend.feedback[0], [])
        self.assertTrue(any("Criterion 1" in f["issue"] for f in backend.feedback[1]))
        self.assertEqual(sum(e["role"] == "planner" for e in report["events"]), 1)

    def test_secret_output_not_saved(self):
        engine = Orchestrator(self.store, LeakyBackend())
        rid = engine.create(TASK)
        self.assertEqual(engine.execute(rid)["status"], "FAILED")
        raw = (self.store.path(rid) / "state.json").read_text(encoding="utf-8")
        self.assertNotIn("BEGIN PRIVATE KEY", raw)
        self.assertNotIn("executor", self.store.load(rid)["outputs"])

    def test_no_sources_uses_five_roles(self):
        engine = Orchestrator(self.store, DemoBackend())
        rid = engine.create(TASK | {"sources": []})
        report = engine.execute(rid)
        self.assertEqual((report["status"], report["calls"]), ("DEMO_COMPLETE", 5))
        self.assertNotIn("researcher", report["graph"])

    def test_wrong_model_cannot_resume(self):
        rid = Orchestrator(self.store, LocalRouter("one")).create(TASK)
        with self.assertRaises(FactoryError):
            Orchestrator(self.store, LocalRouter("two")).execute(rid)
        self.assertEqual(self.store.load(rid)["calls"], 0)

    def test_duplicate_source_and_unknown_field(self):
        for data in (TASK | {"sources": TASK["sources"] * 2}, TASK | {"shell": "not allowed"}):
            with self.subTest(data=data), self.assertRaises(FactoryError):
                validate_task(data)

    def test_quote_must_match_exactly(self):
        with self.assertRaises(FactoryError):
            validate("researcher", {"findings":[{"source":"p","quote":"  Backup  "}], "limitations":"none"}, TASK)

    def test_budget_cannot_be_refunded(self):
        budget = Budget(3)
        for invalid in (0, -1, True, 1.5):
            with self.subTest(invalid=invalid), self.assertRaises(FactoryError):
                budget.reserve(invalid)
        self.assertEqual(budget.used, 0)

    def test_loopback_http_full_workflow(self):
        requests = []
        mutex = threading.Lock()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                with mutex:
                    requests.append((self.path, request))
                role = request["messages"][0]["content"].split(" ")[3]
                payload = json.loads(request["messages"][1]["content"])
                value, _ = DemoBackend().call(role, payload)
                body = json.dumps({"done":True,"message":{"content":json.dumps(value)},
                                   "prompt_eval_count":11,"eval_count":7}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.shutdown)
        original = http.client.HTTPConnection
        port = server.server_address[1]
        def redirect(host, requested_port, timeout):
            self.assertEqual((host, requested_port), ("127.0.0.1", 11434))
            return original(host, port, timeout=timeout)
        with patch("factory.architecture.models.http.client.HTTPConnection", side_effect=redirect):
            engine = Orchestrator(self.store, LocalRouter("fixture-main", {"security":"fixture-review"}))
            rid = engine.create(TASK)
            report = engine.execute(rid)
        self.assertEqual(report["status"], "PENDING_APPROVAL")
        self.assertEqual(report["metrics"], {"input_tokens":66,"output_tokens":42})
        self.assertEqual(len(requests), 6)
        for path, req in requests:
            self.assertEqual(path, "/api/chat")
            self.assertFalse(req["stream"])
            self.assertNotIn("tools", req)
            expected = "fixture-review" if "security role" in req["messages"][0]["content"] else "fixture-main"
            self.assertEqual(req["model"], expected)

    def test_local_router_rejects_bad_protocol(self):
        payload = {"task": TASK}
        cases = [
            (302, b'{}'),
            (200, b'not json'),
            (200, b'x' * 1_000_001),
            (200, b'{"done":false,"message":{"content":"{}"}}'),
            (200, b'{"done":true,"done_reason":"length","message":{"content":"{}"}}'),
            (200, b'{"done":true,"message":{"tool_calls":[{}],"content":"{}"}}'),
        ]
        for status, raw in cases:
            with self.subTest(status=status, length=len(raw)):
                with patch("factory.architecture.models.http.client.HTTPConnection") as conn:
                    response = conn.return_value.getresponse.return_value
                    response.status = status
                    response.read.return_value = raw
                    with self.assertRaises((FactoryError, ValueError)):
                        LocalRouter("fixture").call("planner", payload)
                    conn.return_value.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
