import argparse
import json
import sys
from pathlib import Path
from .engine import Engine, Demo, Ollama, FactoryError, read_json

def main():
    p=argparse.ArgumentParser(description='AI Agent Factory — local draft and review runner')
    p.add_argument('--runs',type=Path,default=Path('.factory-runs'))
    p.add_argument('--backend',choices=['demo','ollama'],default='demo')
    p.add_argument('--model',help='Installed local Ollama model name; no automatic download')
    p.add_argument('--timeout',type=int,default=120,help='Socket timeout in seconds (1–600)')
    s=p.add_subparsers(dest='command',required=True)
    run=s.add_parser('run'); run.add_argument('task',type=Path); run.add_argument('--revisions',type=int,choices=range(3),default=2)
    resume=s.add_parser('resume'); resume.add_argument('id')
    show=s.add_parser('show'); show.add_argument('id')
    a=p.parse_args()
    if a.backend=='ollama' and not a.model: p.error('--model is required for Ollama')
    if not 1<=a.timeout<=600: p.error('timeout must be 1–600 seconds')
    try:
        backend=Demo() if a.backend=='demo' else Ollama(a.model,a.timeout)
        engine=Engine(a.runs,backend)
        if a.command=='show':
            result=read_json(engine.folder(a.id)/'state.json',2_000_000)
        else:
            run_id=engine.create(read_json(a.task),a.revisions) if a.command=='run' else a.id
            print('Run ID: '+run_id,file=sys.stderr)
            result=engine.execute(run_id)
        print(json.dumps(result,ensure_ascii=True,indent=2))
        return 0 if a.command=='show' or result['status']=='REVIEWED_DRAFT' else 2
    except (FactoryError,OSError,ValueError,KeyError,TypeError) as e:
        print('Error: '+str(e),file=sys.stderr)
        return 1
