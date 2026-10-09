"""Seal foreground suspension with source/binary provenance and honest scope."""
from pathlib import Path
import hashlib,json,shutil
from PyInstaller.archive.readers import ZlibArchiveReader
from release_snapshot import canonical
from babelander import __version__
ROOT=Path(__file__).parent
def read(path):return json.loads((ROOT/path).read_text(encoding='utf8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    assert __version__=='2.0.0a16'
    frozen=read('test-results/frozen-source-a16.json')
    assert all(digest(ROOT/'babelander'/name)==value for name,value in frozen.items())
    archive=ZlibArchiveReader(str(ROOT/'build/work/Babelander2/PYZ-00.pyz'))
    compiled={}
    for path in (ROOT/'babelander').glob('*.py'):
        name='babelander' if path.stem=='__init__' else 'babelander.'+path.stem
        code=archive.extract(name)
        compiled[name]=canonical(code)==canonical(compile(path.read_text(encoding='utf8'),code.co_filename,'exec',dont_inherit=True,optimize=0))
    assert all(compiled.values())
    assert (ROOT/'dist/releases'/__version__/'Babelander2/_internal/babelander/theme.qss').read_bytes()==(ROOT/'babelander/theme.qss').read_bytes()
    exe=read('test-results/release-a16/exe.json');wheel=read('test-results/wheel.json')
    assert exe['passed'] and exe['frozen'] and exe['version']==__version__ and exe['qt_platform']=='offscreen'
    assert wheel['passed'] and wheel['selftest']['version']==__version__ and all(wheel['wheel_source_matches'].values())
    files={'core':'unit-tests.json','assets':'asset-unit.json','pipeline':'pipeline.json','layout':'layout-unit.json',
           'equipment':'equipment-checks-a16.json','trigger':'subtitle-trigger-unit.json','accounting':'replay-accounting-a16.json',
           'numeric-recovery':'equipment-recovery-unit.json','window-focus':'window-focus-unit.json'}
    units={name:read('test-results/'+file) for name,file in files.items()}
    assert all(r['passed'] for r in units.values())
    counts={name:r.get('tests_run',r.get('tests',0)) for name,r in units.items()}
    assert sum(counts.values())==290,counts
    replay=read('test-results/window-move-replay-a16.json')
    native=read('test-results/window-focus-native-a16.json')
    for report,key in ((replay,'application_sha256'),(native,'source_sha256')):
        assert report['passed'] and report['source_unchanged']
        assert all(frozen[name]==value for name,value in report[key].items())
    assert replay['owned_model_stopped'] and replay['workers_stopped'] and all(replay['checks'].values())
    assert replay['real_cpu_ocr'] and replay['real_cuda_model'] and replay['foreground_api']=='controlled fixture'
    assert native['foreground_control_calls']==0 and not native['visible_window_created'] and not native['existing_windows_modified']
    public=ROOT/'assets/verification';public.mkdir(exist_ok=True)
    for name,file in files.items():shutil.copy2(ROOT/'test-results'/file,public/(name+'-checks-a16.json'))
    for source,name in [('window-move-replay-a16.json','window-move-replay-a16.json'),
                        ('window-focus-native-a16.json','window-focus-native-a16.json'),
                        ('release-a16/exe.json','exe-selftest-a16.json'),('wheel.json','wheel-a16.json'),
                        ('wheel-selftest.json','wheel-selftest-a16.json')]:
        shutil.copy2(ROOT/'test-results'/source,public/name)
    report={'version':__version__,'release_integrity_passed':True,'synthetic_checks':sum(counts.values()),'synthetic_groups':counts,
            'compiled_modules_match_current_source':compiled,'wheel_source_matches':wheel['wheel_source_matches'],
            'exe_real_checks':len(exe['checks']),'wheel_real_checks':len(wheel['selftest']['checks']),
            'real_engine_focus_checks':replay['checks'],'native_api_checks':native['checks'],
            'single_resume_to_full_qt_ms':replay['resume_to_full_qt_ms'],'single_move_observed_to_full_qt_ms':replay['move_observed_to_full_qt_ms'],'native_state_timing':native['native_state_timing'],
            'new_model':False,'real_game_validated':False,'real_game_fps_measured':False,
            'foreground_changes_by_test':0,'application_sha256':frozen,
            'exe_sha256':digest(ROOT/'dist/releases'/__version__/'Babelander2/Babelander2.exe'),
            'wheel_sha256':digest(ROOT/'dist'/f'babelander_desktop-{__version__}-py3-none-any.whl')}
    (public/'release-a16.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('compiled_modules_match_current_source','wheel_source_matches','application_sha256')},indent=2))
if __name__=='__main__':main()
