"""Seal a12 with explicit equipment failures; integrity is not all-case success."""
from pathlib import Path
import hashlib,json,shutil
from PyInstaller.archive.readers import ZlibArchiveReader
from release_snapshot import canonical
from babelander import __version__
ROOT=Path(__file__).parent
def read(name):return json.loads((ROOT/name).read_text(encoding='utf8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    assert __version__=='2.0.0a12'
    bundle=ROOT/'dist/releases'/__version__/'Babelander2'
    archive=ZlibArchiveReader(str(ROOT/'build/work/Babelander2/PYZ-00.pyz'))
    matches={}
    for p in (ROOT/'babelander').glob('*.py'):
        name='babelander' if p.stem=='__init__' else 'babelander.'+p.stem
        code=archive.extract(name)
        matches[name]=canonical(code)==canonical(compile(p.read_text(encoding='utf8'),code.co_filename,'exec',dont_inherit=True,optimize=0))
    assert all(matches.values())
    assert (bundle/'_internal/babelander/theme.qss').read_bytes()==(ROOT/'babelander/theme.qss').read_bytes()
    units={name:read('test-results/'+file) for name,file in [('core','unit-tests.json'),('assets','asset-unit.json'),('pipeline','pipeline.json'),('layout','layout-unit.json'),('equipment','equipment-checks-a12.json')]}
    assert all(r['passed'] for r in units.values())
    counts={name:r.get('tests_run',r.get('tests',r.get('checks',0))) for name,r in units.items()}
    assert sum(counts.values())==182,counts
    exe=read('test-results/release-a12/exe.json');wheel=read('test-results/wheel.json')
    assert exe['passed'] and exe['version']==__version__ and exe['frozen'] and exe['qt_platform']=='offscreen'
    assert wheel['passed'] and wheel['selftest']['version']==__version__ and all(wheel['wheel_source_matches'].values())
    replay=read('test-results/equipment-structures-a12-complete/report.json')
    palette=read('test-results/equipment-palette-a12-complete/report.json')
    for r in (replay,palette):
        assert r['completed'] and r['application_source_unchanged'] and r['own_model_stopped'] and r['workers_stopped']
        assert r['no_equipment_monitors'] and r['stop_hid_overlay'] and r['stop_released_backdrop']
        assert all(digest(ROOT/'babelander'/name)==value for name,value in r['application_sha256'].items())
    assert len(replay['fixtures'])==20 and len(replay['runs'])==60
    assert all(r['single_capture_ocr'] and r['geometry_exact'] and r['source_colors_preserved'] and r.get('art_unchanged') and not r['cross_panel_blocks'] for r in replay['runs'])
    assert all(r.get('usable') for r in palette['runs']) and len(palette['runs'])==32
    user_card=read('test-results/equipment-user-card-a12-complete.json')
    assert user_card['passed'] and user_card['own_model_stopped'] and user_card['workers_stopped'] and user_card['stop_restored']
    assert user_card['capture_calls']==user_card['ocr_calls']==1 and user_card['layout_slots']==24
    assert user_card['weapon_art_pixels_unchanged'] and user_card['large_power_number_pixels_unchanged']
    paragraphs=[x['source'] for x in user_card['results'][0]['translations']]
    assert "Heaven's Judgment" in paragraphs
    assert any('heavy attacks' in text and '20%' in text and '300%' in text and 'small area' in text for text in paragraphs)
    known=[]
    for r in replay['runs']:
        if not r.get('usable'):
            known.append({k:r.get(k) for k in ('id','pass','renderable','missing_source_words','missing_source_numbers','missing_target_numbers','render_warning')})
    public=ROOT/'assets/verification';public.mkdir(exist_ok=True)
    for name,result in units.items():(public/(name+'-checks-a12.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    for source,destination in [('test-results/release-a12/exe.json','exe-selftest-a12.json'),('test-results/wheel.json','wheel-a12.json'),('test-results/wheel-selftest.json','wheel-selftest-a12.json'),('test-results/equipment-palette-a12-complete/report.json','equipment-palette-regression-a12.json')]:
        shutil.copy2(ROOT/source,public/destination)
    shutil.copytree(ROOT/'test-results/equipment-structures-a12-complete',ROOT/'assets/equipment-structures-a12',dirs_exist_ok=True)
    shutil.copy2(ROOT/'assets/equipment-game-structures-preview/overview.png',ROOT/'assets/equipment-structures-a12/overview.png')
    report={'release_integrity_passed':True,'version':__version__,'synthetic_checks':sum(counts.values()),'synthetic_groups':counts,
        'compiled_modules_match_current_source':matches,'wheel_source_matches':wheel['wheel_source_matches'],
        'exe_real_selftest_checks':len(exe['checks']),'wheel_real_selftest_checks':len(wheel['selftest']['checks']),
        'real_equipment_structures':replay['summary'],'all_equipment_cases_passed':not known,'known_equipment_failures':known,
        'all_60_source_color_checks_passed':True,'all_60_artwork_pixel_checks_passed':True,'palette_regression_passed':32,
        'source_color_block_checks':sum(len(r['source_color_checks']) for r in replay['runs']),
        'user_card_artwork_numbers_and_paragraph_boundaries_passed':True,
        'real_desktop_capture':False,'semantic_accuracy_scored':False,'real_game_fps_measured':False,
        'own_model_and_workers_stopped':True,'exe_sha256':digest(bundle/'Babelander2.exe'),
        'wheel_sha256':digest(ROOT/'dist'/f'babelander_desktop-{__version__}-py3-none-any.whl'),
        'application_sha256':{p.name:digest(p) for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}}
    (public/'release-a12.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    (ROOT/'test-results/frozen-source-a12.json').write_text(json.dumps(report['application_sha256'],indent=2),encoding='utf8')
    print(json.dumps({'integrity':True,'unit_checks':sum(counts.values()),'equipment_usable':sum(r.get('usable',False) for r in replay['runs']),'equipment_runs':60,'known_failures':len(known)}))
if __name__=='__main__':main()
