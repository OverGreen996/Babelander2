"""Publish timing, sampled OCR and concrete quality issues without a quality-score claim."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'test-results/subtitle-quick'
d=json.loads((SOURCE/'results.json').read_text(encoding='utf-8'))
assert d['completed'] and d['owned_model_stopped'] and d['workers_stopped']
assert d['source_unchanged'] and d['subtitle_unchanged']
assert len(d['translation'])==d['total_cues'] and len(d['ocr_ui'])==100 and len(d['extra_ocr_frames'])==200
assert all(hashlib.sha256((ROOT/'babelander'/n).read_bytes()).hexdigest()==digest for n,digest in d['application_source_sha256'].items())
PUBLIC=ROOT/'assets/verification'
PUBLIC.mkdir(exist_ok=True,parents=True)
shutil.copy2(SOURCE/'results.json',PUBLIC/'subtitle-quick-a4.json')
shutil.copy2(SOURCE/'corpus.json',PUBLIC/'subtitle-corpus-a4.json')
diagnostics=json.loads((SOURCE/'diagnostics.json').read_text(encoding='utf-8'))
assert diagnostics['owned_model_stopped']
shutil.copy2(SOURCE/'diagnostics.json',PUBLIC/'subtitle-diagnostics-a4.json')
for p in SOURCE.glob('*.png'):shutil.copy2(p,ROOT/'assets'/('subtitle-'+p.name))
s=d['summary']
def metric(key,field='mean_ms'):return f"{s[key][field]:.2f}" if s[key] else 'N/A'
def timing_row(label,key):
    return f"| {label} | {s[key]['n'] if s[key] else 0} | {metric(key)} | {metric(key,'p95_ms')} | {metric(key,'max_ms')} |"
warnings=Counter(r['warning'] for r in d['translation'] if r['warning'])
warning_table='\n'.join(f'| {warning} | {count} |' for warning,count in warnings.items())
rows={r['cue_id']:r for r in d['translation']}
quality_notes={4:('諷刺語气被翻成正面的「有幫助」','多出這点日光又有什麼用？'),
               6:('not … until 的時間關係翻反','我們得過了午夜才會到家。'),
               8:('blow Sunday（浪費星期天）被字面翻譯','你以為我想把星期天浪費在這種事上？')}
quality_table='\n'.join(f"| {cue} | {rows[cue]['source']} | {rows[cue]['target']} | {note}；意思應接近：{suggestion} |"
                        for cue,(note,suggestion) in quality_notes.items())
diagnostic_table='\n'.join(f"| {r['cue_id']} | {r['normalized_output']} | {r['warning']} |" for r in diagnostics['rows'])
sample=d['sampled_cues'][49]['cue_id']
states=Counter(r['backend_state'] for r in d['translation'])
text=f'''# 真實 SRT 字幕快速測試 · {d['version']}

日期：2026-10-08。檔案：`{d['subtitle_file']}`；**整份 {d['total_cues']} 段**，{d['unique_texts']} 種不同文字。來源 SHA-256：`{d['subtitle_sha256']}`；原檔維持不變。

依照「快速測完」要求，直接逐段送目前本機翻譯引擎，不播放原片或等每段 3 秒。完整文字翻譯花 **{d['translation_pass_seconds']:.2f} 秒**；再从全片平均取樣 100 段不同文字，測三個動態背景時點，共 **300 張 OCR 圖**，花 {d['sampled_pass_seconds']:.2f} 秒。主要測試含收尾共 **{d['wall_seconds']:.2f} 秒**；另 {diagnostics['extra_model_requests']} 次護欄診斷請求不納入反應時間。

## 速度與輸出

| 路徑 | 次數 | 平均 ms | P95 ms | Max ms |
| --- | ---: | ---: | ---: | ---: |
{timing_row('整份文字翻譯（含冷啟動／規則／快取）','translation_all')}
{timing_row('冷模型','translation_cold')}
{timing_row('暖模型，實際模型請求','translation_warm')}
{timing_row('既有快取','translation_cache')}
{timing_row('100 張 OCR 到 Qt 更新（暖機，含拒絕）','ocr_ui_all')}
{timing_row('另外 200 張背景快照，僅 OCR','extra_ocr_latency')}

後端狀態分布：`{json.dumps(dict(states),ensure_ascii=False)}`。完整檔保留重複台詞的自然快取行為；OCR 階段開始前清空測試快取，100 段不重複原文的 UI 路徑仍有 {s['sampled_ui_cache_hits']} 次快取命中。

936 段中 **{s['translation_usable']} 段有無警告的非空譯文、{s['translation_rejected']} 段被護欄拒絕**。此處「有無警告的非空譯文」指有輸出且沒有警告。這是輸出可用性，不是語意正確率；以下抽查證明護欄通過仍然可能翻错。冷啟動、暖機與快取均分開統計，沒有把失敗樣本的 elapsed_ms 設為零。

## 背景快照 OCR

| 項目 | 結果 |
| --- | ---: |
| 300 張原文完全匹配（只合併空白） | {s['all_ocr_exact']}/300 |
| 忽略標點／大小寫後字詞一致 | {s['all_ocr_lexical_exact']}/300 |
| 100 張 UI 路徑原文完全匹配 | {s['ocr_ui_exact']}/100 |
| 100 段中三幀得到不同 OCR 文字 | {s['background_text_changed_cases']}/100 |
| 100 段 UI 有無警告的非空譯文 | {s['ocr_ui_usable']}/100 |

每段使用相同字幕，但背景的三個不同動畫時點（step 0／17／43）有不同像素雜湊。1450 × 250、Arial 30 pt、白字黑描邊、無不透明文字底板。每段三張快照連續辨識，**沒有等背景真的播放 3 秒**。這能快速測 OCR 對背景變動的反應，不能代替持續監測的漏句／過期結果驗收。

兩張字詞不一致都發生在 step 43：cue 259、268 的句尾引號被辨識為 `W`，confidence 分別為 0.60245／0.62815；另外的完全匹配差異主要是標點。這兩張額外快照只送 OCR，沒有送模型或顯示為譯文。

![抽樣字幕與動態背景快照](assets/subtitle-cue-{sample}-step-17.png)

## 品質抽查：目前模型尚不能放心處理口語字幕

以下三段是實際輸出，判讀由閱讀原文與譯文完成；只抽查這幾段，不推算全片語意準確率。

| 原 cue | 原文 | 實際譯文 | 問題 |
| --- | --- | --- | --- |
{quality_table}

這三段都沒有被護欄擋下。數字／否定檢查無法證明諷刺、慣用語、時間邏輯或口語語氣正確；單獨翻譯字幕也缺少前後文。

## 拒絕與少量診斷

| 護欄警告 | 段數 |
| --- | ---: |
{warning_table}

另外明確重送前五個拒絕案例，攔截原始模型輸出，確認是模型或後處理哪一層造成；五次都排除在上方 benchmark 的平均值之外。

| 原 cue | OpenCC 正規化後、護欄前輸出 | 護欄結果 |
| --- | --- | --- |
{diagnostic_table}

cue 5 的三小時譯文被誤擋：目前數字正規化能將「三小時」轉為 `3 小時`，卻沒有同樣處理英文 `three-hour`。cue 1 的「第一天」也會被時間數字正規化看成含 `1 天`，產生數字警告；但該句把時鐘換時間翻成「日出」，本身也有語意錯誤。cue 2 的 `What?` 被原樣返回，cue 49／58 保留英文人名，均遭「沒有中文」護欄拒絕；這些案例分屬模型／護欄問題，不能一概歸為 OCR 錯誤。

警告中的「已保留原文」是主介面核對資料；浮層仍只顯示譯文，失敗時空白。本次未為了提高通過數自動重試所有拒絕、更換模型、放寬護欄或修改應用程式。

## 測量邊界與重現

本次使用 Qwen3 1.7B Q4_K_M／llama.cpp CUDA b10896、RapidOCR CPU 與實際 Qt receiver，全部 offscreen，不開測試視窗、不註冊快捷鍵、不讀遊戲畫面或雲端 API。逐句模式 DIALOG，時間碼與 SRT 序號不送給模型，合併換行並剝除 HTML 顯示標籤，原始 cue 文字另保留。

快測延遲不包含監測 scan／stable 等待、GDI、桌面 compositor 或真實遊戲 FPS。相同設定的每段 3 秒靜態／動態監測結果另見 [100 句背景完整測試](BENCHMARK_MOVING_BACKGROUND.md)；不能用本次快測數字冒充即時監測總延遲。本次未重測 RAM／VRAM，不能推算資源增減百分比。非串流 TTFT／prefill／decode 為 N/A。

測試自有模型和工作執行緒已退出；30 個應用程式檔案與來源 SRT 雜湊不變。完整 [逐句速度／譯文／警告／OCR 結果](assets/verification/subtitle-quick-a4.json)、[護欄診斷](assets/verification/subtitle-diagnostics-a4.json)與 [SRT cue 語料](assets/verification/subtitle-corpus-a4.json)均保存。重現指令（需已安裝本機測試依賴和模型）：

```powershell
.\\.venv\\Scripts\\python.exe probe_subtitle_quick.py --subtitle C:\\subtitles\\movie.en.srt
```
'''
# Normalize a few draft characters to Taiwan Traditional Chinese.
text=text.replace('語气','語氣').replace('這点','這點').replace('再从','再從').replace('翻错','翻錯')
text=text.replace('有無警告的非空譯文','無警告的非空譯文').replace('此處「無警告的非空譯文」指有輸出且沒有警告。','')
(ROOT/'BENCHMARK_SUBTITLE.md').write_text(text,encoding='utf-8')
print(json.dumps({'published':True,'wall_seconds':d['wall_seconds'],'summary':s},ensure_ascii=False))
