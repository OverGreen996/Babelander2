"""Three explicit diagnostic reruns, excluded from the 100-case timing data."""
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

root=Path(__file__).resolve().parent
out=root/'test-results/english-100'
benchmark=json.loads((out/'results.json').read_text(encoding='utf-8'))
rejected=[row for row in benchmark['model_pass'] if row['warning']]
rows=[]
with tempfile.TemporaryDirectory(prefix='Babelander2-English100-diagnostic-') as directory:
    settings=Settings(hotkeys={},model_path=str(root/'test-results/asset-install/assets/downloads/Qwen_Qwen3-1.7B-Q4_K_M.gguf'),
                      server_path=str(next((root/'test-results/asset-install/assets').glob('llama-b10896-*/llama-server.exe'))))
    store=Store(directory);engine=Engine(settings,store,KeyVault(directory),directory)
    translate=engine.local.translate
    captured=[]
    def observe(system,text):
        raw=translate(system,text);captured.append(raw);return raw
    engine.local.translate=observe
    owned=None
    try:
        for row in rejected:
            result=engine.request(row['source'],Mode.DIALOG,Cancellation())
            raw=captured[-1]
            rows.append({'id':row['id'],'source':row['source'],'raw_model_output':raw,
                         'normalized_output':engine.chinese.convert(raw),'warning':result.warning})
    finally:
        owned=engine.local.process;engine.close();engine.join();store.close()
report={'scope':'Three explicit local diagnostic reruns only; excluded from all original timing averages.',
        'extra_model_requests':len(rows),'rows':rows,'owned_model_stopped':owned is not None and owned.poll() is not None}
(out/'diagnostics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
