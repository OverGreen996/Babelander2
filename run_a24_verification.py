"""Serial background regression/real-engine/package checks for OCR changes."""
import os,json,subprocess,sys,time,hashlib,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'test-results/a24-acceptance';OUT.mkdir(parents=True,exist_ok=True)
env=os.environ.copy();env.update(PYTHONIOENCODING='utf-8',QT_QPA_PLATFORM='offscreen')
source={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}
units=('verify','verify_assets','verify_pipeline','verify_layout','verify_equipment','verify_subtitle_trigger',
       'verify_replay','verify_equipment_recovery','verify_window_focus','verify_preload','verify_quest',
       'verify_chat','verify_chat_ocr','verify_super_regressions','verify_ocr_cpu')
stages=[(name,[name+'.py']) for name in units]+[
    ('ocr-edges',['probe_chat_ocr_edges.py','--out','test-results/a24-acceptance/ocr-edges.json']),
    ('weak-flash',['probe_chat_gate_flash.py','--production-only','--out','test-results/a24-acceptance/weak-flash.json']),
    ('chat-events',['probe_chat_events.py','--out','test-results/a24-acceptance/chat-events']),
    ('modes',['supertest_modes.py','--out','test-results/a24-acceptance/modes']),
    ('clean',['probe_chat_poll.py','--child','--scan-ms','100','--out','a24-acceptance/clean']),
    ('package',['supertest.py','--phase','package'])]
rows=[]
for name,args in stages:
    print('START '+name,flush=True);at=time.perf_counter()
    with (OUT/(name+'.log')).open('w',encoding='utf8') as log:
        child=subprocess.run([sys.executable,*args],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                             timeout=900,creationflags=subprocess.CREATE_NO_WINDOW)
    contents=(OUT/(name+'.log')).read_text(encoding='utf8',errors='replace')
    count=re.search(r'Ran (\d+) tests?',contents)
    rows.append({'name':name,'returncode':child.returncode,'seconds':time.perf_counter()-at,
                 'tests_run':int(count[1]) if count else None})
    report={'stages':rows,'source_sha256':source,
        'source_unchanged':source=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')},
        'real_desktop_capture':False,'foreground_control_calls':0,'paid_api_calls':0}
    report['passed']=all(r['returncode']==0 for r in rows) and report['source_unchanged']
    (OUT/'runner.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(rows[-1]),flush=True)
    if child.returncode:raise SystemExit(child.returncode)
