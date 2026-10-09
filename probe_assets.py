"""Real upstream resume+full SHA verification using existing prefixes."""
from pathlib import Path
import json
import shutil
import subprocess
import time
from babelander.assets import ASSETS,download,install
from babelander.types import Cancellation
root=Path(__file__).resolve().parent
testroot=root/'test-results/asset-install';cache=testroot/'assets/downloads';cache.mkdir(parents=True,exist_ok=True)
reference=root.parent/'recovery/test-assets'
rows=[];token=Cancellation()
for asset in ASSETS:
    source=reference/('models' if asset.name.endswith('.gguf') else 'downloads')/asset.name
    partial=cache/(asset.name+'.part');final=cache/asset.name
    if not final.exists():
        with source.open('rb') as src,partial.open('wb') as dst:
            remaining=asset.size-65536
            while remaining:
                block=src.read(min(1024*1024,remaining));dst.write(block);remaining-=len(block)
    at=time.perf_counter();download(asset,cache,token)
    rows.append({'name':asset.name,'size':asset.size,'sha256':asset.sha256,'ms':round((time.perf_counter()-at)*1000,2),'seeded_prefix_bytes':asset.size-65536,'network_suffix_bytes':65536,'passed':True})
    print(asset.name+' verified',flush=True)
model,server=install(testroot,token)
version=subprocess.run([server,'--version'],capture_output=True,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=15)
checks={'three_upstream_resumes_verified':len(rows)==3,'atomic_runtime_installed':Path(server).is_file(),'cuda_dependency_installed':(Path(server).parent/'cudart64_12.dll').is_file(),'version_starts':version.returncode==0 and '10896' in version.stdout+version.stderr}
report={'passed':all(checks.values()),'checks':checks,'assets':rows,'note':'Each real network transfer resumes the last 64 KiB of an existing verified asset; SHA-256 checks entire file. Full-from-zero HTTP path separately tested with controlled responses; no fresh 1.93 GB transfer claimed.'}
(root/'test-results/real-assets.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2));raise SystemExit(not report['passed'])
