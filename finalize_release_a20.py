"""Seal a20 source, actual executable/wheel, and whole-app acceptance evidence."""
from pathlib import Path
import json,hashlib,shutil
from PyInstaller.archive.readers import ZlibArchiveReader
from release_snapshot import canonical
from babelander import __version__
ROOT=Path(__file__).resolve().parent
out=ROOT/'test-results/supertest-a20'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert __version__=='2.0.0a20'
frozen=read(ROOT/'test-results/frozen-source-a20.json');assert frozen=={p.name:digest(p) for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}
archive=ZlibArchiveReader(str(ROOT/'build/work/Babelander2/PYZ-00.pyz'));compiled={}
for p in (ROOT/'babelander').glob('*.py'):
    name='babelander' if p.stem=='__init__' else 'babelander.'+p.stem;code=archive.extract(name)
    compiled[name]=canonical(code)==canonical(compile(p.read_text(encoding='utf8'),code.co_filename,'exec',dont_inherit=True,optimize=0))
assert all(compiled.values())
exe=read(out/'exe.json');wheel=read(out/'wheel.json');summary=read(out/'summary.json')
assert exe['passed'] and exe['frozen'] and exe['version']==__version__ and exe['qt_platform']=='offscreen'
assert wheel['passed'] and wheel['selftest']['version']==__version__ and all(wheel['wheel_source_matches'].values())
assert len(exe['checks'])==len(wheel['selftest']['checks'])==34
assert summary['regression_count']==390 and summary['functional_checks']['regressions']
public=ROOT/'assets/verification/supertest-a20';public.mkdir(parents=True,exist_ok=True)
for name in ('summary.json','runner-units.json','runner-live.json','runner-package.json','runner-soak.json','critical-regressions.json','exe.json','wheel.json','wheel-selftest.json','cloud.json','quality.json','soak.json','resources.json','model-lifecycle.json','preload-cancel.json','native-focus.json'):
    shutil.copy2(out/name,public/name)
for name in ('modes','equipment','quest','chat','chat-events'):
    shutil.copy2(out/name/'report.json',public/(name+'.json'))
shutil.copy2(ROOT/'test-results/supertest-a20-motion/results.json',public/'moving-background.json')
result={'version':__version__,'release_integrity_passed':True,'compiled_modules_match_current_source':compiled,'wheel_source_matches':wheel['wheel_source_matches'],'application_sha256':frozen,
'exe_sha256':digest(ROOT/'dist/releases'/__version__/'Babelander2/Babelander2.exe'),'wheel_sha256':digest(ROOT/'dist'/f'babelander_desktop-{__version__}-py3-none-any.whl'),
'regression_count':390,'exe_real_checks':34,'wheel_real_checks':34,'functional_passed':summary['functional_passed'],'critical_markers_passed':summary['critical_marker_checks_passed'],'speed_passed':summary['speed_passed'],'all_acceptance_passed':summary['all_acceptance_passed'],'semantic_accuracy_scored':False,'real_game_validated':False}
(ROOT/'assets/verification/release-a20.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k not in ('compiled_modules_match_current_source','wheel_source_matches','application_sha256')},indent=2))
