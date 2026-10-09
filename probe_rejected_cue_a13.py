"""Inspect one real guard rejection and owned PID memory; no UI/OCR/API."""
from pathlib import Path
from dataclasses import asdict
import json,subprocess,tempfile,time
from unittest.mock import patch
from babelander.engine import Engine
from babelander.settings import Settings
from babelander.security import KeyVault
from babelander.storage import Store
from babelander.types import Mode,Cancellation
ROOT=Path(__file__).parent
full=json.loads((ROOT/'test-results/replay-a13-mixed-100-t4/results.json').read_text(encoding='utf8'))
failed=next(t for p in full['phases'] for r in p['results'] for t in r['translations'] if t['warning'])
assets=ROOT/'test-results/asset-install/assets'
report={'scope':'Separate single-cue diagnostic, real local model. WDDM PID-specific memory snapshot, not full-replay peak or physical residency.',
        'source':failed['source'],'raw_outputs':[]}
with tempfile.TemporaryDirectory(prefix='Babelander2-guard-diagnostic-') as directory:
    settings=Settings(hotkeys={},model_path=str(assets/'downloads/Qwen_Qwen3-1.7B-Q4_K_M.gguf'),server_path=str(next(assets.glob('llama-b10896-*/llama-server.exe'))))
    store=Store(directory);engine=Engine(settings,store,KeyVault(directory),directory);owned=None
    try:
        engine.acquire_client('guard-diagnostic')
        engine.request('The observer carries 3 notebooks.',Mode.DIALOG,Cancellation())
        owned=engine.local.process;original=engine.local.translate
        def record(system,text):
            output=original(system,text);report['raw_outputs'].append(output);return output
        with patch.object(engine.local,'translate',side_effect=record):
            store.clear_cache();report['result']=asdict(engine.request(failed['source'],Mode.DIALOG,Cancellation()))
        time.sleep(1.1)
        command="Get-CimInstance -ClassName Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory | Where-Object { $_.Name -like 'pid_"+str(owned.pid)+"_*' } | Select-Object Name,DedicatedUsage,SharedUsage | ConvertTo-Json -Compress"
        query=subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,text=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
        if query.returncode==0 and query.stdout.strip():
            rows=json.loads(query.stdout);rows=rows if isinstance(rows,list) else [rows]
            report['owned_gpu_process_memory']={'pid':owned.pid,'counter':'WDDM GPUProcessMemory',
                'dedicated_mib':round(sum(int(r['DedicatedUsage']) for r in rows)/1048576,2),
                'shared_mib':round(sum(int(r['SharedUsage']) for r in rows)/1048576,2),'adapter_rows':rows}
        else:report['owned_gpu_process_memory']=None
    finally:engine.close();engine.join();store.close()
    report['own_model_stopped']=owned is not None and owned.poll() is not None
    report['workers_stopped']=not engine.release_worker.is_alive() and all(not t.is_alive() for q in engine.queues.values() for t in q.threads)
(ROOT/'test-results/guard-diagnostic-a13.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=True))
