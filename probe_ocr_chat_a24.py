"""Serial ABBA production OCR/chat validation against immutable alpha23 code."""
import os,sys,json,subprocess,hashlib,argparse
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'test-results/ocr-chat-a24'
OUT.mkdir(parents=True,exist_ok=True)
BASELINE='53e9292e104ea05bfe6f66cb10757e6503dd6c2b'
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
runs=[]
parser=argparse.ArgumentParser();parser.add_argument('--summarize',action='store_true');args=parser.parse_args()
for round,baseline in enumerate((True,False,False,True)):
    print(f'START animated round={round} baseline={baseline}',flush=True)
    command=[sys.executable,'probe_chat_poll.py','--child','--scan-ms','100','--round',str(round),
             '--animated-chat','--out','ocr-chat-a24']
    if baseline:command+=['--baseline-ref',BASELINE]
    result=None if args.summarize else subprocess.run(command,cwd=ROOT,env=env,timeout=250,creationflags=subprocess.CREATE_NO_WINDOW)
    row=json.loads((OUT/f'{round}-100.json').read_text(encoding='utf8'))
    row['returncode']=int(not row['passed']) if result is None else result.returncode;runs.append(row)

def stats(values):
    return {'n':len(values),'mean_ms':float(np.mean(values)),'p50_ms':float(np.median(values)),
            'p95_ms':float(np.percentile(values,95)),'max_ms':max(values)}

summary={}
for label,baseline in (('baseline',True),('candidate',False)):
    group=[r for r in runs if bool(r['baseline_ref'])==baseline]
    values=[v['shown_to_qt_ms'] for r in group for v in r['results'] if v['shown_to_qt_ms'] is not None]
    summary[label]={'complete_translation':stats(values),
        'ocr':stats([v['ms'] for r in group for v in r['ocr']]),
        'within700':sum(v<=700 for v in values),'captures':sum(r['captures'] for r in group),
        'cpu_core_seconds':sum(r['cpu_core_seconds'] for r in group),
        'cpu_core_seconds_per_second':sum(r['cpu_core_seconds'] for r in group)/sum(r['duration_seconds'] for r in group),
        'private_max_mib':max(r['private_max_mib'] for r in group),
        'recognition_rows_inferred':sum(v['reuse'].get('inferred',0) for r in group for v in r['ocr']),
        'cached_context_rows_reinferred':sum(v['reuse'].get('context_crops',0) for r in group for v in r['ocr']),
        'per_run':[{'round':r['round'],'complete_translation':stats([v['shown_to_qt_ms'] for v in r['results'] if v['shown_to_qt_ms'] is not None]),
                    'ocr':stats([v['ms'] for v in r['ocr']])} for r in group]}

report={'scope':'Same 100 messages, 900ms exposures, five animated backgrounds, isolated ABBA processes. Warm real CPU OCR / CUDA Qwen / offscreen Qt. App-process CPU excludes llama-server. No foreground or desktop capture.',
    'baseline_commit':BASELINE,'summary':summary,'runs':runs,
    'same_frames':all(r['animation_hashes']==runs[0]['animation_hashes'] for r in runs),
    'same_source_messages':all([v['source'] for v in r['results']]==[v['source'] for v in runs[0]['results']] for r in runs),
    'foreground_control_calls':0,'real_desktop_capture':False}
report['same_event_sequence']=all([v['index'] for v in r['results']]==list(range(100)) for r in runs)
# Live capture can observe different animation phases after a speed change.
# Record literal OCR variation, but verify OCR equivalence separately by feeding
# precisely the same pixels/sequence in probe_ocr_fixed_a24.py.
fixed_path=ROOT/'test-results/ocr-fixed-a24.json'
fixed=json.loads(fixed_path.read_text(encoding='utf8')) if fixed_path.exists() else {}
report['fixed_frame_equivalence_passed']=bool(fixed.get('passed'))
report['functional_passed']=all(r['passed'] and r['returncode']==0 for r in runs) and report['same_frames'] and report['same_event_sequence'] and report['fixed_frame_equivalence_passed']
report['speed_gate_passed']=all(summary['candidate'][stage]['p95_ms']<summary['baseline'][stage]['p95_ms'] for stage in ('ocr','complete_translation'))
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='runs'},ensure_ascii=False),flush=True)
raise SystemExit(not(report['functional_passed'] and report['speed_gate_passed']))
