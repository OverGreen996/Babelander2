"""Install the wheel away from editable source, then run its actual self-test."""
from pathlib import Path
import json
import os
import subprocess
import sys
import zipfile
from babelander import __version__
root=Path(__file__).resolve().parent
wheel=root/'dist'/f'babelander_desktop-{__version__}-py3-none-any.whl'
with zipfile.ZipFile(wheel) as archive:
    matches={p.name:archive.read('babelander/'+p.name)==p.read_bytes() for p in (root/'babelander').glob('*') if p.suffix in ('.py','.qss')}
assert all(matches.values()),matches
destination=root/'test-results/wheel-runtime'
subprocess.run([sys.executable,'-m','pip','install','--no-deps','--upgrade','--target',str(destination),str(wheel)],check=True,capture_output=True)
report=root/'test-results/wheel-selftest.json'
environment=os.environ.copy()
environment['QT_QPA_PLATFORM']='offscreen'
environment['BABELANDER_V2_MODEL']=str(root/'test-results/asset-install/assets/downloads/Qwen_Qwen3-1.7B-Q4_K_M.gguf')
environment['BABELANDER_V2_SERVER']=str(next((root/'test-results/asset-install/assets').glob('llama-b10896-*/llama-server.exe')))
code='import sys,pathlib; sys.path.insert(0,sys.argv[1]); import babelander; assert pathlib.Path(babelander.__file__).is_relative_to(pathlib.Path(sys.argv[1])); report=sys.argv[2]; sys.argv=["Babelander2-wheel","--self-test","--report",report]; from babelander.selftest import run; sys.exit(run())'
result=subprocess.run([sys.executable,'-I','-c',code,str(destination),str(report)],env=environment,capture_output=True,timeout=90)
details=json.loads(report.read_text(encoding='utf-8')) if report.exists() else {}
summary={'passed':result.returncode==0 and details.get('passed',False),'wheel_source_matches':matches,'isolated_wheel_import':True,'exit_code':result.returncode,'selftest':details}
(root/'test-results/wheel.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed':summary['passed'],'source_files':len(matches),'exit_code':result.returncode}));raise SystemExit(not summary['passed'])
