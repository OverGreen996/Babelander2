"""Seal a18 after actual source, EXE, wheel and quest replay verification."""
from pathlib import Path
import hashlib,json,shutil,html
from PyInstaller.archive.readers import ZlibArchiveReader
from release_snapshot import canonical
from babelander import __version__
ROOT=Path(__file__).parent
def read(name):return json.loads((ROOT/name).read_text(encoding='utf8'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    assert __version__=='2.0.0a18'
    frozen=read('test-results/frozen-source-a18.json')
    assert all(digest(ROOT/'babelander'/name)==value for name,value in frozen.items())
    archive=ZlibArchiveReader(str(ROOT/'build/work/Babelander2/PYZ-00.pyz'));compiled={}
    for path in (ROOT/'babelander').glob('*.py'):
        name='babelander' if path.stem=='__init__' else 'babelander.'+path.stem;code=archive.extract(name)
        compiled[name]=canonical(code)==canonical(compile(path.read_text(encoding='utf8'),code.co_filename,'exec',dont_inherit=True,optimize=0))
    assert all(compiled.values())
    exe=read('test-results/release-a18/exe.json');wheel=read('test-results/wheel.json')
    assert exe['passed'] and exe['frozen'] and exe['version']==__version__ and exe['qt_platform']=='offscreen'
    assert wheel['passed'] and wheel['selftest']['version']==__version__ and all(wheel['wheel_source_matches'].values())
    assert len(exe['checks'])==len(wheel['selftest']['checks'])==26
    files={'core':'unit-tests.json','assets':'asset-unit.json','pipeline':'pipeline.json','layout':'layout-unit.json',
           'equipment':'equipment-checks-a18.json','trigger':'subtitle-trigger-unit.json','accounting':'replay-accounting-a18.json',
           'numeric-recovery':'equipment-recovery-unit.json','window-focus':'window-focus-unit.json','preload':'preload-unit.json','quest':'quest-unit-a18.json'}
    units={name:read('test-results/'+file) for name,file in files.items()}
    assert all(r['passed'] for r in units.values())
    counts={name:r.get('tests_run',r.get('tests',0)) for name,r in units.items()};assert sum(counts.values())==334,counts
    quest=read('test-results/quest-a18/report.json');equipment=read('test-results/equipment-regression-a18/report.json')
    assert quest['passed'] and len(quest['runs'])==32 and len({f['pattern'] for f in quest['fixtures']})==8
    for report in (quest,equipment):
        assert report['application_source_unchanged'] and report['own_model_stopped'] and report['workers_stopped']
        assert report['application_sha256']=={k:v for k,v in frozen.items() if k.endswith('.py')}
        assert all(r['usable'] and r['single_capture_ocr'] for r in report['runs'])
    assert len(equipment['runs'])==20
    public=ROOT/'assets/verification';public.mkdir(exist_ok=True)
    for name,file in files.items():shutil.copy2(ROOT/'test-results'/file,public/(name+'-checks-a18.json'))
    for source,target in [('release-a18/exe.json','exe-selftest-a18.json'),('wheel.json','wheel-a18.json'),('wheel-selftest.json','wheel-selftest-a18.json'),('equipment-regression-a18/report.json','equipment-regression-a18.json')]:
        shutil.copy2(ROOT/'test-results'/source,public/target)
    destination=ROOT/'assets/quest-structures-a18'
    shutil.copytree(ROOT/'test-results/quest-a18',destination,dirs_exist_ok=True)
    # Static, local gallery with actual rendered outputs and explicit benchmark scope.
    parts=['<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>任務介面 · alpha18 實測</title><style>body{margin:0;background:#0e1620;color:#e9eef5;font:16px/1.7 system-ui}main{max-width:1280px;margin:auto;padding:40px 24px}h1{font-size:36px;line-height:1.3}p{color:#b9cadc}nav{display:flex;gap:12px;flex-wrap:wrap}a{color:#9cdbff}article{background:#182534;border:1px solid #314256;border-radius:14px;padding:22px;margin:28px 0}img{max-width:100%;height:auto;border-radius:8px}summary{cursor:pointer;padding:10px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 monospace}.tag{color:#ade8c0;background:#1d3b34;border-radius:20px;padding:3px 12px;font-size:14px}:focus-visible{outline:3px solid #a1d9ff;outline-offset:4px}@media(max-width:600px){main{padding:24px 14px}h1{font-size:28px}article{padding:14px}}</style><main><p>BABELANDER 2 · ALPHA 18</p><h1>任務在哪裡，譯文就在哪裡。</h1><p>8 種獨立結構、16 張不同內容，真 CPU OCR、本機 CUDA Qwen 與 Qt 原位覆蓋，兩輪共 32 次。左側原文、右側實際譯圖。只有驗證頁做對照，遊戲覆蓋只顯示譯文。</p><p>模型與 OCR 事先暖機；第一輪清快取一次、共用標籤可命中，第二輪保留翻譯快取。全卡平均 '+str(quest['summary'][0]['mean_result_ms'])+' / '+str(quest['summary'][1]['mean_result_ms'])+' ms。這是生成畫面回放，尚非真遊戲／FPS，也不是完整人工語意評分。</p><nav>']
    for f in quest['fixtures'][::2]:parts.append('<a href="#'+f['id']+'">'+html.escape(f['theme'])+'</a>')
    parts.append('</nav><p>人工抽查仍有短標題錯譯：Supply Run → 運輸運輸；Beyond the Walls → 遠離牆壁。以上檢查不涵蓋完整語意評分，詳見 <a href="../../TEST_REPORT_ALPHA18.md">品質限制報告</a>。</p>')
    for f in quest['fixtures']:
        runs=[r for r in quest['runs'] if r['id']==f['id']];r=runs[0]
        parts.append('<article id="'+f['id']+'"><h2>'+html.escape(f['theme'])+' <span class="tag">排版／數值通過</span></h2><p>'+html.escape(' · '.join(f['structural_features']))+'</p><p>首輪 '+str(r['full_qt_latency_ms'])+' ms · 重複 '+str(runs[1]['full_qt_latency_ms'])+' ms · 每輪擷取／OCR 各一次</p><img loading="lazy" src="'+f['id']+'-comparison.png" alt="'+html.escape(f['theme'])+' 原圖與實際原位譯文"><details><summary>幾何、字色與完整性證據</summary><pre>'+html.escape(json.dumps({k:r.get(k) for k in ('geometry','geometry_exact','source_complete','numbers_preserved','source_colors_preserved','art_unchanged','literal_pixels_unchanged','cross_panel_blocks')},ensure_ascii=False,indent=2))+'</pre></details></article>')
    parts.append('<p>單次卡片是靜態快照。遊戲更換任務、更新倒數或捲動後，請重新辨識；取消／還原會移除覆蓋。</p></main></html>')
    (destination/'gallery.html').write_text(''.join(parts),encoding='utf8')
    result={'version':__version__,'release_integrity_passed':True,'synthetic_checks':sum(counts.values()),'synthetic_groups':counts,
            'compiled_modules_match_current_source':compiled,'wheel_source_matches':wheel['wheel_source_matches'],
            'exe_real_checks':len(exe['checks']),'wheel_real_checks':len(wheel['selftest']['checks']),
            'quest_replay_runs':32,'quest_structures':8,'quest_fixtures':16,'quest_summary':quest['summary'],
            'cuda_offload_confirmed':quest['cuda_offload_confirmed'],'equipment_regression_runs':20,
            'semantic_accuracy_scored':False,'real_desktop_capture':False,'real_game_validated':False,'real_game_fps_measured':False,
            'new_model':False,'application_sha256':frozen,
            'exe_sha256':digest(ROOT/'dist/releases'/__version__/'Babelander2/Babelander2.exe'),
            'wheel_sha256':digest(ROOT/'dist'/f'babelander_desktop-{__version__}-py3-none-any.whl')}
    (public/'release-a18.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('application_sha256','compiled_modules_match_current_source','wheel_source_matches')},indent=2))
if __name__=='__main__':main()
