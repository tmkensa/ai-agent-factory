"""End-to-end fixture checks; no external APIs, real model inference or Docker."""
import json, sqlite3, tempfile, subprocess, sys, time, threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from factory.architecture.models import DemoBackend
from factory.platform.evidence import MCP

with tempfile.TemporaryDirectory() as directory:
    d=Path(directory)
    def cli(*args):
        x=subprocess.run([sys.executable,'-m','factory.platform','--root',str(d/'runs'),'--project','smoke',*map(str,args)],capture_output=True,text=True,timeout=15)
        if x.returncode: raise RuntimeError(f'{args[0]} failed: {x.returncode} {x.stderr[:500]}')
        return json.loads(x.stdout)
    r=cli('run','examples/architecture.ar.json'); assert r['status']=='DEMO_COMPLETE'
    en=cli('run','examples/architecture.en.json'); assert en['status']=='DEMO_COMPLETE'
    en2=cli('run','examples/architecture.en.json'); assert cli('compare',en['id'],en2['id'])['baseline']['calls']==en['calls']
    note=d/'note.txt'; note.write_text('backup procedure fixture',encoding='utf-8'); cli('remember',note)
    assert len(cli('recall','backup'))==1
    mem=cli('run','examples/architecture.en.json','--memory-query','backup'); assert mem['status']=='DEMO_COMPLETE'
    jid=cli('schedule','examples/architecture.en.json','--interval',3600,'--approve')['id']; assert cli('tick')==[]
    db=d/'runs/smoke/platform.sqlite3'
    with sqlite3.connect(db) as c:c.execute('update jobs set due=? where id=?',(time.time()-1,jid))
    tick=cli('tick'); assert tick[0]['status']=='DEMO_COMPLETE'; assert cli('tick')==[]; cli('cancel',jid); assert cli('jobs')[0]['status']=='cancelled'
    page=Path(cli('dashboard',d/'dashboard.html')['dashboard']); assert page.is_file() and 'backup procedure fixture' not in page.read_text(encoding="utf-8")
    dig=cli('digest','examples/stage-plan.json')['digest']; cli('stage','examples/stage-plan.json',d/'staged','--digest',dig)
    assert subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=d/'staged',capture_output=True,timeout=10).returncode==0
    print('PASS: Arabic/English workflow, identical-contract comparison, lexical memory retrieval, simulated due schedule/claim/cancel, read-only dashboard and staged sample unit test.')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            try:
                req=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path=='/mcp':
                    assert self.headers['MCP-Protocol-Version']=='2026-07-28'
                    assert req['params']['_meta']['io.modelcontextprotocol/protocolVersion']=='2026-07-28'
                    if req['method']=='tools/list': result={'resultType':'complete','tools':[{'name':'read','annotations':{'readOnlyHint':True},'inputSchema':{'type':'object'}}]}
                    else:
                        assert req['method']=='tools/call' and req['params']['name']=='read'
                        result={'resultType':'complete','content':[{'type':'text','text':'fixture evidence'}]}
                    response={'jsonrpc':'2.0','id':req['id'],'result':result}
                elif self.path=='/api/embed': response={'embeddings':[[1.0,0.0,0.0]]}
                else:
                    assert self.path=='/api/chat'; prompt=req['messages'][0]['content']; payload=json.loads(req['messages'][1]['content'])
                    roles={'Plan the task.':'planner','Use only supplied sources;':'researcher','Draft the deliverable':'executor','Review privacy':'security','Review mandatory':'tester','Evaluate each':'evaluator','Perform the operator-defined':'specialist'}
                    role=next(v for k,v in roles.items() if prompt.startswith(k))
                    val={'text':'Synthetic specialist fixture; unverified.'} if role=='specialist' else DemoBackend().call(role,payload)[0]
                    response={'done':True,'message':{'content':json.dumps(val,ensure_ascii=False)},'prompt_eval_count':12,'eval_count':5}
                raw=json.dumps(response).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
            except Exception:
                self.send_error(400)
    srv=ThreadingHTTPServer(('127.0.0.1',0),Handler); t=threading.Thread(target=srv.serve_forever,daemon=True);t.start()
    try:
        assert MCP(srv.server_port,['read']).call('read',{},True)['text']=='fixture evidence';print('PASS: actual loopback HTTP MCP tools/list and tools/call with synthetic local server.')
    finally:srv.shutdown();srv.server_close();t.join()
    try: srv=ThreadingHTTPServer(('127.0.0.1',11434),Handler)
    except OSError: print('SKIP: Ollama fixture port unavailable (no real service accessed).')
    else:
        t=threading.Thread(target=srv.serve_forever,daemon=True);t.start()
        try:
            rr=cli('--route','ollama/fixture','--role-route','security=ollama/fixture-reviewer','run','examples/architecture.en.json','--specialists','examples/specialists.json','--calls',20)
            assert rr['status']=='PENDING_APPROVAL' and rr['total_calls_this_invocation']==8 and len(rr['specialist_metrics'])==2
            res=cli('approve',rr['id'],'--digest',rr['draft_digest'],'--output',d/'approved.md'); assert res['status']=='EXPORTED'
            cli('remember',note,'--embedding-model','fixture'); assert len(cli('recall','backup','--embedding-model','fixture'))==1
            print('PASS: actual loopback HTTP model transport through full custom-agent pipeline (8 fixture calls), human approval/export and embedding retrieval.')
        finally:srv.shutdown();srv.server_close();t.join()
