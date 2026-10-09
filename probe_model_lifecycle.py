"""Real model crash/restart and idle VRAM release on our owned process."""
from pathlib import Path
from dataclasses import replace
import json
import tempfile
from babelander.settings import load_settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.types import Mode,Cancellation
root=Path(__file__).resolve().parent;checks={};pids=[]
with tempfile.TemporaryDirectory(prefix='Babelander2-restart-') as directory:
    settings=load_settings(directory);store=Store(directory);engine=Engine(settings,store,KeyVault(directory),directory)
    try:
        first=engine.request('A quiet morning at the ancient gate.',Mode.SCREEN,Cancellation())
        process=engine.local.process;pids.append(process.pid);log=engine.local.log
        # Only the child just started by this test, never arbitrary llama PIDs.
        process.terminate();process.wait(5)
        store.clear_cache()
        second=engine.request('A quiet morning at the ancient gate.',Mode.SCREEN,Cancellation())
        process2=engine.local.process;pids.append(process2.pid)
        checks['owned_crash_restarts']=process2.pid!=process.pid and not first.warning and not second.warning
        checks['crashed_log_handle_closed']=log.closed
        engine.last_local_request-=settings.idle_unload_seconds+1
        checks['idle_unloads_real_model']=engine.maybe_unload() and process2.poll() is not None and engine.local.process is None
        third=engine.request('An evening near the northern tower.',Mode.SCREEN,Cancellation())
        process3=engine.local.process;pids.append(process3.pid)
        checks['next_request_reloads']=process3.pid!=process2.pid and not third.warning
        engine.reconfigure(replace(settings,font_size=32,scan_ms=1200))
        checks['presentation_settings_keep_loaded_process']=engine.local.process is process3 and process3.poll() is None
        engine.unload_local()
        checks['manual_unload_stops_owned_model']=process3.poll() is not None and engine.local.process is None
    finally:
        engine.close();engine.join();store.close()
        checks['workers_stopped']=all(not t.is_alive() for q in engine.queues.values() for t in q.threads)
report={'passed':all(checks.values()),'checks':checks,'owned_process_ids':pids,'scope':'Real local CUDA, distinct owned child per startup; clock advanced by setting last request time to exercise automatic idle path without a five-minute sleep.'}
(root/'test-results/model-lifecycle.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2));raise SystemExit(not report['passed'])
