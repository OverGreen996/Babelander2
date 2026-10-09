"""Record measured alpha5 prototype progress; this is not a release certificate."""
from pathlib import Path
import hashlib
import json
import shutil
ROOT=Path(__file__).resolve().parent
old=json.loads((ROOT/'assets/verification/moving-background-100-a4.json').read_text(encoding='utf-8'))
new=json.loads((ROOT/'test-results/moving-background-a5/results.json').read_text(encoding='utf-8'))
assert new['completed'] and new['source_unchanged'] and new['owned_model_stopped'] and new['workers_stopped']
assert all(hashlib.sha256((ROOT/'babelander'/n).read_bytes()).hexdigest()==d for n,d in new['application_source_sha256'].items())
a=old['phases']['moving_noise']['summary'];p=new['phases']['moving_noise'];b=p['summary']
out=ROOT/'assets/verification'
for source,destination in [('moving-background-a5/results.json','moving-background-a5.json'),
                           ('frozen-source-a5.json','frozen-source-a5.json'),
                           ('pipeline.json','pipeline-a5.json'),('unit-tests.json','unit-tests-a5.json'),
                           ('asset-unit.json','asset-unit-a5.json'),('ocr-threads-a5.json','ocr-threads-a5.json')]:
    path=ROOT/'test-results'/source
    if path.exists():shutil.copy2(path,out/destination)
