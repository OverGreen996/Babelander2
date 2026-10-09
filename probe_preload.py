"""Five interleaved cold/preloaded text pairs, true local CUDA, Qt offscreen."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
from pathlib import Path
import hashlib,json,tempfile,time,re,subprocess,shutil
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from babelander.settings import Settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.controller import Controller
from babelander.window import MainWindow
from babelander.types import Mode,Cancellation

ROOT=Path(__file__).parent
APP=QApplication(['Preload background diagnostic'])
for name in ('segoeui.ttf','msjh.ttc'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
APP.setStyle('Fusion');APP.setStyleSheet((ROOT/'babelander/theme.qss').read_text(encoding='utf8'))
assets=ROOT.parent/'recovery/test-assets'
frozen={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').iterdir() if p.suffix in ('.py','.qss')}
text='Before activating the beacon, gather everyone inside the shelter.'
rows=[];checks={};workers=[];processes=[]

def until(predicate,seconds=65):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:APP.processEvents();time.sleep(.005)
    return bool(predicate())

def counts(store):return {table:store.db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('cache','history','usage')}

def run(kind,pair):
    with tempfile.TemporaryDirectory(prefix='Babelander-preload-probe-') as directory:
        settings=Settings(hotkeys={},model_path=str(next((assets/'models').glob('*.gguf'))),server_path=str(assets/'runtime/llama-server.exe'))
        store=Store(directory);vault=KeyVault(directory);engine=Engine(settings,store,vault,directory)
        controller=Controller(engine,store,settings);window=MainWindow(controller,store,settings,vault,directory)
        record={'pair':pair,'condition':kind};process=None
        try:
            if kind=='preloaded':
                before=counts(store);at=time.perf_counter();window.prepare_model()
                record['click_return_ms']=round((time.perf_counter()-at)*1000,3)
                assert until(lambda:window.prepare_button.isEnabled()),'preload timed out'
                assert '已就緒' in window.model_status.text(),window.model_status.text()
                record['preload_ready_ms']=round((time.perf_counter()-at)*1000,2)
                record['preload_db_unchanged']=before==counts(store)
                record['ocr_remained_lazy']=controller.ocr.engine is None
                process=engine.local.process
                assert process and process.poll() is None
                if pair==0:
                    window.navigation.button(8).setChecked(True);window.stack.setCurrentIndex(8)
                    window.resize(1150,900);window.show();APP.processEvents()
                    window.grab().save(str(ROOT/'assets/preload-model-a17.png'))
                    window.hide()
                    window.prepare_model();assert until(lambda:window.prepare_button.isEnabled())
                    checks['repeat_health_check_same_model']=engine.local.process is process
            at=time.perf_counter();result=engine.request(text,Mode.DIALOG,Cancellation())
            record['first_text_request_ms']=round((time.perf_counter()-at)*1000,2)
            record.update(model_ms=round(result.model_ms,2),backend_state=result.backend_state,cache_hit=result.cache_hit,
                          target=result.target,warning=result.warning)
            assert not result.cache_hit and result.target and not result.warning,(result.target,result.warning,result.cache_hit)
            if kind=='preloaded':record['same_process_for_first_translation']=engine.local.process is process
            process=engine.local.process
            gpu=subprocess.run([shutil.which('nvidia-smi') or 'C:/Windows/System32/nvidia-smi.exe',
                                '--query-compute-apps=pid','--format=csv,noheader,nounits'],capture_output=True,text=True,
                               creationflags=subprocess.CREATE_NO_WINDOW,timeout=10)
            record['cuda_offload_confirmed']=gpu.returncode==0 and str(process.pid) in {line.strip() for line in gpu.stdout.splitlines()}
            assert record['cuda_offload_confirmed'],'Owned llama-server was not found in NVIDIA compute-process query'
        finally:
            window.close();controller.join();store.close();APP.processEvents()
            processes.append(process is None or process.poll() is not None)
            workers.append(all(not thread.is_alive() for queue in engine.queues.values() for thread in queue.threads))
        return record

error=None
try:
    for pair in range(5):
        for kind in (('cold','preloaded') if pair%2==0 else ('preloaded','cold')):
            rows.append(run(kind,pair))
            print(json.dumps({k:v for k,v in rows[-1].items() if k not in ('target','warning')},ensure_ascii=False),flush=True)
    prepared=[row for row in rows if row['condition']=='preloaded'];cold=[row for row in rows if row['condition']=='cold']
    checks.update(no_paid_api=True,preload_no_db_writes=all(row['preload_db_unchanged'] for row in prepared),
                  ocr_lazy=all(row['ocr_remained_lazy'] for row in prepared),preload_reuses_model=all(row['same_process_for_first_translation'] for row in prepared),
                  preloaded_requests_warm=all(row['backend_state']=='warm' for row in prepared),
                  baseline_requests_cold=all(row['backend_state']=='cold' for row in cold),
                  no_cache_hits=all(not row['cache_hit'] for row in rows),all_targets_valid=all(row['target'] and not row['warning'] for row in rows))
except Exception as failure:error={'type':type(failure).__name__,'message':str(failure)}
summary={kind:{'samples':len(sample),'mean_ms':round(float(np.mean([r['first_text_request_ms'] for r in sample])),2),
               'p95_ms':round(float(np.percentile([r['first_text_request_ms'] for r in sample],95)),2)}
         for kind in ('cold','preloaded') if (sample:=[row for row in rows if row['condition']==kind])}
report={'passed':error is None and len(rows)==10 and all(checks.values()) and all(workers) and all(processes),
        'error':error,'checks':checks,'summary':summary,'rows':rows,'source_sha256':frozen,
        'source_unchanged':all(hashlib.sha256((ROOT/'babelander'/name).read_bytes()).hexdigest()==sha for name,sha in frozen.items()),
        'owned_models_stopped':all(processes),'workers_stopped':all(workers),'qt_platform':'offscreen','real_cuda':True,
        'scope':'First uncached Engine text request only. Five small paired diagnostics; no OCR/capture/overlay latency or game benchmark.',
        'real_game_validated':False,'user_screens_captured':False,'foreground_control_calls':0,'paid_api':False}
report['passed']=report['passed'] and report['source_unchanged']
(ROOT/'test-results/preload-real-a17.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k not in ('source_sha256','rows')},ensure_ascii=False,indent=2))
raise SystemExit(not report['passed'])
