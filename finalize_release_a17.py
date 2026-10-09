"""Verify source/binary provenance and publish a17-only local test evidence."""
from pathlib import Path
import hashlib,json,shutil
from PyInstaller.archive.readers import ZlibArchiveReader
from release_snapshot import canonical
from babelander import __version__
ROOT=Path(__file__).parent
def read(name):return json.loads((ROOT/name).read_text(encoding='utf8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    assert __version__=='2.0.0a17'
    frozen=read('test-results/frozen-source-a17.json')
    assert all(digest(ROOT/'babelander'/name)==value for name,value in frozen.items())
    archive=ZlibArchiveReader(str(ROOT/'build/work/Babelander2/PYZ-00.pyz'));compiled={}
    for path in (ROOT/'babelander').glob('*.py'):
        name='babelander' if path.stem=='__init__' else 'babelander.'+path.stem;code=archive.extract(name)
        compiled[name]=canonical(code)==canonical(compile(path.read_text(encoding='utf8'),code.co_filename,'exec',dont_inherit=True,optimize=0))
    assert all(compiled.values())
    assert (ROOT/'dist/releases'/__version__/'Babelander2/_internal/babelander/theme.qss').read_bytes()==(ROOT/'babelander/theme.qss').read_bytes()
    exe=read('test-results/release-a17/exe.json');wheel=read('test-results/wheel.json')
    assert exe['passed'] and exe['frozen'] and exe['version']==__version__ and exe['qt_platform']=='offscreen'
    assert wheel['passed'] and wheel['selftest']['version']==__version__ and all(wheel['wheel_source_matches'].values())
    assert len(exe['checks'])==len(wheel['selftest']['checks'])==23
    files={'core':'unit-tests.json','assets':'asset-unit.json','pipeline':'pipeline.json','layout':'layout-unit.json',
           'equipment':'equipment-checks-a17.json','trigger':'subtitle-trigger-unit.json','accounting':'replay-accounting-a17.json',
           'numeric-recovery':'equipment-recovery-unit.json','window-focus':'window-focus-unit.json','preload':'preload-unit.json'}
    units={name:read('test-results/'+file) for name,file in files.items()}
    assert all(report['passed'] for report in units.values())
    counts={name:report.get('tests_run',report.get('tests',0)) for name,report in units.items()};assert sum(counts.values())==314,counts
    real=read('test-results/preload-real-a17.json');cancel=read('test-results/preload-cancel-real-a17.json')
    for report in (real,cancel):
        assert report['passed'] and report['source_unchanged'] and report['owned_models_stopped'] and report['workers_stopped']
        assert report['source_sha256']==frozen and not report['paid_api'] and report['foreground_control_calls']==0
        assert all(report['checks'].values())
    assert len(real['rows'])==10 and all(row['cuda_offload_confirmed'] and not row['cache_hit'] for row in real['rows'])
    public=ROOT/'assets/verification';public.mkdir(exist_ok=True)
    for name,file in files.items():shutil.copy2(ROOT/'test-results'/file,public/(name+'-checks-a17.json'))
    for source,target in [('preload-real-a17.json','preload-real-a17.json'),('preload-cancel-real-a17.json','preload-cancel-real-a17.json'),
                          ('release-a17/exe.json','exe-selftest-a17.json'),('wheel.json','wheel-a17.json'),('wheel-selftest.json','wheel-selftest-a17.json')]:
        shutil.copy2(ROOT/'test-results'/source,public/target)
    result={'version':__version__,'release_integrity_passed':True,'synthetic_checks':sum(counts.values()),'synthetic_groups':counts,
            'compiled_modules_match_current_source':compiled,'wheel_source_matches':wheel['wheel_source_matches'],
            'exe_real_checks':len(exe['checks']),'wheel_real_checks':len(wheel['selftest']['checks']),
            'real_preload_checks':real['checks'],'real_cancellation_checks':cancel['checks'],
            'first_text_request_diagnostic':real['summary'],'diagnostic_pairs':5,'complete_ocr_pipeline_benchmark':False,
            'new_model':False,'real_game_validated':False,'real_game_fps_measured':False,'application_sha256':frozen,
            'exe_sha256':digest(ROOT/'dist/releases'/__version__/'Babelander2/Babelander2.exe'),
            'wheel_sha256':digest(ROOT/'dist'/f'babelander_desktop-{__version__}-py3-none-any.whl')}
    (public/'release-a17.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({key:value for key,value in result.items() if key not in ('application_sha256','compiled_modules_match_current_source','wheel_source_matches')},indent=2))
if __name__=='__main__':main()
