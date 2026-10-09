"""Cancel a real owned startup, then retry; no visible window or user screen."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
from pathlib import Path
import hashlib,json,tempfile,time
from PySide6.QtWidgets import QApplication
from babelander.settings import Settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.controller import Controller
from babelander.window import MainWindow

ROOT=Path(__file__).parent;APP=QApplication(['Preload cancellation background check'])
frozen={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').iterdir() if p.suffix in ('.py','.qss')}
def until(predicate,seconds=10):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:APP.processEvents();time.sleep(.005)
    return bool(predicate())
checks={};report={'checks':checks,'source_sha256':frozen,'foreground_control_calls':0,'user_screens_captured':False,
                 'paid_api':False,'real_model':True,'qt_platform':'offscreen','real_game_validated':False}
with tempfile.TemporaryDirectory(prefix='Babelander-preload-cancel-') as directory:
    assets=ROOT.parent/'recovery/test-assets';settings=Settings(hotkeys={},model_path=str(next((assets/'models').glob('*.gguf'))),server_path=str(assets/'runtime/llama-server.exe'))
    store=Store(directory);vault=KeyVault(directory);engine=Engine(settings,store,vault,directory)
    controller=Controller(engine,store,settings);window=MainWindow(controller,store,settings,vault,directory);processes=[]
    try:
        window.prepare_model()
        assert until(lambda:engine.local.process is not None),'startup never spawned'
        process=engine.local.process;processes.append(process)
        checks['cancelled_during_owned_startup']=window.prepare_cancel.isEnabled() and process.poll() is None
        identifier=controller.preparation_id;at=time.perf_counter();window.cancel_model_preparation()
        assert until(lambda:process.poll() is not None and not engine.pending),'cancelled startup did not stop'
        report['cancel_to_owned_process_exit_ms']=round((time.perf_counter()-at)*1000,2)
        window.preparation_finished(identifier,{'ready':True})
        checks['cancelled_completion_not_ready']='取消' in window.model_status.text() and '已就緒' not in window.model_status.text()
        checks['cancelled_work_accounted']=engine.active_local_calls==0 and not engine.pending
        window.prepare_model();assert until(lambda:window.prepare_button.isEnabled(),65)
        checks['retry_preload_ready']='已就緒' in window.model_status.text()
        processes.append(engine.local.process)
        checks['no_preload_text_persistence']=all(store.db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0 for table in ('cache','history','usage'))
    except Exception as error:report['error']={'type':type(error).__name__,'message':str(error)}
    finally:
        window.close();controller.join();store.close();APP.processEvents()
        report['owned_models_stopped']=all(process is None or process.poll() is not None for process in processes)
        report['workers_stopped']=all(not thread.is_alive() for queue in engine.queues.values() for thread in queue.threads)
report['source_unchanged']=all(hashlib.sha256((ROOT/'babelander'/name).read_bytes()).hexdigest()==sha for name,sha in frozen.items())
report['passed']=len(checks)==5 and all(checks.values()) and 'error' not in report and report['source_unchanged'] and report['owned_models_stopped'] and report['workers_stopped']
(ROOT/'test-results/preload-cancel-real-a17.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'},ensure_ascii=False,indent=2));raise SystemExit(not report['passed'])
