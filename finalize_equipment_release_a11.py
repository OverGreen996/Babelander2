"""Seal a11 only after source, bundle, wheel, lifecycle and replay verification."""
from pathlib import Path
import hashlib,json,shutil
from PyInstaller.archive.readers import ZlibArchiveReader
from release_snapshot import canonical
from babelander import __version__
ROOT=Path(__file__).resolve().parent
def read(path):return json.loads((ROOT/path).read_text(encoding='utf8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    assert __version__=='2.0.0a11'
    bundle=ROOT/'dist/releases'/__version__/'Babelander2'
    archive=ZlibArchiveReader(str(ROOT/'build/work/Babelander2/PYZ-00.pyz'))
    matches={}
    for path in (ROOT/'babelander').glob('*.py'):
        name='babelander' if path.stem=='__init__' else 'babelander.'+path.stem
        code=archive.extract(name)
        matches[name]=canonical(code)==canonical(compile(path.read_text(encoding='utf8'),code.co_filename,'exec',dont_inherit=True,optimize=0))
    assert all(matches.values())
    assert (bundle/'_internal/babelander/theme.qss').read_bytes()==(ROOT/'babelander/theme.qss').read_bytes()
    units={name:read('test-results/'+filename) for name,filename in (
        ('core','unit-tests.json'),('assets','asset-unit.json'),('pipeline','pipeline.json'),('layout','layout-unit.json'),('equipment','equipment-checks-a11.json'))}
    assert all(r['passed'] for r in units.values())
    counts={name:r.get('tests_run',r.get('tests',r.get('checks',0))) for name,r in units.items()}
    assert sum(counts.values())==168,counts
    exe=read('test-results/release-a11/exe.json');wheel=read('test-results/wheel.json')
    assert exe['passed'] and exe['version']==__version__ and exe['frozen'] and exe['qt_platform']=='offscreen'
    assert wheel['passed'] and wheel['selftest']['version']==__version__ and all(wheel['wheel_source_matches'].values())
    replay=read('test-results/equipment-matrix-a11-final/report.json')
    assert replay['completed'] and replay['application_source_unchanged'] and replay['own_model_stopped'] and replay['workers_stopped']
    assert replay['no_equipment_monitors'] and replay['stop_hid_overlay'] and replay['stop_released_backdrop']
    assert len(replay['fixtures'])==32 and len(replay['runs'])==96
    assert all(r.get('usable') and r['single_capture_ocr'] and r['geometry_exact'] for r in replay['runs'])
    assert all(digest(ROOT/'babelander'/name)==value for name,value in replay['application_sha256'].items())
    baseline=read('test-results/equipment-matrix-a10-baseline/report.json')
    assert baseline['version']=='2.0.0a10' and baseline['completed'] and baseline['application_source_unchanged']
    assert {f['id']:f['frame_sha256'] for f in replay['fixtures']}=={f['id']:f['frame_sha256'] for f in baseline['fixtures']}
    user=read('test-results/equipment-user-card-a11.json')
    assert user['passed'] and user['own_model_stopped'] and user['workers_stopped'] and user['capture_calls']==user['ocr_calls']==1
    assert user['results'][0]['renderable'] and user['results'][0]['geometry']==[366,46,450,737]
    assert user['weapon_art_pixels_unchanged'] and user['large_power_number_pixels_unchanged']
    public=ROOT/'assets/verification';public.mkdir(exist_ok=True)
    for source,destination in (('test-results/release-a11/exe.json','exe-selftest-a11.json'),('test-results/wheel.json','wheel-a11.json'),
        ('test-results/wheel-selftest.json','wheel-selftest-a11.json'),('test-results/equipment-checks-a11.json','equipment-checks-a11.json')):
        shutil.copy2(ROOT/source,public/destination)
    for name,result in units.items():(public/(name+'-checks-a11.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    shutil.copytree(ROOT/'test-results/equipment-matrix-a11-final',ROOT/'assets/equipment-matrix-a11',dirs_exist_ok=True)
    shutil.copy2(ROOT/'test-results/equipment-matrix-a10-baseline/report.json',public/'equipment-matrix-baseline-a10.json')
    report={'passed':True,'version':__version__,'compiled_modules_match_current_source':matches,'theme_matches':True,
        'synthetic_checks':sum(counts.values()),'synthetic_groups':counts,'exe_real_selftest_checks':len(exe['checks']),
        'wheel_real_selftest_checks':len(wheel['selftest']['checks']),'wheel_source_matches':wheel['wheel_source_matches'],
        'real_equipment_matrix':replay['summary'],'same_fixture_pixels_as_a10':True,'real_desktop_capture':False,'real_game_fps_measured':False,
        'semantic_accuracy_scored':False,'own_model_and_workers_stopped':True,
        'user_equipment_image':{'single_capture_ocr':True,'layout_slots':user['layout_slots'],'full_qt_ms':user['results'][0]['full_qt_ms'],
            'weapon_art_pixels_unchanged':True,'large_power_number_pixels_unchanged':True,'screen_geometry_simulated':True},
        'exe_sha256':digest(bundle/'Babelander2.exe'),'wheel_sha256':digest(ROOT/'dist'/f'babelander_desktop-{__version__}-py3-none-any.whl'),
        'application_sha256':{p.name:digest(p) for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}}
    (public/'release-a11.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    (ROOT/'test-results/frozen-source-a11.json').write_text(json.dumps(report['application_sha256'],indent=2),encoding='utf8')
    print(json.dumps({'passed':True,'synthetic_checks':sum(counts.values()),'real_matrix_runs':96,'compiled_modules':len(matches),'exe_checks':len(exe['checks']),'wheel_checks':len(wheel['selftest']['checks'])}))
if __name__=='__main__':main()
