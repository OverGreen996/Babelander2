"""Serial background acceptance for a23; no paid APIs or desktop interaction."""
import os,json,subprocess,sys,time,hashlib,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'test-results/a23-acceptance';OUT.mkdir(parents=True,exist_ok=True)
env=os.environ.copy();env.update(PYTHONIOENCODING='utf-8',QT_QPA_PLATFORM='offscreen')
source={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}
stages=[
 ('units',['supertest.py','--phase','units']),
 ('ocr-edges',['probe_chat_ocr_edges.py']),
 ('weak-flash',['probe_chat_gate_flash.py','--production-only','--out','test-results/a23-weak-flash.json']),
 ('chat-events',['probe_chat_events.py','--out','test-results/a23-chat-events']),
 ('modes',['supertest_modes.py','--out','test-results/a23-modes']),
 ('clean',['probe_chat_poll.py','--child','--scan-ms','100','--out','chat-clean-a23']),
 ('animated-repeat',['probe_chat_poll.py','--child','--scan-ms','100','--animated-chat','--round','2','--out','chat-fixed-a23-final']),
 ('animated-four-threads',['probe_chat_poll.py','--child','--scan-ms','100','--animated-chat','--ocr-threads','4','--round','3','--out','chat-fixed-a23-final']),
 ('package',['supertest.py','--phase','package']),
 ('soak',['supertest.py','--phase','soak','--seconds','300'])]
parser=argparse.ArgumentParser();parser.add_argument('--resume-from',choices=[s[0] for s in stages]);options=parser.parse_args()
rows=[];prior_failed_attempts=[]
if options.resume_from:
 previous=json.loads((OUT/'runner.json').read_text(encoding='utf8'))
 assert previous['source_sha256']==source,'Application changed; rerun acceptance from start'
 offset=[s[0] for s in stages].index(options.resume_from)
 rows=previous['stages'][:offset]
 assert all(r['returncode']==0 for r in rows)
 prior_failed_attempts=previous.get('prior_failed_attempts',[])+[r for r in previous['stages'][offset:] if r['returncode']]
 stages=stages[offset:]
for name,args in stages:
 print('START '+name,flush=True);start=time.perf_counter()
 with (OUT/(name+'.log')).open('w',encoding='utf8') as log:
  child=subprocess.run([sys.executable,*args],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                       timeout=900,creationflags=subprocess.CREATE_NO_WINDOW)
 rows.append({'name':name,'returncode':child.returncode,'seconds':time.perf_counter()-start})
 report={'stages':rows,'prior_failed_attempts':prior_failed_attempts,'source_sha256':source,'source_unchanged':source=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')},'real_desktop_capture':False,'foreground_control_calls':0,'paid_api_calls':0}
 report['passed']=all(r['returncode']==0 for r in rows) and report['source_unchanged']
 (OUT/'runner.json').write_text(json.dumps(report,indent=2),encoding='utf8')
 print(json.dumps(rows[-1]),flush=True)
 if child.returncode:raise SystemExit(child.returncode)
