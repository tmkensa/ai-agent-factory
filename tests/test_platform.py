import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from factory.engine import FactoryError
from factory.platform.providers import Router, request
from factory.platform.evidence import fetch, MCP, PlainText
from factory.platform.workspace import stage, digest, snapshot, sandbox_test, docker_command
from factory.platform.operations import Notes, run_specialists, specialists, custom_skill, dashboard, compare

TASK={"goal":"Test","criteria":["One"],"context":"","language":"en","sources":[]}
PLAN={"files":[{"path":"src/main.py","content":"print(1)\n"},{"path":"tests/test_x.py","content":"# example\n"}]}
IMAGE="python@sha256:"+"a"*64

class PlatformTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.root=Path(t.name)
    def test_cloud_requires_approval(self):
        with self.assertRaises(FactoryError): Router("openai/model")
        with self.assertRaises(FactoryError): Router("ollama/local",{"security":"gemini/model"})
        with self.assertRaises(FactoryError): Router("gemini/../../foo",allow_cloud=True)
    @patch.dict("os.environ",{"OPENAI_API_KEY":"test","ANTHROPIC_API_KEY":"test","GEMINI_API_KEY":"test"})
    def test_four_provider_contracts(self):
        text='{"steps":["one"]}'
        cases=[("ollama/model",{"done":True,"message":{"content":text},"prompt_eval_count":2,"eval_count":3},"/api/chat"),
               ("openai/model",{"choices":[{"finish_reason":"stop","message":{"content":text}}],"usage":{"prompt_tokens":2,"completion_tokens":3}},"/v1/chat/completions"),
               ("anthropic/model",{"stop_reason":"end_turn","content":[{"type":"text","text":text}],"usage":{"input_tokens":2,"output_tokens":3}},"/v1/messages"),
               ("gemini/model",{"candidates":[{"finishReason":"STOP","content":{"parts":[{"text":text}]}}],"usageMetadata":{"promptTokenCount":2,"candidatesTokenCount":3}},"/v1beta/models/model:generateContent")]
        for spec,response,path in cases:
            with self.subTest(spec=spec),patch("factory.platform.providers.request",return_value=response) as call:
                value,metric=Router("ollama/local",{"planner":spec},True).call("planner",{"task":TASK})
                self.assertEqual(value,{"steps":["one"]}); self.assertEqual(metric,{"model":spec,"input_tokens":2,"output_tokens":3}); self.assertEqual(call.call_args.args[1],path)
                self.assertNotIn("tools",call.call_args.args[2])
    def test_router_rejects_secret_before_call(self):
        with patch("factory.platform.providers.request") as call:
            with self.assertRaises(FactoryError): Router("ollama/local").call("planner",{"task":TASK|{"context":"-----BEGIN PRIVATE KEY-----"}})
            call.assert_not_called()
    def test_router_rejects_tool_response(self):
        with patch("factory.platform.providers.request",return_value={"done":True,"message":{"content":"{}","tool_calls":[{}]}}):
            with self.assertRaises(FactoryError): Router("ollama/local").call("planner",{"task":TASK})
    def test_http_rejects_redirect(self):
        with patch("factory.platform.providers.http.client.HTTPSConnection") as http:
            http.return_value.getresponse.return_value.status=302
            with self.assertRaises(FactoryError): request("api.openai.com","/v1/chat/completions",{})
            http.return_value.close.assert_called_once()
    def test_web_rejects_nonpublic_ip_and_unapproved_host(self):
        with self.assertRaises(FactoryError): fetch("https://bad.example/x","good.example")
        with patch("factory.platform.evidence.socket.getaddrinfo",return_value=[(None,None,None,None,("127.0.0.1",443))]):
            with self.assertRaises(FactoryError): fetch("https://example.org/x","example.org")
        with self.assertRaises(FactoryError): fetch("https://example.org/x?secret=1","example.org")
    def test_web_parses_untrusted_html(self):
        p=PlainText(); p.feed("<p>Hello</p><script>hidden()</script><p>World</p>"); self.assertEqual(p.parts,["Hello","World"])
        with patch("factory.platform.evidence.socket.getaddrinfo",return_value=[(None,None,None,None,("8.8.8.8",443))]),patch("factory.platform.evidence.PinnedHTTPS") as c:
            r=c.return_value.getresponse.return_value; r.status=200; r.getheader.side_effect=lambda k,d: {"Content-Type":"text/html"}.get(k,d); r.read.return_value=b"<h1>Public evidence</h1>"
            out=fetch("https://example.org/x","example.org"); self.assertIn("Public evidence",out["text"]); c.assert_called_once_with("example.org","8.8.8.8")
    def test_mcp_allowlist_and_readonly(self):
        m=MCP(5000,["read"])
        with patch.object(m,"rpc") as rpc:
            with self.assertRaises(FactoryError): m.call("read",{})
            with self.assertRaises(FactoryError): m.call("delete",{},True)
            rpc.assert_not_called()
            rpc.return_value={"tools":[{"name":"read","annotations":{"readOnlyHint":False}}]}
            with self.assertRaises(FactoryError): m.call("read",{},True)
        with patch.object(m,"rpc",side_effect=[{"tools":[{"name":"read","annotations":{"readOnlyHint":True}}]},{"content":[{"type":"text","text":"data"}]}]): self.assertEqual(m.call("read",{},True),{"id":"mcp:read","text":"data"})
    def test_mcp_protocol_metadata(self):
        with patch("factory.platform.evidence.request",return_value={"jsonrpc":"2.0","id":1,"result":{"resultType":"complete","tools":[]}}) as call:
            self.assertEqual(MCP(5000,[]).tools(),[]); args=call.call_args.args; self.assertEqual(args[-1],5000); self.assertEqual(args[3]["MCP-Protocol-Version"],"2026-07-28"); self.assertEqual(args[2]["params"]["_meta"]["io.modelcontextprotocol/clientCapabilities"],{})
    def test_stage_digest_no_overwrite(self):
        dest=self.root/"out"
        with self.assertRaises(FactoryError): stage(PLAN,dest,"wrong")
        self.assertFalse(dest.exists()); stage(PLAN,dest,digest(PLAN)); self.assertEqual((dest/"src/main.py").read_text(),"print(1)\n")
        with self.assertRaises(FileExistsError): stage(PLAN,dest,digest(PLAN))
    def test_stage_unsafe_paths(self):
        for path in ("../escape.py","/etc/test.py",".env.txt","dir/CON.txt","C:/x.py","a\\b.py"):
            with self.subTest(path=path),self.assertRaises(FactoryError):
                plan={"files":[{"path":path,"content":"data"}]}; stage(plan,self.root/"out",digest(plan))
        self.assertFalse((self.root/"out").exists())
    def test_stage_rejects_secrets_and_snapshot_hidden_files(self):
        plan={"files":[{"path":"x.txt","content":"-----BEGIN PRIVATE KEY-----"}]}
        with self.assertRaises(FactoryError): stage(plan,self.root/"out",digest(plan))
        src=self.root/"src"; stage(PLAN,src,digest(PLAN)); (src/".env").write_text("secret")
        with self.assertRaises(FactoryError): snapshot(src,self.root/"clean")
    def test_sandbox_command_and_gate(self):
        src=self.root/"src"; stage(PLAN,src,digest(PLAN)); clean=self.root/"clean"; snapshot(src,clean)
        cmd=docker_command(clean,IMAGE,"example"); self.assertIn("--network=none",cmd); self.assertIn("--read-only",cmd); self.assertIn("--pull=never",cmd); self.assertIn("--cap-drop=ALL",cmd); self.assertIn("--user=65534:65534",cmd)
        with patch("factory.platform.workspace._sandbox",return_value={"exit_code":0,"output":"fixture"}) as run:
            with self.assertRaises(FactoryError): sandbox_test(src,IMAGE)
            run.assert_not_called(); self.assertEqual(sandbox_test(src,IMAGE,True)["exit_code"],0)
        with self.assertRaises(FactoryError): docker_command(clean,"python:latest","example")
    def test_php_lint_suite(self):
        src=self.root/"php"; plan={"files":[{"path":"app/Test.php","content":"<?php echo 1;"}]}; stage(plan,src,digest(plan))
        self.assertEqual(docker_command(src,IMAGE,"example","php-lint")[-3:],["php","-l","./app/Test.php"])
    def test_custom_roles_dependencies_and_output(self):
        roles=[{"name":"domain","job":"Analyze domain","depends_on":[]},{"name":"summary","job":"Summarize","depends_on":["domain"]}]
        class Backend:
            def call(self,role,payload):
                if payload["specialist"]["name"]=="summary": assert payload["dependencies"]=={"domain":"draft"}
                return {"text":"draft"},{"input_tokens":2,"output_tokens":3}
        evidence,metrics=run_specialists(roles,TASK,Backend(),2); self.assertEqual(len(metrics),2); self.assertTrue(evidence[0]["text"].startswith("UNVERIFIED")); self.assertIn("name: custom-domain",custom_skill(roles[0]))
        with self.assertRaises(FactoryError): run_specialists(roles,TASK,Backend(),1)
        with self.assertRaises(FactoryError): specialists([{"name":"x","job":"a","depends_on":["x"]}])
    def test_memory_search_and_isolation(self):
        n=Notes(self.root/"one.db"); other=Notes(self.root/"two.db"); n.remember("نسخ احتياطي database")
        self.assertEqual(len(n.search("نسخ")),1); self.assertEqual(other.search("نسخ"),[])
    def test_memory_vector_mock(self):
        n=Notes(self.root/"vector.db")
        with patch("factory.platform.operations.request",side_effect=[{"embeddings":[[1,0]]},{"embeddings":[[1,0]]}]):
            n.remember("document","embed-local"); self.assertEqual(n.search("query","embed-local")[0]["score"],1.0)
    def test_schedule_claim_and_no_cloud(self):
        n=Notes(self.root/"schedule.db"); spec={"task":TASK,"route":None,"calls":8}
        with self.assertRaises(FactoryError): n.schedule(spec,3600)
        with self.assertRaises(FactoryError): n.schedule(spec|{"route":"openai/model"},3600,True)
        jid=n.schedule(spec,3600,True,now=100); self.assertEqual(n.tick(lambda _:None,now=3699),[])
        def run(s): self.assertEqual(s,spec); return {"id":"run","status":"DEMO_COMPLETE"}
        self.assertEqual(n.tick(run,now=3700)[0]["id"],jid); self.assertEqual(n.tick(run,now=3700),[]); n.cancel(jid); self.assertEqual(n.jobs()[0]["status"],"cancelled")
    def test_schedule_failure_not_retried(self):
        n=Notes(self.root/"schedule.db"); n.schedule({"task":TASK,"route":None,"calls":8},3600,True,now=0)
        def fail(_): raise RuntimeError("private")
        n.tick(fail,now=3600); self.assertEqual(n.jobs()[0]["status"],"failed"); self.assertEqual(n.tick(fail,now=7200),[])
    def test_dashboard_escapes_and_hides_drafts(self):
        n=Notes(self.root/"d.db"); store=SimpleNamespace(summaries=lambda:iter([{"id":"<script>","status":"ok","backend":"demo","events":[],"gate":{},"draft":"PRIVATE DRAFT"}]))
        out=self.root/"dash.html"; dashboard(store,n,out); text=out.read_text(encoding="utf-8"); self.assertIn("&lt;script&gt;",text); self.assertNotIn("PRIVATE DRAFT",text)
        with self.assertRaises(FileExistsError): dashboard(store,n,out)

    def test_compare_requires_identical_inputs(self):
        a={"task":TASK,"status":"DEMO_COMPLETE","gate":{"score":100},"calls":6,"backend":"demo","events":[{"seconds":0.2}]}
        store=SimpleNamespace(load=lambda rid: a if rid=="a" else a|{"calls":7})
        self.assertEqual(compare(store,"a","b")["candidate"]["calls"],7)
        store=SimpleNamespace(load=lambda rid: a if rid=="a" else a|{"task":TASK|{"goal":"different"}})
        with self.assertRaises(FactoryError): compare(store,"a","b")

    def test_cli_stage(self):
        from factory.platform.__main__ import main
        from contextlib import redirect_stdout
        path=self.root/"plan.json"; path.write_text(json.dumps(PLAN))
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(["digest",str(path)]),0)
            d=json.loads(stdout.getvalue())["digest"]
        with redirect_stdout(io.StringIO()): self.assertEqual(main(["stage",str(path),str(self.root/"staged"),"--digest",d]),0)
        self.assertTrue((self.root/"staged/src/main.py").is_file())

if __name__=="__main__": unittest.main()
