"""Publish bound-source alpha6 experiments, including failures and load limits."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'assets/verification'
OUT.mkdir(exist_ok=True,parents=True)
baseline=json.loads((OUT/'moving-background-a5.json').read_text(encoding='utf-8'))
experiments=[]
for threads in (2,4):
    path=ROOT/f'test-results/moving-background-a6-threads{threads}/results.json'
    result=json.loads(path.read_text(encoding='utf-8'))
    assert all(result.get(k) for k in ('completed','source_unchanged','owned_model_stopped','workers_stopped'))
    assert all(hashlib.sha256((ROOT/'babelander'/name).read_bytes()).hexdigest()==digest
               for name,digest in result['application_source_sha256'].items())
    shutil.copy2(path,OUT/f'moving-background-a6-threads{threads}.json')
    experiments.append(result)
for source,destination in [('frozen-source-a6.json','frozen-source-a6.json'),('pipeline.json','pipeline-a6.json'),
                           ('unit-tests.json','unit-tests-a6.json'),('asset-unit.json','asset-unit-a6.json')]:
    shutil.copy2(ROOT/'test-results'/source,OUT/destination)
assert json.loads((OUT/'pipeline-a6.json').read_text())['passed']
assert json.loads((OUT/'unit-tests-a6.json').read_text())['passed']
assert json.loads((OUT/'asset-unit-a6.json').read_text())['passed']

summaries=[baseline['phases']['moving_noise']['summary']]+[r['phases']['moving_noise']['summary'] for r in experiments]
rows=[]
for label,key in [('完整 Qt 更新平均','mean_ms'),('P95','p95_ms'),('Max','max_ms')]:
    rows.append('| '+label+' | '+' | '.join(f"{s['display_latency'][key]:.2f} ms" for s in summaries)+' |')
for label,key in [('700 ms 內完成','usable_display_within_700_ms'),('無警告且原文匹配譯文','usable_display'),
                  ('至少一次完全匹配 OCR','exact_ocr_seen'),('OCR 次數','ocr_calls'),('擷取次數','captures'),
                  ('換句後才顯示上一句','display_after_sentence_changed')]:
    rows.append('| '+label+' | '+' | '.join(str(s[key])+('/100' if key in ('usable_display_within_700_ms','usable_display','exact_ocr_seen') else '') for s in summaries)+' |')
details=[]
for experiment in experiments:
    phase=experiment['phases']['moving_noise']
    counts=phase['metrics']['counts']
    details.append(f"- {experiment['ocr_threads']} threads：候選覆蓋 {counts.get('ocr_candidate_superseded',0)}、OCR 完成後因新畫面淘汰 {counts.get('ocr_result_superseded',0)}；捕捉緩衝終場狀態 `{phase.get('capture_streams',[])}`。")
load=experiments[1].get('system_load_samples',[])
load_line='沒有連續系統負載樣本。'
if load:
    cpu=[r['whole_system_cpu_percent'] for r in load if r.get('whole_system_cpu_percent') is not None]
    gpu=[r['gpu_instant_percent'] for r in load if 'gpu_instant_percent' in r]
    load_line=f"4 threads 試驗共 {len(load)} 個系統樣本；CPU 為約 15 秒區間平均，範圍 {min(cpu):.1f}–{max(cpu):.1f}%；GPU 為瞬時抽樣，範圍 {min(gpu):.1f}–{max(gpu):.1f}%。包含本機測試模型和其他程式，不是 App 專屬占用。"
text=f'''# alpha6：獨立擷取與減少重複辨識

日期：2026-10-08。優先順序為速度 > 精準 > 資源；700 ms 是門檻，還要減少慢句。

同一組 100 句、每句 3 秒、1450 × 250 白字黑描邊、20 FPS 移動暗雜訊。真 CPU OCR、CUDA Qwen、offscreen Qt；合成擷取取代 GDI，先暖機、零翻譯快取。

| 指標 | alpha5 | alpha6 2 threads | alpha6 4 threads |
| --- | ---: | ---: | ---: |
{chr(10).join(rows)}

**這不是乾淨的效能 A/B。** alpha5 與本輪背景負載不同；alpha6 的 2 threads 試驗完成前後抽樣，發現兩個 UnrealEditor 在約 1 秒取樣中合計增加 9.48 CPU core-seconds，GPU 約 92%。取樣間隔另有程序列舉成本；GPU 是全系統值，不能全歸給某一程式，也不能回推每一筆慢句的確切成因。{load_line} 沒有停止使用者程式，也沒有測遊戲 FPS／frametime；不據此將 4 threads 改成預設。

兩個 alpha6 試驗都啟用實驗性的 adaptive_ocr_recheck，產品預設仍關閉，OCR threads 預設仍 2。因此與 alpha5 比較包含解耦和複查策略兩項變更，無法將收益全部歸給單項。只證明這個白字 fixture 的觀測覆蓋，不證明暗字、混色文字、短字幕或真遊戲完全不漏。

平均與 P95 僅包含各輪成功樣本；700 ms 覆蓋率以全部 100 句為分母，拒絕／未顯示列為失敗。通過現有護欄不等於語意正確，尚無這 100 句全部譯文的人工標註。物理螢幕呈現時間不包含在內。

## 實作與限制

- 擷取獨立於 OCR 與翻譯；OCR 執行中仍持續觀察。最多一張 active ROI、一張 latest pending，加生產端一張 transient。pending 覆蓋與已辨識淘汰分別計數，沒有無上限 frame queue。
- 亮字變化產生 capture epoch，辨識與 Qt 接收都檢查；A→B→A 必須使用新的 epoch，不能復活最早的 A。dim/raw 路徑仍是啟發式，不能由 bright epoch 保證所有文字生命週期。
- OCR 時间包含在稳定窗口；非零稳定值仍需 OCR 完成後的新畫面確認，優先喚醒擷取而不再多等完整週期。
- 不因任何 OCR 候選立即清空已顯示譯文，避免抖動空白；空白 OCR 仍清除。已顯示的上一句在新譯文到達前可能暫留，尚未加獨立 retention deadline，過時保留時間仍待驗收。
- 實驗性 episode budget 只在可靠 OCR 重複相同文字且具有亮字特徵時將複查 1.2→2→3 秒；亮字改變立即辨識，無亮字保留 800 ms fallback。混色的暗字局部變化可能延遲，尚不足以設為預設；未加入通用 edge／stroke／connected-component 文字偵測。
- 分段時間包含擷取、hash、OCR 排隊／開始／完成、確認畫面、翻譯與 Qt 更新。新版 first-correct-OCR 計算使用實際 OCR 完成時間，包含排隊；合成素材的 onset 與實際遊戲 onset 仍不同。
- ROI byte counter 包含 active、pending 和 transient ndarray；不包含 GDI 暫存、ONNX tensors、縮圖及 native allocator，不能當成總 RAM 上限。

{chr(10).join(details)}

本表測的是 alpha6 原始碼；新 EXE／wheel 的功能檢查另外記錄在 TEST_REPORT.md，不能把本表當成執行檔的 100 句驗收。96 項舊 alpha5 檢查不移用為本輪驗收；本輪 57 核心、35 管線、12 資產檢查合計 104 項通過。31 個 app 源檔／QSS 前後雜湊一致，測試自有模型及 workers 已退出。中斷的 pre-fix 試驗獨立保留，不納入表格。

下一步先在可對照的系統負載下重測，並擴充短字幕、混色與局部數字／否定詞變更測試。保留 PP-OCRv6 Small；沒有以更重模型或降低解析度來掩蓋觸發問題。

[2 threads 逐句資料](assets/verification/moving-background-a6-threads2.json)、[4 threads 逐句資料](assets/verification/moving-background-a6-threads4.json)、[管線檢查](assets/verification/pipeline-a6.json)。
'''
text=text.replace('时间','時間').replace('稳定','穩定')
(ROOT/'BENCHMARK_LATENCY_A6.md').write_text(text,encoding='utf-8')
print(json.dumps({'published':True,'summaries':summaries[1:],'clean_ab_test':False},ensure_ascii=False))
