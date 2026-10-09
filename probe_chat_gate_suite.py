"""Balanced independent animated chat A/B; serial actual local model runs."""
import os,sys,json,subprocess,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'test-results/chat-gate-live'
OUT.mkdir(parents=True,exist_ok=True);runs=[];env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
candidate=hashlib.sha256((ROOT/'chat_gate_experiment.py').read_bytes()).hexdigest()
for i,enabled in enumerate((False,True,True,False)):
    print(f'START animated round {i} candidate={enabled}',flush=True)
    command=[sys.executable,'probe_chat_poll.py','--child','--scan-ms','100','--round',str(i),'--animated-chat','--out','chat-gate-live']
    if enabled:command.append('--experimental-gate')
    result=subprocess.run(command,cwd=ROOT,env=env,timeout=250,creationflags=subprocess.CREATE_NO_WINDOW)
    row=json.loads((OUT/f'{i}-100.json').read_text(encoding='utf8'));row['returncode']=result.returncode;runs.append(row)
summary={}
for enabled in (False,True):
    selected=[r for r in runs if r['experimental_gate']==enabled]
    v=[r['shown_to_qt_ms'] for run in selected for r in run['results'] if r['shown_to_qt_ms'] is not None]
    summary[str(enabled)]={'n':len(v),'mean_ms':float(np.mean(v)),'p95_ms':float(np.percentile(v,95)),
        'max_ms':max(v),'within700':sum(x<=700 for x in v),'ocr_calls':sum(len(r['ocr']) for r in selected),
        'cpu_core_seconds':sum(r['cpu_core_seconds'] for r in selected)}
report={'runs':runs,'summary':summary,'candidate_sha256':candidate,
    'candidate_unchanged':candidate==hashlib.sha256((ROOT/'chat_gate_experiment.py').read_bytes()).hexdigest(),
    'same_animation_frames':all(r['animation_hashes']==runs[0]['animation_hashes'] for r in runs),
    'real_desktop_capture':False,'foreground_control_calls':0,'real_local_model':True}
report['functional_passed']=all(r['passed'] and r['returncode']==0 for r in runs) and report['candidate_unchanged'] and report['same_animation_frames']
report['speed_gate_passed']=summary['True']['within700']>=summary['False']['within700'] and summary['True']['p95_ms']<=summary['False']['p95_ms']
(OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='runs'}),flush=True)
raise SystemExit(not report['functional_passed'] or not report['speed_gate_passed'])
