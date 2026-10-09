"""Five explicit subtitle guard diagnostics, excluded from benchmark timings."""
from bootstrap import prepare
prepare()
from pathlib import Path
import json
import tempfile
from babelander.settings import Settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.types import Cancellation,Mode

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'test-results/subtitle-quick'
benchmark=json.loads((OUT/'results.json').read_text(encoding='utf-8'))
assert benchmark['completed'] and benchmark['owned_model_stopped']
rows=[r for r in benchmark['translation'] if r['warning']][:5]
captured=[];diagnostics=[]
with tempfile.TemporaryDirectory(prefix='Babelander2-SRT-diagnostics-') as directory:
    settings=Settings(hotkeys={},model_path=str(ROOT/'test-results/asset-install/assets/downloads/Qwen_Qwen3-1.7B-Q4_K_M.gguf'),
        server_path=str(next((ROOT/'test-results/asset-install/assets').glob('llama-b10896-*/llama-server.exe'))))
    store=Store(directory);engine=Engine(settings,store,KeyVault(directory),directory)
    translate=engine.local.translate
    def observe(system,text):
        raw=translate(system,text);captured.append(raw);return raw
    engine.local.translate=observe
    try:
        for row in rows:
            captured.clear();result=engine.request(row['source'],Mode.DIALOG,Cancellation())
            diagnostics.append({'cue_id':row['cue_id'],'source':row['source'],'raw_model_output':captured[-1] if captured else None,
                'normalized_output':engine.chinese.convert(captured[-1]) if captured else None,'warning':result.warning})
    finally:
        owned=engine.local.process;engine.close();engine.join();store.close()
report={'scope':'First five rejected subtitle cues, explicit diagnostic reruns only. Excluded from original benchmark latency samples.',
    'extra_model_requests':len(diagnostics),'rows':diagnostics,'owned_model_stopped':owned is not None and owned.poll() is not None}
(OUT/'diagnostics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
