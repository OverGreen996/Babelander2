"""Publish timings, inputs and diagnostics without changing the tested app."""
from pathlib import Path
import json
import math
import shutil
import statistics

root=Path(__file__).resolve().parent
out=root/'test-results/english-100'
report=json.loads((out/'results.json').read_text(encoding='utf-8'))
diagnostic=json.loads((out/'diagnostics.json').read_text(encoding='utf-8'))
assert report['completed'] and report['owned_model_stopped'] and report['workers_stopped']
assert len(report['model_pass'])==len(report['ocr_ui_pass'])==100
assert report['summary']['cache_hits']==0
assert len({r['text'] for r in report['model_pass']})==100
assert diagnostic['owned_model_stopped']
def stats(values):
    ordered=sorted(values)
    return {'samples':len(values),'mean_ms':round(statistics.mean(values),2),
            'p50_ms':round(ordered[math.ceil(len(values)*.5)-1],2),
            'p95_ms':round(ordered[math.ceil(len(values)*.95)-1],2),
            'min_ms':round(ordered[0],2),'max_ms':round(ordered[-1],2)}
summary=report['summary']
summary['ocr_to_ui_after_first_initialization']=stats([r['elapsed_ms'] for r in report['ocr_ui_pass'][1:]])
summary['ocr_stage_all']=stats([r['ocr_ms'] for r in report['ocr_ui_pass']])
summary['ocr_stage_warm']=stats([r['ocr_ms'] for r in report['ocr_ui_pass'][1:]])
report['summary']=summary
(out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
verification=root/'assets/verification'
shutil.copy2(out/'results.json',verification/'english-100-a4.json')
shutil.copy2(out/'diagnostics.json',verification/'english-100-diagnostics-a4.json')
shutil.copy2(out/'corpus.json',verification/'english-100-corpus-a4.json')
rows=[]
for label,key in [('純翻譯：全部 100 句（含首次載模型）','translation_all'),
                  ('純翻譯：模型暖機後 99 句','translation_warm'),
                  ('OCR → 翻譯 → Qt 更新：全部 100 句','ocr_to_ui_all'),
                  ('OCR → 翻譯 → Qt 更新：首次 OCR 初始化後 99 句','ocr_to_ui_after_first_initialization'),
                  ('OCR → 翻譯 → Qt 更新：有可顯示譯文 97 句','ocr_to_ui_usable')]:
    s=summary[key];rows.append(f"| {label} | {s['mean_ms']:.2f} | {s['p50_ms']:.2f} | {s['p95_ms']:.2f} | {s['max_ms']:.2f} |")
group_rows=[]
labels={'short':'短句','story':'劇情','action':'行動指示','conditions':'條件／數值','long':'長句'}
for group in labels:
    model=[r['elapsed_ms'] for r in report['model_pass'] if r['group']==group and r['backend_state']=='warm']
    ui=[r['elapsed_ms'] for r in report['ocr_ui_pass'] if r['group']==group and r['id']!=1]
    group_rows.append(f"| {labels[group]} | 20 | {statistics.mean(model):.2f}（n={len(model)}） | {statistics.mean(ui):.2f}（n={len(ui)}） |")
diagnostic_rows=[]
for r in diagnostic['rows']:
    diagnostic_rows.append(f"| {r['id']} | {r['source']} | {r['normalized_output']} |")
text=f'''# 100 句全新英文：反應時間實測

日期：2026-10-08；Babelander {report['version']}／RTX 3080 Ti／Qwen3-1.7B Q4_K_M／llama.cpp b10896 CUDA。

**模型暖機後，純翻譯平均 {summary['translation_warm']['mean_ms']:.2f} ms；自製英文圖片經 OCR、翻譯至 Qt 介面更新，平均 {summary['ocr_to_ui_all']['mean_ms']:.2f} ms。**

同一批 100 個全新、不重複的英文句子，短句、劇情、行動指示、條件／數值、長句各 20。與前次 fixture 報告／程式案例檢查無完全相同句子。全數以字幕模式的同一 prompt 執行，沒有改模型／profile／context／thinking 設定。每句翻譯一次，再清空測試快取跑一次 OCR 至 UI；共 200 次實際本機模型請求、快取命中 0 次、付費 API 0 次。

## 時間結果

單位 ms；平均使用算術平均，P50／P95 使用 nearest-rank。表中「回應」包含護欄拒絕的決定時間，有譯文者另列，沒有隱藏失敗的三句。

| 測試路徑 | 平均 | P50 | P95 | 最慢 |
| --- | --- | --- | --- | --- |
{chr(10).join(rows)}

首次需要模型的純翻譯耗時 **{report['model_pass'][0]['elapsed_ms']:.2f} ms**，包含載入；首次 OCR 流程耗時 **{report['ocr_ui_pass'][0]['elapsed_ms']:.2f} ms**，此時模型已暖機，包含懶載入 OCR／辨識／翻譯／Qt 更新，不能全部算成 OCR 初始化。暖機後單獨 OCR 階段平均 {summary['ocr_stage_warm']['mean_ms']:.2f} ms。整個雙遍流程約 {report['wall_seconds']:.2f} 秒。

| 句型 | 全新句數 | 暖機純翻譯平均 ms | OCR 暖機後整條流程平均 ms |
| --- | --- | --- | --- |
{chr(10).join(group_rows)}

## 品質與拒絕

自製圖片的 OCR 空白正規化後逐句完全一致：**100／100**。兩遍均為 **97 句有可顯示譯文、3 句被否定護欄擋下**；這不等於 97% 語意準確率，未對所有譯文做人工標註。

額外針對這三句做 **3 次診斷重跑**，捕捉後端原始輸出，完全不納入上述平均。三句的否定都以「從未／未」表達，現有護欄只接受「不／勿／別／禁止／無須／毋須」，所以否定檢查有誤擋。第 86 句另有 `treasury` 殘留英文，仍有翻譯完整度問題，不能把誤擋解除當成語意品質通過。這次只測量與記錄，沒有變更已測試的應用程式碼。

| 案例 | 英文 | 診斷重跑的繁體正規化輸出 |
| --- | --- | --- |
{chr(10).join(diagnostic_rows)}

## 測量邊界

使用 Qt **offscreen** 與 1450 × 250 px 自製高對比圖片，字型 Arial 30 pt、CPU OCR、完整原解析度。圖片繪製在計時前完成；擷取替代為記憶體複製，仍使用 Controller／Engine／實際 MainWindow receiver。結束點是 Qt slot 已更新 target／警告；不代表螢幕 compositor 已呈現遊戲浮窗。

**不包含真實 GDI 擷取、遊戲動畫、800 ms 掃描排程或 300 ms 穩定判斷；不能解讀為字幕出現後固定 0.35 秒便看到譯文。** 這是同機、連續單件工作、沒有排队壓力的測試，模型可能受益於共同 prompt 的後端 prefix cache；不是所有遊戲的平均速度。未開桌面測試視窗、未注册測試快捷鍵、不讀取使用者畫面／設定，結束後自有模型與 worker 均已停止。

## 可重現資料

- [100 句完整英文](assets/verification/english-100-corpus-a4.json)
- [逐句譯文、OCR 結果與毫秒紀錄](assets/verification/english-100-a4.json)
- [三句護欄診斷重跑](assets/verification/english-100-diagnostics-a4.json)

測試腳本：`probe_100_english.py`；診斷：`probe_100_diagnostics.py`。200 次本機請求屬主測試，另三次為診斷；沒有自動 API 重試。
'''
(root/'BENCHMARK_100_ENGLISH.md').write_text(text.replace('排队','排隊').replace('注册','註冊'),encoding='utf-8')
print(json.dumps({'completed':True,'summary':summary},ensure_ascii=False))
