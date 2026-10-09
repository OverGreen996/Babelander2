"""Preserve the full two-phase alpha8 moving-background comparison."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'assets/verification'
raw=ROOT/'test-results/moving-background-a8-line-ab/results.json'
report=json.loads(raw.read_text(encoding='utf-8'))
assert report['version']=='2.0.0a8' and report['completed'] and report['source_unchanged']
assert report['owned_model_stopped'] and report['workers_stopped']
assert all(hashlib.sha256((ROOT/'babelander'/name).read_bytes()).hexdigest()==sha for name,sha in report['application_source_sha256'].items())
control,fast=(report['phases'][name] for name in ('moving_control','moving_line_reuse'))
assert all(p['summary']['sentences_presented']==100 and p['monitor_drained'] and not p['errors'] for p in (control,fast))
OUT.mkdir(parents=True,exist_ok=True)
shutil.copy2(raw,OUT/'moving-background-a8-line-ab.json')
adversarial=json.loads((ROOT/'test-results/layout-adversarial-a8.json').read_text(encoding='utf-8'))
assert adversarial['source_matches_frozen'] and not adversarial['all_fast_match_full']
shutil.copy2(ROOT/'test-results/layout-adversarial-a8.json',OUT/'layout-adversarial-a8.json')
(OUT/'frozen-source-a8.json').write_text(json.dumps(report['application_source_sha256'],indent=2),encoding='utf-8')
def cell(phase,key):return str(phase['summary'][key])
def timing(phase,key,part):
    value=phase['summary'][key]
    return str(value[part]) if value else 'N/A'
rows=[]
for title,key in [('700 ms 內完整 Qt 譯文／100（嚴格原文匹配）','usable_display_within_700_ms'),
                  ('700 ms 內完整 Qt 譯文／100（句尾句點容差）','period_tolerant_display_within_700_ms'),
                  ('完全匹配 OCR 至少看到一次／100','exact_ocr_seen'),('3 秒內可用完整 Qt 譯文／100','usable_display_within_3_seconds'),
                  ('OCR 次數','ocr_calls'),('模型請求','backend_requests'),('cache hit','cache_hits'),
                  ('護欄拒絕次數','guard_rejections'),('字幕切換後才顯示的結果','display_after_sentence_changed'),
                  ('OCR 工作總耗時 ms','ocr_wall_work_ms'),('CPU seconds，包含 fixture','cpu_seconds_including_fixture')]:
    rows.append(f'| {title} | {cell(control,key)} | {cell(fast,key)} |')
for title,key,part in [('完整 Qt 譯文平均 ms','display_latency','mean_ms'),('P50 ms','display_latency','p50_ms'),
                       ('P95 ms','display_latency','p95_ms'),('Max ms','display_latency','max_ms'),
                       ('平均 ms（句尾句點容差）','period_tolerant_display_latency','mean_ms'),
                       ('OCR 平均 ms','ocr_call_latency','mean_ms'),('OCR P95 ms','ocr_call_latency','p95_ms')]:
    rows.append(f'| {title} | {timing(control,key,part)} | {timing(fast,key,part)} |')
paths=Counter(r.get('path','full') for r in fast['ocr'])
reasons=Counter(r.get('reason','unknown') for r in fast['ocr'] if r.get('path')=='full')
details=[]
for case in fast['outcomes']:
    ms=case['display_latency_ms']
    if ms is None or ms>700:
        source=report['corpus'][case['case_id']-1]['text']
        details.append(f"| {case['case_id']} | {round(ms,2) if ms is not None else '未取得'} | {source} |")
text='''# alpha8：100 句動態背景、字幕行重用對照

**結論：目前不建議開啟。** 完整反應時間沒有證明收益，開啟輪平均與 P95 更差；另有實際高信心混色截字。功能預設保持關閉。即使早期 OCR-only 平均下降，也不能當成完整翻譯變快。

2026-10-08。兩輪各 100 句，每句 3 秒；同一程序、相同資料與背景 seed，先 control、再開啟行重用。不是隨機交錯的乾淨硬體 A/B，背景系統負載可變；不能只把差值當成改動的因果效果。

真實 PP-OCRv6 Small／ONNX CPU（4 threads）、Qwen3 1.7B Q4_K_M／CUDA、Qt offscreen。兩輪同樣開啟實驗性自適應複查，stable=100 ms、dialog scan=100 ms。模型先暖機，每輪清空 SQLite cache，新 session 不沿用行位置提示。

1450×250、Arial 30 pt、白字黑邊；背景目標 20 FPS 持續變動、無文字背板。合成 capture 取代 GDI。時間從測試文字出現到完整 Qt 更新，包含取樣與穩定確認；不是單看模型時間，也不是螢幕像素呈現時間。

## 實際結果

| 指標 | 行重用關閉 | 行重用開啟 |
| --- | --- | --- |
'''+ '\n'.join(rows)+f'''

可用譯文意指有完整目標文字、沒有護欄警告且原文歸屬匹配；**不是人工語意正確率**。平均／P95 的分母只包含該規則下顯示成功的句子，700 ms 覆蓋率固定以全部 100 句為分母。護欄拒絕、沒有顯示與過慢仍保留。

句尾句點容差只忽略英文單字後最後一個 ASCII `.`；不忽略數字／小數、問號、驚嘆號、省略號或文字內容。嚴格指標另列，沒有改寫 alpha6 歷史紀錄。

## 執行路徑

開啟輪 OCR 路徑：`{dict(paths)}`。完整偵測原因：`{dict(reasons)}`。

同組第 1–40 句的 OCR 平均在開啟輪較低，但第 41–100 句反而上升；模型、renderer 與擷取也在後段變慢。整機 CPU 曾有 98.34% 的採樣值。這支持資源競爭可能是因素之一，但不能證明都是外部程式造成，或排除本功能的額外成本；沒有因此刪除較差的後段。

先完整偵測取得可信的橫排行位置；新畫面依當前白字像素更新文字左右邊界，驗證行數與位置後才略過偵測。不是沿用舊文字寬度。相同 glyph episode 的安全複查做完整偵測，讓下句能利用近期行提示。提示最多重用三次／兩秒；變形、移位、新行、彩字、低信心等回到完整 OCR。

每次辨識包含 fallback 的整體耗時；不是只計算成功快速路徑。擷取、OCR、翻譯三個階段及過期 session／epoch 阻擋仍在。

## 開啟輪的慢句與失敗

| 句號 | 完整 Qt 延遲 ms（嚴格） | 原文 |
| --- | --- | --- |
'''+ '\n'.join(details)+'''

## 使用範圍

設定 → OCR 執行緒可選 1–4；「白字字幕加速（試驗）」可開關，儲存會停止既有監測，重新開始才使用新設定。**預設仍是 2 threads、行重用關閉、自適應複查關閉**；本表不能當成預設設定的速度。

全暗字幕與黃色字幕會回到完整 OCR，但暗字混在白字旁邊／新暗字行仍可能被快速路徑截掉，因此沒有自動開啟。固定白字場景的測試不能當成通用遊戲 recall 驗收。沒有新增模型或第二套 OCR session，提示只保存有界座標／hash／時間，不保存原文或影像歷史；沒有測本功能的獨立 native RAM／VRAM 上限。

額外 8 個真 OCR 圖片案例中，白字、較寬白字、新白字行、移位、黃字、全暗字與完整 OCR 的結果相符；混色新暗字行及同一行暗字後綴則都只輸出 `Open the gate`，漏掉 `before midnight`，信心仍約 0.998。**這是實際失敗，不是 8 項通過。** 見 [混色發現紀錄](assets/verification/layout-adversarial-a8.json)。

系統 CPU 每約 15 秒一筆、GPU 使用率／總顯存為瞬時整機值，存在原始資料；沒有把 GPU 總使用率當成本程式用量。CPU seconds 含背景 renderer，不是純 app pipeline。未測真遊戲 FPS／frametime、HDR、特殊字體與語意品質。

初版排程試跑在完成前中止，保存於 `test-results/moving-background-a8-initial-interrupted`，不算通過、不混入本表。早期 OCR-only 試作保存於 `test-results/ocr-layout-a8`，也不作為本版完整翻譯延遲。

[原始兩輪資料](assets/verification/moving-background-a8-line-ab.json)、[源檔凍結](assets/verification/frozen-source-a8.json)、[本版功能驗證](TEST_REPORT.md)。
'''
(ROOT/'BENCHMARK_LATENCY_A8.md').write_text(text,encoding='utf-8')
print(json.dumps({'control':control['summary'],'line_reuse':fast['summary'],'paths':dict(paths)},ensure_ascii=False))
