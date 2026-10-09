"""Seal measured a23 fixes and reject recall-regressing detector changes."""
from pathlib import Path
import json,hashlib,shutil,zipfile
import numpy as np
from babelander import __version__
ROOT=Path(__file__).resolve().parent
PUBLIC=ROOT/'assets/verification/chat-noise-a23'
def read(name):return json.loads((ROOT/name).read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stats(rows):
 values=[r['shown_to_qt_ms'] for r in rows]
 return {'n':len(values),'mean_ms':float(np.mean(values)),'p50_ms':float(np.median(values)),
         'p95_ms':float(np.percentile(values,95)),'max_ms':max(values),'within700':sum(v<=700 for v in values)}
assert __version__=='2.0.0a23'
actual={p.name:sha(p) for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}
units=read('test-results/supertest-a23/runner-units.json')
assert units['application_sha256']==actual and units['source_unchanged']
assert len(units['runs'])==14 and sum(r['tests_run'] or 0 for r in units['runs'])==432 and all(r['returncode']==0 for r in units['runs'])
paths={'animated-0':'test-results/chat-fixed-a23-final/0-100.json',
       'legacy-chat':'test-results/chat-fixed-a23-final/1-100.json',
       'animated-2':'test-results/chat-fixed-a23-final/2-100.json',
       'animated-four-threads':'test-results/chat-fixed-a23-final/3-100.json',
       'clean':'test-results/chat-clean-a23/0-100.json',
       'units':'test-results/supertest-a23/runner-units.json',
       'weak-flash':'test-results/a23-weak-flash.json','chat-events':'test-results/a23-chat-events/report.json',
       'ocr-edges':'test-results/chat-ocr-edges-a23.json','modes':'test-results/a23-modes/report.json',
       'detector-scale':'test-results/chat-detector-scale-a23.json',
       'exe':'test-results/supertest-a23/exe.json','wheel':'test-results/supertest-a23/wheel.json',
       'soak':'test-results/supertest-a23/soak.json','resources':'test-results/supertest-a23/resources.json',
       'acceptance-runner':'test-results/a23-acceptance/runner.json'}
data={name:read(path) for name,path in paths.items()}
for key in ('animated-0','animated-2','animated-four-threads','clean'):
 r=data[key];assert r['passed'] and r['source_unchanged'] and r['source_sha256']==actual
 assert r['model_stayed_warm'] and r['owned_model_stopped'] and r['workers_stopped'] and r['sessions_cleared']
 assert r['sqlite_rows']=={'cache':0,'history':0,'usage':0}
legacy=data['legacy-chat'];assert legacy['legacy_chat'] and legacy['source_sha256']==actual and not legacy.get('fatal_error') and not legacy['errors']
assert data['modes']['overall_passed'] and len(data['modes']['checks'])==28
assert data['chat-events']['passed'] and data['ocr-edges']['passed'] and data['weak-flash']['recall_not_worse']
assert data['exe']['passed'] and data['wheel']['passed'] and len(data['exe']['checks'])==37 and len(data['wheel']['selftest']['checks'])==37
assert data['soak']['passed'] and data['resources']['passed'] and data['acceptance-runner']['passed']
noise=stats(data['animated-0']['results']+data['animated-2']['results']);clean=stats(data['clean']['results']);four=stats(data['animated-four-threads']['results'])
unknown=[r for r in legacy['results'] if r['index'] is None]
assert unknown and all(r['source']=='■' for r in unknown)
PUBLIC.mkdir(parents=True,exist_ok=True)
for name,path in paths.items():shutil.copy2(ROOT/path,PUBLIC/(name+'.json'))
summary={'version':__version__,'application_sha256':actual,'regressions':432,'groups':14,
 'clean':clean,'animated_default_two_threads':noise,'animated_optional_four_threads':four,
 'legacy_chat':{'delivered_real_messages':100-len(legacy['missing']),'missing':legacy['missing'],'false_square_results':len(unknown),'all_results':len(legacy['results'])},
 'animated_runs':[{'round':r['round'],'threads':r.get('ocr_threads',2),'cpu_core_seconds':r['cpu_core_seconds'],'ocr_calls':len(r['ocr']),
                   'decorations_removed':sum(o['decorations'] for o in r['ocr']),'latency':stats(r['results'])} for r in (data['animated-0'],data['animated-2'],data['animated-four-threads'])],
 'weak_flash_ms':[r['events'][0]['shown_to_qt_ms'] for r in data['weak-flash']['runs']],
 'detector_scale_decision':'Rejected: 960 and 736 caps lose baseline-recognizable dim 11px and 14px text on 1440px ROI.',
 'modes_checks':28,'ocr_edges_checks':len(data['ocr-edges']['checks']),'exe_checks':37,'wheel_checks':37,
 'resource_acceptance':data['resources']['resource_acceptance'],'soak_seconds':data['soak']['duration_seconds'],
 'real_game_validated':False,'semantic_accuracy_scored':False,'real_desktop_capture':False,'foreground_control_calls':0,'paid_api_calls':0,
 'all_latency_under700':noise['within700']==noise['n'] and clean['within700']==clean['n'],
 'scope':'Generated images -> real CPU PP-OCRv6 Small -> warm CUDA Qwen -> Qt update, 900ms independent exposures, four visible chat messages. CPU core seconds exclude llama-server child. Default 2 threads retained. No game FPS or CPU/RAM savings claim.'}
(PUBLIC/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
rows=[]
for name,item in (('乾淨背景／2 執行緒',clean),('動態背景／2 執行緒／兩輪',noise),('動態背景／4 執行緒／一輪',four)):
 rows.append(f"| {name} | {item['n']} | {item['mean_ms']:.2f}ms | {item['p95_ms']:.2f}ms | {item['max_ms']:.2f}ms | {item['within700']}/{item['n']} |")
report=f"""# alpha23：修正背景假字與聊天重複翻譯

正式程式修正兩項聊天問題：以相對文字尺寸排除微小獨立幾何裝飾；聊天捲動比對容忍有周圍訊息佐證的簡繁字形、字元交界標點與雜引號抖動。原始 OCR 與使用者翻譯內容不被改寫，原文仍可在既有核對工具查看，浮窗維持目前譯文排版。沒有加入額外模型、OCR 引擎或背景擷取執行緒。

## 動態背景功能對照

相同五種聊天結構、100 則一般跨遊戲訊息，中英混合、x4/x5/x6、否定句、長句換行、重複 GG；加入像素抖動、波浪光影、半透明光影與移動粒子。每則曝光 900ms，保留最近四則。使用真 CPU OCR、暖本機 CUDA 模型與 Qt offscreen；沒有操控前景、抓使用者桌面或呼叫付費 API。

測試工具修正了兩件事：動畫 phase 對齊每則曝光；區塊結束等實際監測週期、翻譯佇列與 UI 清空，不再用結果筆數假裝排空。首輪工具收尾錯誤已保留於 acceptance-runner 的 prior_failed_attempts；修正後乾淨回放重新執行通過。

- 封存 alpha22 聊天比對邏輯加原本未過濾裝飾的路徑，在新版測試工具下收到 **{100-len(legacy['missing'])}/100** 則真正訊息，另外產生 **{len(unknown)} 筆 ■ 假字**。這是同一 OCR／排程的舊聊天邏輯注入對照，並非重測舊 EXE。
- alpha23 三輪動態回放各 **100/100**，沒有漏訊息、重複或假字，target 非空且沒有護欄拒絕。這不是 100% 語意正確率。
- 正常大小的幾何符號、帶說話者的符號、數字、英文縮寫、標點、表情、缺少幾何資料的行均保留。只有相對中位文字字高不到一半、寬度小於 1.2 倍字高的獨立幾何字形才排除；沒有亮度或信心門檻。
- 捲動比對至少需要兩行相符佐證；孤立訊息仍嚴格比較，數量、否定詞、問號變動及新追加的相同 GG 不被這些規則吃掉。適用一般新增／捲動聊天，不宣稱可辨識所有原地編輯。

## 完整譯文延遲

起點為生成畫面實際切換，終點為 Qt 接收並更新完整譯文；包含觀察等待、OCR、翻譯與 UI 傳遞，不包含真遊戲／螢幕掃描顯示時間。模型先暖機，切換畫面樣式保留同一模型，沒有預先餵入預期翻譯。

| 場景 | 訊息 | 平均 | P95 | 最大 | 700ms 內 |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

2 執行緒兩輪個別平均 {summary['animated_runs'][0]['latency']['mean_ms']:.2f}／{summary['animated_runs'][1]['latency']['mean_ms']:.2f}ms，顯示本輪延遲有明顯波動；其他程式負載未隔離，不把差異全歸因於單一改動。沒有全數達到 700ms。4 執行緒 CPU 工作為 {summary['animated_runs'][2]['cpu_core_seconds']:.2f} 核心秒，2 執行緒兩輪為 {summary['animated_runs'][0]['cpu_core_seconds']:.2f}／{summary['animated_runs'][1]['cpu_core_seconds']:.2f} 核心秒；這是應用程序 CPU 時間，獨立 llama-server 未計入。沒有據此宣稱 CPU、RAM 或遊戲 FPS 改善，也沒有自動改寫使用者設定，產品仍預設 2 執行緒。

只出現約 200ms、RGB(30,34,40) 在 RGB(16,20,26) 背景的新暗字兩次都收到，完整更新 {summary['weak_flash_ms'][0]:.2f}／{summary['weak_flash_ms'][1]:.2f}ms。這個先前抗雜訊觸發器漏掉的反例仍保留作驗收。

## 沒採用的加速

檢查固定 RapidOCR 3.9.2 原始碼發現，max 模式使用動態上限而不是配置中的 limit_side_len。以同一 OCR 測試完整、960、736、完整上限，共 108 個畫面／輪；縮圖雖較快，卻讓原版可讀的 11px 與 14px 暗字整組消失。736 另出現中文斷行／缺字。**兩個縮圖方案均未進產品**；上輪會漏 200ms 暗字的文字特徵觸發器也維持停用。

## 驗收與資源回收

- 14 組 **432 項回歸**通過，含新增裝飾過濾、字形抖動、數量／否定／問號及監測事件測試。
- 六模式循序／並行、單次裝備／任務卡、原位大小、停止及模型崩潰恢復 **28 項**通過。
- 真 OCR 邊界 **32 項**、聊天追加／重複事件 **8 項**、暗字短訊息兩輪通過。
- 實際 EXE 與隔離安裝 wheel 各 **37 項**自檢通過；封裝 EXE 背景長跑約 **{summary['soak_seconds']:.0f} 秒**、資源漂移與停止釋放驗收通過。這是固定生成字幕長跑；不是所有遊戲的記憶體洩漏證明。
- 私人聊天的 SQLite cache／history／usage 均為零，監測 worker、OCR session cache 與測試自有模型均回收。

## 仍需突破的部分

目前安全修正的是假字污染與重複事件；動態背景仍頻繁完整 OCR，CPU 成本沒有根治，慢速尾端尚未穩定壓進 700ms。下一個加速方案必須同時守住小字／暗字／短暫新行，並以固定曝光與完整譯文的 P95 驗收。真遊戲 FPS、不同解析度與字型、遊戲原位覆蓋相容性及全面語意品質尚未實測。本輪沒有擴大核心模型或新增功能。

[完整原始數據與摘要](assets/verification/chat-noise-a23/summary.json)。alpha22 EXE／原始碼封存保留；alpha23 可編輯原始碼另備份於 dist/Babelander2-2.0.0a23-source.zip。
"""
(ROOT/'TEST_REPORT_ALPHA23.md').write_text(report,encoding='utf8')
p=ROOT/'README.md';text=p.read_text(encoding='utf8').replace('Windows OCR 翻譯工作臺 · 2.0.0 alpha 22','Windows OCR 翻譯工作臺 · 2.0.0 alpha 23')
banner=f"**alpha23 動態聊天修正：** 粒子假字與字形抖動不再污染本輪聊天室；三輪動態回放各 100/100，無漏訊息、重複或假字。乾淨背景平均 {clean['mean_ms']:.0f}ms；動態背景兩輪平均 {noise['mean_ms']:.0f}ms、P95 {noise['p95_ms']:.0f}ms，仍未全數達 700ms。432 項回歸及 EXE／wheel 驗證通過，會漏暗字的縮圖方案未採用。[完整驗證與限制](TEST_REPORT_ALPHA23.md)。"
if '**alpha23 動態聊天修正：**' not in text:text=text.replace('## 六種閱讀情境',banner+'\n\n## 六種閱讀情境',1)
p.write_text(text,encoding='utf8')
p=ROOT/'CHANGELOG.md';text=p.read_text(encoding='utf8')
if not text.startswith('# 2.0.0a23'):
 text='# 2.0.0a23 · 抗粒子假字與聊天去重\n\n- 排除相對文字顯著過小的獨立幾何裝飾，保留正常符號、數字、表情與未知幾何資料。\n- 聊天捲動比對在周圍訊息佐證下容忍簡繁字形及交界標點抖動；保留數量、否定與問號變動。\n- 動態測試改為真正工作排空與相對動畫時鐘；三輪各 100 則零漏讀／重複／假字。\n- 432 項回歸、六模式／崩潰恢復、暗字短訊息、EXE／wheel 及五分鐘長跑通過。700ms 尚未全面達標；漏暗字的縮圖候選未採用。[完整證據](TEST_REPORT_ALPHA23.md)。\n\n'+text
p.write_text(text,encoding='utf8')
p=ROOT/'ARCHITECTURE.md';text=p.read_text(encoding='utf8')
if '## alpha23 聊天事件品質' not in text:
 text+='\n\n## alpha23 聊天事件品質\n\n完整 OCR 之後、跨行聊天組裝之前，依本張圖片的文字中位字高排除微小獨立幾何裝飾；raw evidence 仍保留原始辨識結果。chat_decorations_filtered 的計數代表含被排除裝飾的 OCR 幀數，recent.count 是該幀符號數，不是全程累計字數。聊天捲動比對僅在至少兩行佐證下容忍簡繁字形與交界標點抖動，沒有全域文字去重，也沒有保存私人文字的新快取。OpenCC 比對轉換器只快取一份固定詞典，不快取聊天內容。偵測器縮圖與舊抗雜訊觸發器均未採用，原始全區偵測與停止回收政策保留。\n'
p.write_text(text,encoding='utf8')
p=ROOT/'TEST_REPORT.md';text=p.read_text(encoding='utf8')
if '**alpha23 動態聊天修正：**' not in text:
 text=text.replace('# alpha8 驗證紀錄','# 驗證紀錄',1)
 text=text.replace('# 驗證紀錄','# 驗證紀錄'+"\n\n"+banner,1)
 text=text.replace('最新 alpha18：','歷史 alpha18：',1)
p.write_text(text,encoding='utf8')
p=ROOT/'SUPERTEST.md';text=p.read_text(encoding='utf8')
if '## alpha23 修正範圍驗收' not in text:
 text+="\n\n## alpha23 修正範圍驗收\n\n執行 `.venv/Scripts/python.exe run_a23_verification.py`，依序驗證 432 項回歸、真 OCR 邊界、200ms 暗字、重複聊天事件、六模式並行／崩潰恢復、乾淨與動態聊天、4 執行緒候選、EXE／wheel 和五分鐘背景長跑。全部使用生成畫面與本機引擎，不呼叫付費 API或操控桌面；並非重測所有歷史卡片矩陣或所有遊戲。完整範圍與未達標數據見 [alpha23](TEST_REPORT_ALPHA23.md)。封存器 `finalize_release_a23.py` 要求對照原始數據齊備且目前程式 SHA 一致，才建立備份；它不代替測試。\n"
p.write_text(text,encoding='utf8')
from release_snapshot import main
main()
artifacts=read('test-results/artifacts.json')
assert artifacts['passed'] and all(artifacts['compiled_modules_match_current_source'].values())
manifest=ROOT/'dist/Babelander2-2.0.0a23-sha256.json'
manifest.write_text(json.dumps({**artifacts,'regressions':432,'exe_checks':37,'wheel_checks':37,'acceptance':summary},ensure_ascii=False,indent=2),encoding='utf8')
with zipfile.ZipFile(ROOT/'dist/Babelander2-2.0.0a23-source.zip') as backup:
 assert all(hashlib.sha256(backup.read('Babelander2/'+name)).hexdigest()==digest for name,digest in artifacts['source_files'].items())
print(json.dumps({'release_integrity_passed':True,'source_files':len(artifacts['source_files']),'exe_sha256':artifacts['exe_sha256'],'source_zip_sha256':artifacts['source_zip_sha256'],'summary':{'clean':clean,'noise':noise,'four_threads':four}}))
