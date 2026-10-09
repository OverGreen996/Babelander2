"""Seal only fresh a21 evidence; do not borrow a20's full-suite acceptance."""
from pathlib import Path
import hashlib,json,shutil,zipfile
from babelander import __version__
ROOT=Path(__file__).resolve().parent
PUBLIC=ROOT/'assets/verification/chat-ocr-a21'

def read(path):return json.loads(path.read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

assert __version__=='2.0.0a21'
frozen=read(ROOT/'test-results/frozen-source-a21.json')
actual={p.name:sha(p) for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}
assert frozen==actual
units=read(ROOT/'test-results/supertest-a21/runner-units.json')
ocr=read(ROOT/'test-results/chat-incremental-final-a21/report.json')
full=read(ROOT/'test-results/chat-full-control-a21/report.json')
live=read(ROOT/'test-results/chat-reuse-live-a21/report.json')
edges=read(ROOT/'test-results/chat-ocr-edges-a21.json')
modes=read(ROOT/'test-results/a21-modes/report.json')
events=read(ROOT/'test-results/a21-chat-events/report.json')
exe=read(ROOT/'test-results/supertest-a21/exe.json')
wheel=read(ROOT/'test-results/supertest-a21/wheel.json')
assert len(units['runs'])==14 and sum(r['tests_run'] or 0 for r in units['runs'])==413
assert all(r['returncode']==0 for r in units['runs']) and units['source_unchanged'] and units['application_sha256']==actual
assert ocr['source_unchanged'] and ocr['frames_identical'] and not ocr['event_mismatches']
assert ocr['source_sha256']=={k:v for k,v in actual.items() if k.endswith('.py')}
assert edges['passed'] and edges['source_unchanged'] and modes['functional_passed'] and events['passed']
for report in (full,live):
    assert report['completed'] and report['source_sha256']==actual and report['source_unchanged']
    assert report['live_summary']['results']==report['live_summary']['no_warning']==100
    assert not report['live_summary']['missing_message_indices'] and not report['live_summary']['duplicated_message_indices']
    assert report['sqlite_rows']=={'cache':0,'history':0,'usage':0}
    assert report['owned_model_stopped'] and report['workers_stopped'] and report['recognition_sessions_cleared'] and report['shared_ocr_context_cleared']
assert [r['source'] for r in full['live_results']]==[r['source'] for r in live['live_results']]
assert exe['passed'] and exe['frozen'] and exe['version']==__version__
assert wheel['passed'] and wheel['selftest']['version']==__version__ and all(wheel['wheel_source_matches'].values())
PUBLIC.mkdir(parents=True,exist_ok=True)
for name,path in {
    'ocr-abba.json':'chat-incremental-final-a21/report.json',
    'chat-control.json':'chat-full-control-a21/report.json',
    'chat-reuse.json':'chat-reuse-live-a21/report.json',
    'edge-cases.json':'chat-ocr-edges-a21.json',
    'modes.json':'a21-modes/report.json','chat-events.json':'a21-chat-events/report.json',
    'units.json':'supertest-a21/runner-units.json',
    'exe.json':'supertest-a21/exe.json','wheel.json':'supertest-a21/wheel.json',
    'package.json':'supertest-a21/runner-package.json',
}.items():shutil.copy2(ROOT/'test-results'/path,PUBLIC/name)
summary={'version':__version__,'application_sha256':actual,'regressions':413,
         'new_message_outputs_equal':True,'private_sqlite_rows':live['sqlite_rows'],
         'cache_sessions_cleared':True,'edge_checks':len(edges['checks']),
         'ocr_runs':[{k:v for k,v in r.items() if k!='samples'} for r in ocr['runs']],
         'control_live':full['live_summary'],'reuse_live':live['live_summary'],
         'recognition_patch_peak_mib':live['recognition_patch_peak_mib'],
         'exe_checks':len(exe['checks']),'wheel_checks':len(wheel['selftest']['checks']),
         'semantic_accuracy_scored':False,'all_700ms_passed':False,
         'real_game_validated':False,'real_desktop_capture':False,'foreground_control_calls':0,
         'scope':'Chat recognition reuse only. No capture frequency, model, OCR threads, allocator, card or subtitle trigger changes. Full a20 suite is historical evidence, not rerun here.'}
(PUBLIC/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
from release_snapshot import main
main()
artifacts=read(ROOT/'test-results/artifacts.json')
assert artifacts['passed'] and all(artifacts['compiled_modules_match_current_source'].values())
manifest=ROOT/'dist/Babelander2-2.0.0a21-sha256.json'
manifest.write_text(json.dumps({**artifacts,'regressions':413,'exe_checks':len(exe['checks']),
                               'wheel_checks':len(wheel['selftest']['checks'])},ensure_ascii=False,indent=2),encoding='utf8')
with zipfile.ZipFile(ROOT/'dist/Babelander2-2.0.0a21-source.zip') as archive:
    assert all(hashlib.sha256(archive.read('Babelander2/'+name)).hexdigest()==digest for name,digest in artifacts['source_files'].items())
print(json.dumps({'release_integrity_passed':True,'source_files':len(artifacts['source_files']),
                  'exe_sha256':artifacts['exe_sha256'],'source_zip_sha256':artifacts['source_zip_sha256']}))
