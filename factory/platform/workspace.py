"""Explicit, digest-bound staging. Models cannot execute commands."""
import hashlib
import json
import re
import os
import stat
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path, PurePosixPath
from factory.engine import require

from factory.architecture.contracts import SECRET

def safe_text(text):
    require(isinstance(text,str) and not SECRET.search(text),"Potential secret detected; action denied")
    return text

def digest(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def validate_files(plan):
    require(isinstance(plan,dict) and set(plan)=={"files"} and isinstance(plan["files"],list) and 1<=len(plan["files"])<=32,"Invalid staged file plan")
    result=[]; seen=set(); size=0
    for item in plan["files"]:
        require(isinstance(item,dict) and set(item)=={"path","content"},"File must contain path and content")
        name=item["path"]; require(isinstance(name,str) and len(name)<=200 and re.fullmatch(r"[A-Za-z0-9_./-]+",name),"Invalid file path")
        parts=name.split("/"); require(all(p not in {"", ".", ".."} and not p.startswith(".") and p.rstrip(". ")==p and p.split(".")[0].upper() not in {"CON","PRN","AUX","NUL",*[f"COM{i}" for i in range(1,10)],*[f"LPT{i}" for i in range(1,10)]} for p in parts),"Unsafe path")
        path=PurePosixPath(name); require(path.suffix.lower() in {".py",".php",".js",".css",".html",".json",".md",".txt"},"File type denied")
        key=name.casefold(); require(key not in seen,"Duplicate path"); seen.add(key)
        content=safe_text(item["content"]); size+=len(content.encode()); require(size<=250000,"Workspace byte cap exceeded")
        result.append((path,content))
    return result

def stage(plan,destination,approval):
    files=validate_files(plan); require(digest(plan)==approval,"Approval digest mismatch")
    dest=Path(destination); dest.mkdir(mode=0o700,parents=False,exist_ok=False)
    try:
        for path,content in files:
            target=dest.joinpath(*path.parts); target.parent.mkdir(parents=True,exist_ok=True)
            with target.open("x",encoding="utf-8") as f: f.write(content)
    except Exception:
        shutil.rmtree(dest); raise
    return str(dest.resolve())

def docker_command(workspace,image,name,suite="python"):
    path=Path(workspace).resolve(strict=True)
    require(path.is_dir() and not any(c in str(path) for c in ',\r\n"'),"Unsafe Docker mount path")
    require(isinstance(image,str) and re.fullmatch(r"[a-z0-9][a-z0-9./:_-]*@sha256:[a-f0-9]{64}",image),"Use an already installed digest-pinned Linux Python image")
    require(suite in {"python","php-lint"},"Unsupported sandbox suite")
    if suite=="python": command=["python","-m","unittest","discover","-s","tests","-v"]
    else:
        names=["./"+f.relative_to(path).as_posix() for f in sorted(path.rglob("*.php"))]
        require(bool(names),"No PHP files to lint")
        command=["php","-l",*names]
    return ["docker","run","--rm","--name",name,"--pull=never","--network=none","--read-only","--cap-drop=ALL","--security-opt=no-new-privileges","--user=65534:65534","--memory=256m","--cpus=1","--pids-limit=64","--tmpfs","/tmp:rw,noexec,nosuid,size=32m","--log-driver=none","--mount",f"type=bind,source={path},target=/work,readonly","--workdir=/work","-e","PYTHONDONTWRITEBYTECODE=1",image,*command]

def snapshot(workspace,destination):
    source=Path(workspace); require(source.is_dir() and not source.is_symlink(),"Invalid staging directory")
    files=[]; size=0; dirs=0
    for root, subdirs, names in os.walk(source,followlinks=False):
        dirs+=len(subdirs); require(dirs<=64,"Directory budget exceeded")
        for n in subdirs:
            f=Path(root)/n; require(not f.is_symlink() and not n.startswith("."),"Unsafe staging directory")
        for n in names:
            f=Path(root)/n; info=f.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and not n.startswith("."),"Unsafe staging file")
            require(len(files)<32 and info.st_size<=250000-size,"Workspace size limit")
            with f.open("rb") as reader: raw=reader.read(250001-size)
            size+=len(raw); require(size<=250000,"Workspace size limit")
            files.append({"path":f.relative_to(source).as_posix(),"content":raw.decode("utf-8")})
    plan={"files":files}; stage(plan,destination,digest(plan))
    # The snapshot is inside a private temporary parent; mount root must be readable by nobody.
    Path(destination).chmod(0o755)
    for f in Path(destination).rglob("*"): f.chmod(0o755 if f.is_dir() else 0o644)


def sandbox_test(workspace,image,approved=False,suite="python"):
    require(approved is True,"Explicit Docker execution approval required")
    with tempfile.TemporaryDirectory() as directory:
        clean=Path(directory)/"workspace"; snapshot(workspace,clean)
        return _sandbox(clean,image,suite)


def _sandbox(workspace,image,suite):
    name="agent-factory-"+uuid.uuid4().hex
    command=docker_command(workspace,image,name,suite)
    # Use a sanitized snapshot, not a mount of a live project.
    # Keep captured output bounded via a pipe and stop if it exceeds the limit.
    import threading
    with tempfile.TemporaryFile() as sink:
        proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
        oversized=[]
        def drain():
            remaining=100_000
            while True:
                chunk=proc.stdout.read(4096)
                if not chunk: break
                sink.write(chunk[:remaining]); remaining-=min(remaining,len(chunk))
                if remaining==0:
                    oversized.append(True); proc.kill(); break
        reader=threading.Thread(target=drain,daemon=True); reader.start()
        try:
            code=proc.wait(timeout=120); reader.join(timeout=5)
            require(not reader.is_alive() and not oversized,"Sandbox output limit exceeded")
            sink.seek(0); return {"exit_code":code,"output":sink.read().decode(errors="replace")}
        finally:
            if proc.poll() is None: proc.kill(); proc.wait()
            proc.stdout.close()
            reader.join(timeout=5)
            subprocess.run(["docker","rm","-f",name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,check=False)
