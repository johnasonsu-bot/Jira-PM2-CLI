"""Start/query only the Forge process with PM2; never persist ambient secrets."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action', choices=['start','status'])
    args=parser.parse_args()
    pm2=shutil.which('pm2')
    if not pm2:
        candidate=Path.home()/'.npm-global/bin/pm2'
        if candidate.is_file():
            pm2=str(candidate)
    if not pm2:
        raise SystemExit('PM2 unavailable. Run forge-devops-server directly, or install npm package pm2.')
    clean={k:os.environ[k] for k in ('PATH','HOME','USER','LANG','TMPDIR') if k in os.environ}
    def run(argv):
        result=subprocess.run([pm2,*argv],env=clean,capture_output=True,text=True,timeout=30)
        if result.returncode:
            raise SystemExit('PM2 operation failed; use forge-devops-server for diagnostics.')
        return result.stdout
    # The first PM2 invocation may print a daemon-start banner before its result.
    # Initialize separately so jlist remains a machine-readable JSON response.
    run(['ping'])
    items=json.loads(run(['jlist']))
    own=[p for p in items if p.get('name')=='forge-devops']
    entry=Path(sys.executable).parent/'forge-devops-server'
    if args.action=='start':
        if not entry.is_file():
            raise SystemExit('Run manage.py with the Python venv used to install Forge.')
        if own:
            expected=str(entry)
            if own[0].get('pm2_env',{}).get('pm_exec_path')!=expected:
                raise SystemExit('PM2 name forge-devops belongs to a different entrypoint; not modified.')
            if own[0].get('pm2_env',{}).get('status')!='online':
                run(['restart',str(own[0]['pm_id'])])
        else:
            run(['start',str(entry),'--name','forge-devops','--interpreter',sys.executable,'--','--port','8766'])
        own=[p for p in json.loads(run(['jlist'])) if p.get('name')=='forge-devops']
    print(json.dumps([{'name':p['name'],'pid':p.get('pid'),'status':p.get('pm2_env',{}).get('status'),
                      'restarts':p.get('pm2_env',{}).get('restart_time'),'memory':p.get('monit',{}).get('memory')} for p in own],indent=2))

if __name__=='__main__':
    main()
