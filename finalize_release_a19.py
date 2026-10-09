"""Seal chat evidence with actual source/bundle/wheel provenance."""
from pathlib import Path
import json,hashlib,shutil,html
from PyInstaller.archive.readers import ZlibArchiveReader
from release_snapshot import canonical
from babelander import __version__
ROOT=Path(__file__).resolve().parent
def read(name):return json.loads((ROOT/name).read_text(encoding='utf8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    assert __version__=='2.0.0a19'
    frozen=read('test-results/frozen-source-a19.json')
    assert all(digest(ROOT/'babelander'/name)==value for name,value in frozen.items())
    archive=ZlibArchiveReader(str(ROOT/'build/work/Babelander2/PYZ-00.pyz'));compiled={}
    for path in (ROOT/'babelander').glob('*.py'):
        name='babelander' if path.stem=='__init__' else 'babelander.'+path.stem;code=archive.extract(name)
        compiled[name]=canonical(code)==canonical(compile(path.read_text(encoding='utf8'),code.co_filename,'exec',dont_inherit=True,optimize=0))
    assert all(compiled.values())
    exe=read('test-results/release-a19/exe.json');wheel=read('test-results/wheel.json')
    assert exe['passed'] and exe['frozen'] and exe['version']==__version__ and exe['qt_platform']=='offscreen'
    assert wheel['passed'] and wheel['selftest']['version']==__version__ and all(wheel['wheel_source_matches'].values())
    assert len(exe['checks'])==len(wheel['selftest']['checks'])==30
    files={'core':'unit-tests.json','assets':'asset-unit.json','pipeline':'pipeline.json','layout':'layout-unit.json',
           'equipment':'equipment-checks-a19.json','trigger':'subtitle-trigger-unit.json','accounting':'replay-accounting-a19.json',
           'numeric-recovery':'equipment-recovery-unit.json','window-focus':'window-focus-unit.json','preload':'preload-unit.json',
           'quest':'quest-unit-a19.json','chat':'chat-unit-a19.json'}
    units={name:read('test-results/'+file) for name,file in files.items()}
    assert all(r['passed'] for r in units.values())
    counts={name:r.get('tests_run',r.get('tests',0)) for name,r in units.items()};assert sum(counts.values())==374,counts
    chat=read('test-results/chat-a19-ui-final/report.json');events=read('test-results/chat-events-a19/report.json')
    assert chat['completed'] and chat['source_unchanged'] and chat['source_sha256']==frozen
    assert chat['owned_model_stopped'] and chat['workers_stopped'] and chat['cuda_offload_confirmed']
    assert len(chat['text_rows'])==len(chat['live_results'])==100 and not chat['errors']
    assert not chat['live_summary']['missing_message_indices'] and not chat['live_summary']['duplicated_message_indices']
    assert chat['sqlite_rows']=={'cache':0,'history':0,'usage':0} and events['passed']
    public=ROOT/'assets/verification';public.mkdir(exist_ok=True)
    for name,file in files.items():shutil.copy2(ROOT/'test-results'/file,public/(name+'-checks-a19.json'))
    for source,target in [('release-a19/exe.json','exe-selftest-a19.json'),('wheel.json','wheel-a19.json'),('wheel-selftest.json','wheel-selftest-a19.json')]:shutil.copy2(ROOT/'test-results'/source,public/target)
    destination=ROOT/'assets/chat-a19';shutil.copytree(ROOT/'test-results/chat-a19-ui-final',destination,dirs_exist_ok=True)
    shutil.copytree(ROOT/'test-results/chat-events-a19',destination/'events',dirs_exist_ok=True)
    parts=['''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>通用遊戲聊天 · alpha19</title><style>body{margin:0;background:#0e1620;color:#e9eef5;font:16px/1.7 system-ui}main{max-width:1280px;margin:auto;padding:40px 24px}h1{font-size:36px;line-height:1.3}p{color:#b9cadc}a{color:#9cdbff}article{background:#182534;border:1px solid #314256;border-radius:14px;padding:22px;margin:28px 0}img{max-width:100%;height:auto;border-radius:8px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}summary{cursor:pointer;padding:10px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 monospace}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border-bottom:1px solid #314256;text-align:left;padding:10px;vertical-align:top;overflow-wrap:anywhere}.table{overflow:auto}.warn{color:#ffe0a6}nav{display:flex;gap:16px;flex-wrap:wrap}:focus-visible{outline:3px solid #a1d9ff;outline-offset:4px}@media(max-width:800px){.pair{grid-template-columns:1fr}main{padding:24px 14px}h1{font-size:28px}}</style><main><p>BABELANDER 2 · ALPHA 19</p><h1>數量要準。GG 就留 GG。</h1><p>100 則通用遊戲聊天，五種聊天室樣式；真 CPU OCR、本機 CUDA Qwen、正式監測流程與 Qt 浮層。所有畫面由測試自行產生，沒有佔用桌面或讀取私人聊天室。</p><nav><a href="#frames">聊天室畫面</a><a href="#events">重複與突發</a><a href="#messages">100 句結果</a><a href="../../TEST_REPORT_ALPHA19.md">測試範圍與限制</a></nav>''']
    summary=chat['live_summary']
    parts.append('<p>100 則均收到，無重複；'+str(summary['no_warning'])+' 則產生譯文。畫面出現至 Qt 回傳平均 '+str(summary['fixture_shown_to_qt']['mean_ms'])+' ms、P95 '+str(summary['fixture_shown_to_qt']['p95_ms'])+' ms；包含 800ms 輪詢等待，所有回傳包含護欄拒絕。模型與 OCR 已暖機。</p>')
    parts.append('<p class="warn">護欄通過不等於語意正確。人工抽查仍有 Party full? → 黨滿了？、Save one potion for me → 儲存一個藥水來我，以及 Focus the healer first 遺漏 first 等問題。尚未達到 700ms 完整反應目標，也不是實際遊戲 FPS 測試。</p><div id="frames">')
    for index,title in [(19,'隊伍：物資／GG'),(39,'對戰：戰術／倒數'),(59,'合作：座標／斷線'),(79,'公會：中英混合'),(96,'精簡：長句換行'),(99,'精簡：最後一則 GG')]:
        source=f'chat-{index+1:03d}-original.png';target=f'chat-{index+1:03d}-translated.png'
        parts.append('<article><h2>'+html.escape(title)+'</h2><div class="pair"><figure><img loading="lazy" src="'+source+'" alt="自製聊天室原畫面"><figcaption>原圖</figcaption></figure><figure><img loading="lazy" src="'+target+'" alt="真 OCR 和翻譯後的 Qt 聊天室浮層"><figcaption>實際 Qt 譯文，最新訊息在底端</figcaption></figure></div></article>')
    parts.append('</div><article id="events"><h2>同一個人再次傳 GG，也要顯示。</h2><p>同一說話者完全相同的 GG 連續兩次、再同時新增四則訊息。FIFO 順序、保留英文縮寫、靜止不重複、最新訊息可見與 SQLite 不留聊天紀錄全部通過；這組短語不需要載入 Qwen。</p><div class="pair"><img loading="lazy" src="events/original.png" alt="重複 GG 與四則新增訊息原畫面"><img loading="lazy" src="events/translated.png" alt="真 Qt 顯示兩次 GG 並依序保留新增縮寫"></div></article><h2 id="messages">100 句文字請求實際輸出</h2><p>以下是文字測試，不含 OCR；完整 OCR 原文、事件、計時與字元差異見 <a href="report.json">回放 JSON</a>。表格的英文只用於自製驗證頁對照，不會雙語並排在遊戲浮層。</p><div class="table"><table><thead><tr><th scope="col">#</th><th scope="col">輸入</th><th scope="col">實際輸出／護欄原因</th><th scope="col">請求 ms</th></tr></thead><tbody>')
    for row in chat['text_rows']:parts.append('<tr><td>'+str(row['index']+1)+'</td><td>'+html.escape(row['source'])+'</td><td'+(' class="warn"' if row['warning'] else '')+'>'+html.escape(row['target'] or row['warning'])+'</td><td>'+str(row['request_ms'])+'</td></tr>')
    parts.append('</tbody></table></div></main></html>');(destination/'gallery.html').write_text(''.join(parts),encoding='utf8')
    result={'version':__version__,'release_integrity_passed':True,'synthetic_checks':sum(counts.values()),'synthetic_groups':counts,
            'compiled_modules_match_current_source':compiled,'wheel_source_matches':wheel['wheel_source_matches'],
            'exe_real_checks':len(exe['checks']),'wheel_real_checks':len(wheel['selftest']['checks']),
            'chat_text_summary':chat['text_summary'],'chat_live_summary':summary,'chat_event_checks':events['checks'],
            'cuda_offload_confirmed':chat['cuda_offload_confirmed'],'semantic_accuracy_scored':False,
            'real_game_validated':False,'real_desktop_capture':False,'application_sha256':frozen,
            'exe_sha256':digest(ROOT/'dist/releases'/__version__/'Babelander2/Babelander2.exe'),
            'wheel_sha256':digest(ROOT/'dist'/f'babelander_desktop-{__version__}-py3-none-any.whl')}
    (public/'release-a19.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('application_sha256','compiled_modules_match_current_source','wheel_source_matches')},indent=2))
if __name__=='__main__':main()
