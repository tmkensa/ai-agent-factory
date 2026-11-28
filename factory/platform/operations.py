"""Explicit custom roles, local project memory, recurring jobs, and HTML dashboard."""
import html
import json
import math
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from factory.engine import require
from .workspace import safe_text, digest
from .providers import request, route

NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,47}\Z")


def specialists(raw):
    require(isinstance(raw,list) and len(raw)<=5,"At most five custom specialists")
    roles={}
    for item in raw:
        require(isinstance(item,dict) and set(item)=={"name","job","depends_on"},"Invalid specialist definition")
        name=item["name"]; job=safe_text(item["job"]); deps=item["depends_on"]
        require(isinstance(name,str) and NAME.fullmatch(name) and name not in roles,"Invalid or duplicate specialist")
        require(1<=len(job.strip())<=1500 and isinstance(deps,list) and all(isinstance(d,str) for d in deps) and len(deps)==len(set(deps)),"Invalid specialist contract")
        roles[name]={"job":job,"depends_on":deps}
    require(all(d in roles for r in roles.values() for d in r["depends_on"]),"Unknown specialist dependency")
    done=set(); layers=[]
    while len(done)<len(roles):
        ready=sorted(n for n,r in roles.items() if n not in done and set(r["depends_on"])<=done)
        require(bool(ready),"Specialist dependency cycle")
        layers.append(ready); done.update(ready)
    return roles,layers


def custom_skill(item):
    roles,_=specialists([item]); name=next(iter(roles)); job=roles[name]["job"]
    require(name==name.lower() and "_" not in name,"Skill name must use lowercase letters and hyphens")
    return ("---\nname: custom-"+name+"\ndescription: " + json.dumps("Operator-defined drafting specialist: "+job[:200],ensure_ascii=False)+"\n---\n# "+name+"\n\n## Assignment\n"+job+"\n\n## Boundaries\nReturn evidence and limitations. Never execute commands, access secrets, or expand permissions. Ask before external actions.\n")


def run_specialists(raw,task,backend,limit):
    from concurrent.futures import ThreadPoolExecutor
    roles,layers=specialists(raw)
    require(type(limit) is int and len(roles)<=limit,"Specialist call budget exceeded")
    outputs={}; metrics=[]
    for layer in layers:
        def run(name):
            role=roles[name]; started=time.monotonic()
            payload={"task":task,"specialist":{"name":name,"job":role["job"]},"dependencies":{d:outputs[d] for d in role["depends_on"]}}
            value,usage=backend.call("specialist",payload)
            require(isinstance(value,dict) and set(value)=={"text"},"Invalid specialist output")
            text=safe_text(value["text"]); require(0<len(text.strip())<=3000,"Specialist output limit")
            return name,text,{"role":name,"seconds":round(time.monotonic()-started,4),**usage}
        with ThreadPoolExecutor(max_workers=2) as pool:
            for name,text,metric in pool.map(run,layer):
                outputs[name]=text; metrics.append(metric)
    # Keep generated claims distinct from external sources. They are not proof.
    evidence=[{"id":"specialist:"+n,"text":"UNVERIFIED GENERATED ANALYSIS:\n"+text} for n,text in outputs.items()]
    return evidence,metrics


class Notes:
    def __init__(self, path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        require(not self.path.is_symlink(),"Unsafe notes database")
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS notes (id TEXT PRIMARY KEY, text TEXT NOT NULL, model TEXT, vector TEXT, created REAL NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, spec TEXT NOT NULL, interval INTEGER NOT NULL, due REAL NOT NULL, status TEXT NOT NULL, result TEXT)")
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=5)
        try:
            with db: yield db
        finally: db.close()
    def remember(self,text,model=None):
        text=safe_text(text); require(0<len(text.strip())<=12000,"Note size limit")
        vector=embed(model,text) if model else None
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            require(db.execute("SELECT count(*) FROM notes").fetchone()[0]<1000,"Project note limit")
            nid=uuid.uuid4().hex; db.execute("INSERT INTO notes VALUES (?,?,?,?,?)",(nid,text,model,json.dumps(vector),time.time()))
        return nid
    def search(self,query,model=None,limit=5):
        query=safe_text(query); require(0<len(query.strip())<=2000 and type(limit) is int and 1<=limit<=20,"Invalid search")
        q=embed(model,query) if model else set(re.findall(r"\w+",query.casefold()))
        with self.db() as db: rows=db.execute("SELECT id,text,vector FROM notes WHERE model IS ?",(model,)).fetchall()
        hits=[]
        for nid,text,vector in rows:
            if model:
                v=json.loads(vector); require(len(v)==len(q),"Embedding dimension mismatch")
                score=sum(a*b for a,b in zip(v,q))
            else:
                score=len(q & set(re.findall(r"\w+",text.casefold())))/max(1,len(q))
            if score>0: hits.append({"id":nid,"text":text,"score":round(score,6)})
        return sorted(hits,key=lambda x:(-x["score"],x["id"]))[:limit]
    def schedule(self,spec,interval,approved=False,now=None):
        require(approved is True,"Scheduling requires explicit approval")
        require(type(interval) is int and 3600<=interval<=31*86400,"Interval must be one hour to 31 days")
        require(isinstance(spec,dict) and set(spec)=={"task","route","calls"},"Invalid schedule spec")
        require(spec["route"] is None or route(spec["route"])[0]=="ollama","Cloud scheduling denied")
        require(type(spec["calls"]) is int and 1<=spec["calls"]<=30,"Invalid scheduled budget")
        packed=safe_text(json.dumps(spec,ensure_ascii=False)); require(len(packed)<=100000,"Schedule size limit")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            require(db.execute("SELECT count(*) FROM jobs").fetchone()[0]<100,"Project job limit")
            jid=uuid.uuid4().hex; db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?)",(jid,packed,interval,(time.time() if now is None else now)+interval,"ready",None))
        return jid
    def tick(self,runner,now=None):
        now=time.time() if now is None else now
        # Commit the claim before model work. A crashed or failed job never auto-retries.
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows=db.execute("SELECT id,spec,interval FROM jobs WHERE status='ready' AND due<=? ORDER BY due LIMIT 10",(now,)).fetchall()
            db.executemany("UPDATE jobs SET status='running' WHERE id=?",[(r[0],) for r in rows])
        results=[]
        for jid,spec,interval in rows:
            try:
                report=runner(json.loads(spec)); status="ready" if report["status"] in {"DEMO_COMPLETE","PENDING_APPROVAL"} else "failed"; result={"run":report["id"],"status":report["status"]}
            except Exception as exc:
                status="failed"; result={"error":type(exc).__name__}
            with self.db() as db: db.execute("UPDATE jobs SET status=?,due=?,result=? WHERE id=?",(status,now+interval,json.dumps(result),jid))
            results.append({"id":jid,**result})
        return results
    def jobs(self):
        with self.db() as db: return [{"id":r[0],"due":r[1],"status":r[2],"result":json.loads(r[3]) if r[3] else None} for r in db.execute("SELECT id,due,status,result FROM jobs ORDER BY due")]
    def cancel(self,jid):
        with self.db() as db:
            require(db.execute("UPDATE jobs SET status='cancelled' WHERE id=? AND status!='running'",(jid,)).rowcount==1,"Missing or running job")


