"""Seal fresh chat scheduling evidence and actual a22 binary/source packages."""
from pathlib import Path
import hashlib,json,shutil,zipfile
from babelander import __version__
ROOT=Path(__file__).resolve().parent;PUBLIC=ROOT/'assets/verification/chat-poll-a22'
def read(path):return json.loads(path.read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
actual={p.name:sha(p) for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}
assert __version__=='2.0.0a22'
assert read(ROOT/'test-results/frozen-source-a22.json')==actual
units=read(ROOT/'test-results/supertest-a22/runner-units.json')
bench=read(ROOT/'test-results/chat-poll-fixed-a22/report.json')
burst=read(ROOT/'test-results/chat-poll-burst-a22/0-100.json')
resources=read(ROOT/'test-results/chat-poll-resources-a22.json')
settings=read(ROOT/'test-results/settings-a22/report.json')
modes=read(ROOT/'test-results/a22-modes/report.json')
events=read(ROOT/'test-results/a22-chat-events/report.json')
edges=read(ROOT/'test-results/chat-ocr-edges-a22.json')
exe=read(ROOT/'test-results/supertest-a22/exe.json')
wheel=read(ROOT/'test-results/supertest-a22/wheel.json')
assert len(units['runs'])==14 and sum(r['tests_run'] or 0 for r in units['runs'])==421
assert all(r['returncode']==0 for r in units['runs']) and units['source_unchanged'] and units['application_sha256']==actual
assert bench['functional_passed'] and bench['source_sha256']==actual and bench['source_unchanged']
assert burst['passed'] and burst['source_sha256']==actual and burst['source_unchanged']
assert resources['passed'] and resources['source_sha256']==actual and resources['source_unchanged']
assert settings['passed'] and modes['functional_passed'] and modes['application_sha256']==actual and events['passed']
assert edges['passed'] and edges['source_sha256']=={k:v for k,v in actual.items() if k.endswith('.py')}
assert exe['passed'] and exe['frozen'] and exe['version']==__version__ and len(exe['checks'])==37
assert wheel['passed'] and wheel['selftest']['version']==__version__ and len(wheel['selftest']['checks'])==37 and all(wheel['wheel_source_matches'].values())
PUBLIC.mkdir(parents=True,exist_ok=True)
for name,path in {
    'fixed-abba.json':'chat-poll-fixed-a22/report.json','burst.json':'chat-poll-burst-a22/0-100.json',
    'resources.json':'chat-poll-resources-a22.json','settings.json':'settings-a22/report.json',
    'units.json':'supertest-a22/runner-units.json','modes.json':'a22-modes/report.json',
    'chat-events.json':'a22-chat-events/report.json','edges.json':'chat-ocr-edges-a22.json',
    'exe.json':'supertest-a22/exe.json','wheel.json':'supertest-a22/wheel.json',
    'package.json':'supertest-a22/runner-package.json',
}.items():shutil.copy2(ROOT/'test-results'/path,PUBLIC/name)
for width in (1190,880):shutil.copy2(ROOT/f'test-results/settings-a22/settings-{width}.png',PUBLIC/f'settings-{width}.png')
summary={'version':__version__,'application_sha256':actual,'regressions':421,
         'full_latency':bench['summary'],'fixed_sources_identical':True,
         'warm_model_verified':all(r['model_stayed_warm'] for r in bench['runs']),
         'burst_messages':len(burst['results']),'burst_within_700ms':sum(r['shown_to_qt_ms']<=700 for r in burst['results']),
         'noise_cpu_scope':resources['scope'],'resource_runs':[{k:v for k,v in r.items() if k!='traces'} for r in resources['runs']],
         'exe_checks':37,'wheel_checks':37,'all_700ms_passed':bench['summary']['100']['within_700ms']==200,
         'real_game_validated':False,'semantic_accuracy_scored':False,
         'real_desktop_capture':False,'foreground_control_calls':0,
         'scope':'Chat observation scheduling, independently exposed setting and FIFO shared-image admission to prevent busy chat starving other image work. No model, OCR engine/threads, card/subtitle trigger, allocator or stop-release policy changes. Resource-only run stubs translation; fixed and burst runs use the real local model.'}
(PUBLIC/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
from release_snapshot import main
main()
artifacts=read(ROOT/'test-results/artifacts.json')
assert artifacts['passed'] and all(artifacts['compiled_modules_match_current_source'].values())
(ROOT/'dist/Babelander2-2.0.0a22-sha256.json').write_text(json.dumps({**artifacts,'regressions':421,'exe_checks':37,'wheel_checks':37},ensure_ascii=False,indent=2),encoding='utf8')
with zipfile.ZipFile(ROOT/'dist/Babelander2-2.0.0a22-source.zip') as archive:
    assert all(hashlib.sha256(archive.read('Babelander2/'+name)).hexdigest()==digest for name,digest in artifacts['source_files'].items())
print(json.dumps({'release_integrity_passed':True,'source_files':len(artifacts['source_files']),
                  'exe_sha256':artifacts['exe_sha256'],'source_zip_sha256':artifacts['source_zip_sha256']}))
