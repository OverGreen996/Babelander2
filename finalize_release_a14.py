"""Seal numeric recovery with explicit safe-fallback and synthetic-test limits."""
from pathlib import Path
import hashlib,json,shutil
from PyInstaller.archive.readers import ZlibArchiveReader
from release_snapshot import canonical
from babelander import __version__
ROOT=Path(__file__).parent
def read(path):return json.loads((ROOT/path).read_text(encoding='utf8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    assert __version__=='2.0.0a14'
    frozen=read('test-results/frozen-source-a14.json')
    assert all(digest(ROOT/'babelander'/name)==value for name,value in frozen.items())
    archive=ZlibArchiveReader(str(ROOT/'build/work/Babelander2/PYZ-00.pyz'))
    compiled={}
    for path in (ROOT/'babelander').glob('*.py'):
        name='babelander' if path.stem=='__init__' else 'babelander.'+path.stem
        code=archive.extract(name)
        compiled[name]=canonical(code)==canonical(compile(path.read_text(encoding='utf8'),code.co_filename,'exec',dont_inherit=True,optimize=0))
    assert all(compiled.values())
    assert (ROOT/'dist/releases'/__version__/'Babelander2/_internal/babelander/theme.qss').read_bytes()==(ROOT/'babelander/theme.qss').read_bytes()
    exe=read('test-results/release-a14/exe.json');wheel=read('test-results/wheel.json')
    assert exe['passed'] and exe['frozen'] and exe['version']==__version__ and exe['qt_platform']=='offscreen'
    assert wheel['passed'] and wheel['selftest']['version']==__version__ and all(wheel['wheel_source_matches'].values())
    files={'core':'unit-tests.json','assets':'asset-unit.json','pipeline':'pipeline.json','layout':'layout-unit.json',
           'equipment':'equipment-checks-a14.json','trigger':'subtitle-trigger-unit.json','accounting':'replay-accounting-a14.json',
           'numeric-recovery':'equipment-recovery-unit.json'}
    units={name:read('test-results/'+file) for name,file in files.items()}
    assert all(r['passed'] for r in units.values())
    counts={name:r.get('tests_run',r.get('tests',0)) for name,r in units.items()}
    assert sum(counts.values())==230,counts
    matrix=read('test-results/equipment-structures-a14-final/report.json')
    assert matrix['version']==__version__ and all(matrix[k] for k in ('completed','application_source_unchanged','own_model_stopped','workers_stopped','no_equipment_monitors','stop_hid_overlay','stop_released_backdrop'))
    assert all(frozen[name]==value for name,value in matrix['application_sha256'].items())
    assert len(matrix['runs'])==40
    assert all(all(r[k] for k in ('usable','renderable','single_capture_ocr','geometry_exact','art_unchanged','literal_pixels_unchanged','source_colors_preserved')) for r in matrix['runs'])
    previous=read('assets/verification/equipment-regression-a13.json')
    assert {f['id']:f['frame_sha256'] for f in matrix['fixtures']}=={f['id']:f['frame_sha256'] for f in previous['fixtures']}
    numeric=read('test-results/equipment-numeric-a14.json')
    assert numeric['passed'] and numeric['source_unchanged'] and numeric['wrong_value_cases']==0
    assert all(frozen[name]==value for name,value in numeric['source_sha256'].items())
    assert numeric['exact_recovery_cases']==26 and numeric['safe_fallback_cases']==2
    public=ROOT/'assets/verification';public.mkdir(exist_ok=True)
    for name,file in files.items():shutil.copy2(ROOT/'test-results'/file,public/(name+'-checks-a14.json'))
    for source,name in [('equipment-structures-a14-final/report.json','equipment-regression-a14.json'),
                        ('equipment-numeric-a14.json','equipment-numeric-a14.json'),
                        ('release-a14/exe.json','exe-selftest-a14.json'),('wheel.json','wheel-a14.json'),
                        ('wheel-selftest.json','wheel-selftest-a14.json')]:
        shutil.copy2(ROOT/'test-results'/source,public/name)
    gallery=ROOT/'assets/equipment-recovery-a14';gallery.mkdir(exist_ok=True)
    for name in ('battle-card-0-original.png','battle-card-0-translated.png','battle-card-0-comparison.png'):
        shutil.copy2(ROOT/'test-results/equipment-structures-a14-final'/name,gallery/name)
    report={'version':__version__,'release_integrity_passed':True,'synthetic_checks':sum(counts.values()),'synthetic_groups':counts,
            'compiled_modules_match_current_source':compiled,'wheel_source_matches':wheel['wheel_source_matches'],
            'exe_real_checks':len(exe['checks']),'wheel_real_checks':len(wheel['selftest']['checks']),
            'equipment_full_pipeline':matrix['summary'],'exact_numeric_cases':numeric['exact_recovery_cases'],
            'safe_numeric_fallback_cases':numeric['safe_fallback_cases'],'wrong_numeric_cases':numeric['wrong_value_cases'],
            'negative_retry_cases':len(numeric['negative_cases']),'real_game_fps_measured':False,'semantic_accuracy_scored':False,
            'new_model':False,'subtitle_numeric_retries_enabled':False,'application_sha256':frozen,
            'exe_sha256':digest(ROOT/'dist/releases'/__version__/'Babelander2/Babelander2.exe'),
            'wheel_sha256':digest(ROOT/'dist'/f'babelander_desktop-{__version__}-py3-none-any.whl')}
    (public/'release-a14.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('compiled_modules_match_current_source','wheel_source_matches','application_sha256')},indent=2))
if __name__=='__main__':main()