def embed(model,text):
    require(isinstance(model,str) and 0<len(model)<=200,"Invalid local embedding model")
    r=request("127.0.0.1","/api/embed",{"model":model,"input":text,"truncate":False},local_port=11434)
    vectors=r.get("embeddings"); require(isinstance(vectors,list) and len(vectors)==1,"Invalid embedding response")
    v=vectors[0]; require(isinstance(v,list) and 1<=len(v)<=8192 and all(type(x) in (int,float) and math.isfinite(x) and abs(x)<=1e20 for x in v),"Invalid vector")
    length=math.sqrt(sum(x*x for x in v)); require(length>0,"Zero vector")
    return [x/length for x in v]


def dashboard(store,notes,destination):
    def esc(x): return html.escape(str(x),quote=True)
    rows=[]
    for run in store.summaries():
        gate=run.get("gate") or {}; rows.append((run["id"],run["status"],run["backend"],len(run["events"]),gate.get("score","—")))
    jobs=notes.jobs()
    def table(headers,items):
        return "<table><thead><tr>"+"".join("<th>"+esc(x)+"</th>" for x in headers)+"</tr></thead><tbody>"+"".join("<tr>"+"".join("<td>"+esc(x)+"</td>" for x in row)+"</tr>" for row in items)+"</tbody></table>"
    page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>AI Agent Factory</title><style>body{background:#101829;color:#e8efff;font:16px system-ui;margin:32px}h1{color:#79d8e2}table{border-collapse:collapse;width:100%;background:#19253a}th,td{padding:10px;text-align:left;border-bottom:1px solid #40516b}section{overflow:auto}small{color:#b2c4dc}</style><h1>AI Agent Factory | تمكين الرقمية</h1><small>Local read-only snapshot | لوحة متابعة محلية</small><section><h2>Runs | التشغيل</h2>'+table(["Run ID","Status","Backend","Role events","Gate score"],rows)+'</section><section><h2>Schedules | الجدولة</h2>'+table(["Job ID","Due (Unix UTC)","Status"],[(j["id"],j["due"],j["status"]) for j in jobs])+'</section><p>Demo scores are not model quality. No secrets, tasks, prompts, notes or draft contents are displayed.</p></html>'
    with Path(destination).open("x",encoding="utf-8") as f: f.write(page)
    return str(Path(destination).resolve())


def compare(store, first, second):
    a,b=store.load(first),store.load(second)
    from factory.architecture.state import validate_state
    for rid,state in ((first,a),(second,b)):
        if state.get("version")==3: validate_state(state,rid)
    require(digest(a.get("original_task",a["task"]))==digest(b.get("original_task",b["task"])),"Compare identical task contracts only")
    def metrics(state):
        events=state["events"]+state.get("specialist_metrics",[])
        return {"status":state["status"],"gate_score":(state.get("gate") or {}).get("score"),"calls":state["calls"]+state.get("specialist_calls",0),"sum_role_seconds":round(sum(e.get("seconds",0) for e in events),3),"backend":state["backend"]}
    return {"baseline":metrics(a),"candidate":metrics(b),"warning":"Gate scores are not independent factual or security assurance; demo and model scores are not comparable. Sum of role seconds is not wall time. No automatic adoption."}
