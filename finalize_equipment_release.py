"""Check the final alpha9 bundle/test evidence before sealing source backup."""
from pathlib import Path
import hashlib
import json
import shutil
from PyInstaller.archive.readers import ZlibArchiveReader
from release_snapshot import canonical
from babelander import __version__

ROOT=Path(__file__).resolve().parent
def read(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    assert __version__=='2.0.0a9'
    bundle=ROOT/'dist/releases'/__version__/'Babelander2'
    archive=ZlibArchiveReader(str(ROOT/'build/work/Babelander2/PYZ-00.pyz'))
    matches={}
    for path in (ROOT/'babelander').glob('*.py'):
        name='babelander' if path.stem=='__init__' else 'babelander.'+path.stem
        code=archive.extract(name)
        matches[name]=canonical(code)==canonical(compile(path.read_text(encoding='utf-8'),code.co_filename,'exec',dont_inherit=True,optimize=0))
    assert all(matches.values()),matches
    theme_matches=(bundle/'_internal/babelander/theme.qss').read_bytes()==(ROOT/'babelander/theme.qss').read_bytes()
    assert theme_matches
    units={name:read('test-results/'+filename) for name,filename in (
        ('core','unit-tests.json'),('assets','asset-unit.json'),('pipeline','pipeline.json'),
        ('layout','layout-unit.json'),('equipment','equipment-checks-a9.json'))}
    assert all(result['passed'] for result in units.values())
    count=sum(result.get('tests_run',result.get('tests',result.get('checks',0))) for result in units.values())
    assert count==146,count
    exe=read('test-results/release-a9/exe.json');wheel=read('test-results/wheel.json')
    assert exe['passed'] and exe['version']==__version__ and exe['frozen'] and exe['qt_platform']=='offscreen'
    assert wheel['passed'] and wheel['selftest']['version']==__version__ and all(wheel['wheel_source_matches'].values())
    replay=read('test-results/equipment-real-a9.json')
    assert replay['completed'] and replay['own_model_stopped'] and replay['workers_stopped'] and replay['capture_and_dispatchers_stopped']
    assert replay['blank_cleared'] and replay['stop_hid_overlay']
    assert all(digest(ROOT/'babelander'/name)==value for name,value in replay['application_sha256'].items())
    public=ROOT/'assets/verification';public.mkdir(exist_ok=True)
    for source,destination in (('test-results/release-a9/exe.json','exe-selftest-a9.json'),
        ('test-results/wheel.json','wheel-a9.json'),('test-results/wheel-selftest.json','wheel-selftest-a9.json'),
        ('test-results/equipment-checks-a9.json','equipment-checks-a9.json'),('test-results/equipment-real-a9.json','equipment-real-a9.json')):
        shutil.copy2(ROOT/source,public/destination)
    report={'passed':True,'version':__version__,'compiled_modules_match_current_source':matches,
        'theme_matches':theme_matches,'synthetic_checks':count,
        'synthetic_groups':{name:result.get('tests_run',result.get('tests',result.get('checks',0))) for name,result in units.items()},
        'exe_real_selftest_checks':len(exe['checks']),'wheel_real_selftest_checks':len(wheel['selftest']['checks']),
        'wheel_source_matches':wheel['wheel_source_matches'],'real_equipment_replay':replay['summary'],
        'real_desktop_capture':False,'real_game_fps_measured':False,'semantic_accuracy_scored':False,
        'own_model_and_workers_stopped':True,'exe_sha256':digest(bundle/'Babelander2.exe'),
        'wheel_sha256':digest(ROOT/'dist'/f'babelander_desktop-{__version__}-py3-none-any.whl'),
        'application_sha256':{p.name:digest(p) for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}}
    (public/'release-a9.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'test-results/frozen-source-a9.json').write_text(json.dumps(report['application_sha256'],indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'synthetic_checks':count,'compiled_modules':len(matches),
        'exe_checks':len(exe['checks']),'wheel_checks':len(wheel['selftest']['checks'])}))

if __name__=='__main__':main()