threads=json.loads((ROOT/'test-results/ocr-threads-a5.json').read_text(encoding='utf-8'))
table='\n'.join(f"| {r['threads']} | {r['mean_ms']:.2f} | {r['cpu_seconds']:.3f} |" for r in threads['rows'])
not_ready=[r['case_id'] for r in p['outcomes'] if not r['usable_display']]
slow=[r['case_id'] for r in p['outcomes'] if r['display_latency_ms'] is not None and r['display_latency_ms']>700]
text=f'''# 700 毫秒目標：alpha5 原型測試

日期：2026-10-08。**尚未全面達到 700 ms；目前不是正式發行驗收。** 同一組 100 句、每句 3 秒、20 FPS 動態雜訊、1450 × 250 Arial 白字黑描邊、CPU OCR／CUDA／offscreen Qt。新測試 300 秒，先暖機、零翻譯快取；不含真實 GDI 與實體螢幕可見時間。

| 指標 | alpha4 | alpha5 原型 |
| --- | ---: | ---: |
| 完全匹配原文且無警告譯文 | {a['usable_display']}/100 | {b['usable_display']}/100 |
| fixture 換句到完整 Qt 更新平均 | {a['display_latency']['mean_ms']:.2f} ms | {b['display_latency']['mean_ms']:.2f} ms |
| P95 | {a['display_latency']['p95_ms']:.2f} ms | {b['display_latency']['p95_ms']:.2f} ms |
| Max | {a['display_latency']['max_ms']:.2f} ms | {b['display_latency']['max_ms']:.2f} ms |
| 700 ms 內完成 | 依舊逐句紀錄判讀 | {b['usable_display_within_700_ms']}/100 |
| 3 秒內完成 | {a['usable_display_within_3_seconds']}/100 | {b['usable_display_within_3_seconds']}/100 |
| 至少一次完全正確 OCR | {a['exact_ocr_seen']}/100 | {b['exact_ocr_seen']}/100 |
| OCR 次數 | {a['ocr_calls']} | {b['ocr_calls']} |
| OCR 單次平均／P95 | {a['ocr_call_latency']['mean_ms']:.2f} / {a['ocr_call_latency']['p95_ms']:.2f} ms | {b['ocr_call_latency']['mean_ms']:.2f} / {b['ocr_call_latency']['p95_ms']:.2f} ms |
| 換句到首次完全正確 OCR 平均／P95 | {a['first_exact_ocr_latency']['mean_ms']:.2f} / {a['first_exact_ocr_latency']['p95_ms']:.2f} ms | {b['first_exact_ocr_latency']['mean_ms']:.2f} / {b['first_exact_ocr_latency']['p95_ms']:.2f} ms |
| 擷取次數 | {a['captures']} | {b['captures']} |
| 模型請求數 | {a['backend_requests']} | {b['backend_requests']} |
| 非完全匹配原文仍有譯文的額外顯示 | {a['nonexact_source_display_results']} | {b['nonexact_source_display_results']} |
| 譯文到達時 fixture 已換句 | {a['display_after_sentence_changed']} | {b['display_after_sentence_changed']} |

平均與 P95 僅計入可用且完全匹配的譯文，新版 n={b['display_latency']['n']}；700 ms 覆蓋率以全部 100 句為分母，把拒絕列為未完成。**74 句及時输出不代表 74 句語意正確**，尚無此語料的完整人工語意標註。

未就緒：{not_ready}。就緒但超過 700 ms：{slow}。原文完全匹配指合併空白後逐字比較；新版 3 次漏句尾句點造成額外翻譯，並沒有算成同一原文成功樣本。

## 已改的排程

- 新 `dialog_scan_ms=100` 只控制字幕觀察；其他監測仍 `scan_ms=800`。
- 新設定 `stable_ms=100`，穩定窗口從實際第一次擷取開始，OCR 時間可包含在內；非零 stable 還需要另一張实际捕捉畫面確認字形／文字沒有改變。
- 以期限排程，OCR 完後不再額外睡整個週期。OCR 一看到新候選就增加事件版本、清舊浮層與舊待翻，不等 stable 期限。
- max(BGR) ≥ 220 的二值字形指紋只做亮字 fast path；coverage .001–.65。亮字相同、原圖有變仍每 1.2 秒 full OCR；不具有效亮字特徵時保留 800 ms fallback。只保存指紋，沒有新增原圖歷史。

舊設定檔的 stable 值保留，沒有修改使用者設定；舊值 300 ms 不會自動變 100 ms。目標設定必須用「字幕觀察間隔 100／字幕穩定等待 100」。模型、OCR 解析度、CPU threads=2、CUDA 層数與字詞護欄均保持。1.2 秒複查仍可能阻塞下一句 OCR；擷取／OCR尚未彼此解耦。

亮字 fast path 不代表通用文字偵測，仍需測暗字、低飽和／半透明字、亮背景、粒子、打字動畫、短於觀察間隔的字幕與混色行。100 句至少看過一次、無跨句晚到，不證明全部遊戲不漏字幕。

## CPU 執行緒候選實驗

同樣三張保存的短／中／長字幕圖，各暖機後重複 3 次；沒有遊戲負載、沒有測 RAM／VRAM。三種設定的辨識輸出一致，但樣本量很小。

| OCR threads | 9 次平均 wall ms | 9 次總 CPU seconds |
| --- | ---: | ---: |
{table}

增加 4 threads 讓單次更快，但 CPU seconds 明顯增加；不能叫低資源優化，也未改為產品預設。詳見 [threads 原始實驗](assets/verification/ocr-threads-a5.json)。

新／舊母程序 CPU seconds {b['cpu_seconds_including_fixture']:.3f}／{a['cpu_seconds_including_fixture']:.3f} 包含同程序 fixture renderer；其 render wall 各約 138 秒，不能從差值推算 App CPU 降幅。新捕捉次數增加，不含真 GDI 成本；本輪未重新量模型 RAM、VRAM、遊戲 FPS／frametime。更高觀察頻率在遊戲的成本尚未驗收。

## 下一步與證據

先對「換句到 capture／OCR」長尾加可對照的時間戳，分開 admission 等待、前次 OCR 占用、capture deadline miss、fixture renderer 和 UI 排程；不能在未量前把全部原因指定為 OCR 或 GDI。再以固定品質保留案例檢查 guard、有限上下文／提示與模型候選。

新版目前核心 57、管線/UI 27、下載合約 12 項通過，**96 項不等於 700 ms 或語意驗收通過**。這次是原始碼原型監測，不是 EXE/wheel 本輪重測；alpha4 的打包結果保留在歷史報告，不移用給 alpha5。測試自有模型／workers 已退出、31 個應用程式源檔/QSS 雜湊不變。

[完整逐句結果](assets/verification/moving-background-a5.json)、[管線檢查](assets/verification/pipeline-a5.json)。
'''
text=text.replace('输出','輸出').replace('实际','實際').replace('層数','層數')
(ROOT/'BENCHMARK_LATENCY_A5.md').write_text(text,encoding='utf-8')
print(json.dumps({'published':True,'mean_ms':b['display_latency']['mean_ms'],'p95_ms':b['display_latency']['p95_ms'],
                  'within_700ms':b['usable_display_within_700_ms'],'target_fully_met':False}))
