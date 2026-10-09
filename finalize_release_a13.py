"""Verify release provenance and publish measurements with explicit limits."""
from pathlib import Path
import hashlib,json,shutil
from PyInstaller.archive.readers import ZlibArchiveReader
from release_snapshot import canonical
from babelander import __version__
ROOT=Path(__file__).parent
def read(path):return json.loads((ROOT/path).read_text(encoding='utf8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    assert __version__=='2.0.0a13'
    frozen=read('test-results/frozen-source-a13.json')
    assert all(digest(ROOT/'babelander'/name)==value for name,value in frozen.items())
    archive=ZlibArchiveReader(str(ROOT/'build/work/Babelander2/PYZ-00.pyz'))
    compiled={}
    for path in (ROOT/'babelander').glob('*.py'):
        name='babelander' if path.stem=='__init__' else 'babelander.'+path.stem
        code=archive.extract(name)
        compiled[name]=canonical(code)==canonical(compile(path.read_text(encoding='utf8'),code.co_filename,'exec',dont_inherit=True,optimize=0))
    assert all(compiled.values())
    assert (ROOT/'dist/releases'/__version__/'Babelander2/_internal/babelander/theme.qss').read_bytes()==(ROOT/'babelander/theme.qss').read_bytes()
    exe=read('test-results/release-a13/exe.json');wheel=read('test-results/wheel.json')
    assert exe['passed'] and exe['frozen'] and exe['version']==__version__ and exe['qt_platform']=='offscreen'
    assert wheel['passed'] and wheel['selftest']['version']==__version__ and all(wheel['wheel_source_matches'].values())
    files={'core':'unit-tests.json','assets':'asset-unit.json','pipeline':'pipeline.json','layout':'layout-unit.json',
           'equipment':'equipment-checks-a13.json','trigger':'subtitle-trigger-unit.json','accounting':'replay-accounting-a13.json'}
    units={name:read('test-results/'+file) for name,file in files.items()}
    assert all(r['passed'] for r in units.values())
    counts={name:r.get('tests_run',r.get('tests',0)) for name,r in units.items()}
    assert sum(counts.values())==208,counts
    full=read('test-results/replay-a13-final-100-t4/results.json')
    small=read('test-results/replay-a13-mixed-20/results.json')
    baseline=read('test-results/replay-a12-baseline-20/results.json')
    for report in (full,small,baseline):
        assert all(report[k] for k in ('completed','source_unchanged','owned_model_stopped','workers_stopped','temporary_frames_removed'))
    assert full['application_source_sha256']==frozen and full['resource_sampler_stopped']
    assert small['application_source_sha256']==read('test-results/frozen-source-a13-pre-guard.json')
    assert full['summary']['4']['cues']==100 and full['holdout_summary']['4']['cues']==12
    assert full['config']['mixed_text_trigger'] and small['config']['mixed_text_trigger']
    equipment=read('test-results/equipment-structures-a13-final-regression/report.json')
    assert equipment['completed'] and equipment['application_source_unchanged'] and equipment['own_model_stopped'] and equipment['workers_stopped']
    assert all(digest(ROOT/'babelander'/name)==value for name,value in equipment['application_sha256'].items())
    assert len(equipment['runs'])==20 and all(r['renderable'] and r['single_capture_ocr'] and r['geometry_exact'] and r['art_unchanged'] and r['source_colors_preserved'] for r in equipment['runs'])
    known=[{k:r.get(k) for k in ('id','missing_source_numbers','missing_target_numbers')} for r in equipment['runs'] if not r['usable']]
    public=ROOT/'assets/verification';public.mkdir(exist_ok=True)
    for name,file in files.items():shutil.copy2(ROOT/'test-results'/file,public/(name+'-checks-a13.json'))
    for source,name in [('replay-a12-baseline-20/results.json','replay-baseline-20-a12.json'),
                        ('replay-a13-mixed-20/results.json','replay-mixed-20-a13.json'),
                        ('replay-a13-final-100-t4/results.json','replay-mixed-100-t4-a13.json'),
                        ('replay-a13-mixed-100-t4/results.json','replay-pre-guard-100-t4-a13.json'),
                        ('guard-diagnostic-a13.json','guard-diagnostic-a13.json'),
                        ('subtitle-trigger-stress-a13.json','subtitle-trigger-stress-a13.json'),
                        ('native-capture-a13.json','native-capture-a13.json'),
                        ('ocr-opencv-budget-a13.json','ocr-opencv-budget-a13.json'),
                        ('release-a13/exe.json','exe-selftest-a13.json'),('wheel.json','wheel-a13.json'),
                        ('wheel-selftest.json','wheel-selftest-a13.json'),
                        ('equipment-structures-a13-final-regression/report.json','equipment-regression-a13.json')]:
        shutil.copy2(ROOT/'test-results'/source,public/name)
    report={'version':__version__,'release_integrity_passed':True,'synthetic_checks':sum(counts.values()),'synthetic_groups':counts,
        'compiled_modules_match_current_source':compiled,'wheel_source_matches':wheel['wheel_source_matches'],
        'exe_real_checks':len(exe['checks']),'wheel_real_checks':len(wheel['selftest']['checks']),
        'full_replay':full['summary'],'full_replay_holdouts':full['holdout_summary'],
        'mixed_trigger_default_enabled':False,'default_ocr_threads':2,'tested_fast_ocr_threads':4,
        'known_equipment_failures':known,'semantic_accuracy_scored':False,'real_game_fps_measured':False,
        'own_gpu_memory_samples':[row['owned_gpu_process_memory'] for row in full['system_load'] if row.get('owned_gpu_process_memory')],
        'live_gdi_only_measured':True,'source_color_regression_passed':20,
        'application_sha256':frozen,'exe_sha256':digest(ROOT/'dist/releases'/__version__/'Babelander2/Babelander2.exe'),
        'wheel_sha256':digest(ROOT/'dist'/f'babelander_desktop-{__version__}-py3-none-any.whl')}
    (public/'release-a13.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'release_integrity_passed':True,'unit_checks':sum(counts.values()),'subtitle':full['summary'],'holdouts':full['holdout_summary'],'known_equipment_failures':len(known)}))
if __name__=='__main__':main()
