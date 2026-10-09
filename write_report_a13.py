"""Render the current measurements without turning failed cases into success."""
from pathlib import Path
import json
ROOT=Path(__file__).parent
def read(path):return json.loads((ROOT/path).read_text(encoding='utf8'))
def main():
    baseline=read('test-results/replay-a12-baseline-20/results.json')
    small=read('test-results/replay-a13-mixed-20/results.json')
    full=read('test-results/replay-a13-final-100-t4/results.json')
    assert full['completed']
    b=baseline['summary']['2'];s=small['summary']['2'];f=full['summary']['4']
    h0=baseline['holdout_summary']['2'];h1=small['holdout_summary']['2'];hf=full['holdout_summary']['4']
    stress=read('test-results/subtitle-trigger-stress-a13.json');native=read('test-results/native-capture-a13.json')
    samples=full['system_load']
    gpu_samples=[r['owned_gpu_process_memory'] for r in samples if r.get('owned_gpu_process_memory')]
    gpu_text=(f"另以自有模型 PID 查 WDDM GPUProcessMemory，{len(gpu_samples)} 個採樣的 DedicatedUsage 最大 {max(r['dedicated_mib'] for r in gpu_samples):.2f} MiB、SharedUsage 最大 {max(r['shared_mib'] for r in gpu_samples):.2f} MiB；不是整機 GPU 總量，也不是物理駐留量或峰值硬上限。" if gpu_samples else '本輪未取得自有 PID 的 GPU 記憶體计數，不以整機 GPU 記憶體替代。')
    app_peak=max(row['app']['working_mib'] for row in samples if row.get('app'))
    model_peak=max(row['model']['working_mib'] for row in samples if row.get('model'))
    phases=[p for p in full['phases'] if p['label'].startswith('block-')]
    app_cpu=sum(p['process_cpu_seconds'] for p in phases)
    model_cpu=sum(p['model_resources_after']['cpu_seconds']-p['model_resources_before']['cpu_seconds'] for p in phases)
    failures=[r for p in phases for r in p['outcomes'] if r['source'] and not r['usable_current_display']]
    slow=[r for p in phases for r in p['outcomes'] if r['source'] and r['usable_current_display'] and not r['within_700ms']]
    detail='\n'.join(f"- {r['cue_id']}：{r['source']}；"+(f"{r['display_latency_ms']:.2f} ms" if r['display_latency_ms'] is not None else '當句未取得完整可用譯文') for r in failures+slow) or '- 本輪沒有未顯示或超過 700 ms 的案例。'
    native_rows='\n'.join(f"| {r['roi_dimensions'][0]} × {r['roi_dimensions'][1]} | {r['cpu_readable_capture']['mean_ms']} ms | {r['cpu_readable_capture']['p95_ms']} ms |" for r in native['rows'])
    table='\n'.join(f"| {label} | {r['cues']} | {r['usable_current_display']} | {r['usable_within_700ms']} | {r['display_latency']['mean_ms']} ms | {r['display_latency']['p95_ms']} ms | {r['ocr_calls']} |" for label,r in [('舊版／2 執行緒／觸發關閉',b),('新版／2 執行緒／觸發開啟',s),('新版／4 執行緒／觸發開啟',f)])
    text=f'''# alpha13：混色短字幕觸發與完整回放

2026-10-08。裝備外觀維持 alpha12；本輪針對字幕漏看與延遲，不更換 OCR 或翻譯模型。

## 實作與取捨

新增「白字旁的暗字變化偵測（試驗）」，預設關閉。辨認中亮度、有強邊缘的文字形狀，排除與已知亮字相交的反鋸齒部分。至少三個符合範圍的區塊、最多 256 個幾何摘要；結構必須在兩張實際畫面中一致，且相隔至少 70 ms，才更新 capture epoch、喚醒 OCR。新 epoch 會淘汰舊字幕結果。僅保存兩份 SHA-256／時間狀態，不增加 OCR engine、模型或影像歷史；既有 raw watchdog、佇列上限與 Stop／session 檢查都保留。

這是描邊暗字提示，**不是通用文字偵測器**。極小字、低對比、短字與持續逐字動畫可能仍等定期複查；靜止的非文字圖形仍可能觸發 OCR。沒有因合成測試通過便開啟預設，也沒有更改使用者既有設定。

曾嘗試使用 OCR 期間的確認畫面省略 OCR 後擷取，既有「OCR 結束前換句」回歸失敗，已撤回。正式版本仍要求 OCR 後的新畫面确认，沒有拿過期顯示風險換延遲。

## 完整時間

PP-OCRv6 Small／CPU、Qwen3 1.7B Q4_K_M／CUDA、實際 Controller 與 Qt offscreen。預先產生移動背景，20 FPS 循環；每句 3 秒、1450 × 250 白字黑描邊。每區塊暖機、清 SQLite 快取；llama prefix cache 不宣稱清空。沒有雲端 API、可見視窗或全域快捷鍵。

從測試字幕實際發布到完整譯文 Qt 更新，包含取樣、OCR、確認與翻譯；**不是單看模型時間，也不包含真遊戲 GDI／compositor／螢幕顯示**。前兩輪只有相同的 20 個洗牌樣本，且在否定護欄修正前；後一輪是修正後重新跑的完整 100 句，執行緒也不同。因此表格不是單一改動的乾淨速度 A/B，不將不同輪次的差值宣稱為新觸發器的加速。

| 設定 | 全部句數 | 當句可用 | 700 ms 內 | 平均完整更新 | P95 | OCR 次數 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{table}

平均與 P95 只包含當句仍存在時成功更新的案例；700 ms 覆蓋率以全部句數為分母。原文只允許英文單字末尾的一個句點容差，不忽略否定、數字或其他標點。可用代表完整原文歸屬與既有護欄通過，**不是人工語意正確率**。完整 100 句快取命中 {f['cache_hits']}、護欄拒絕 {f['guard_rejections']}、舊句跨 cue 晚顯示 {f['late_source_display']}。

### 未顯示／超過門檻

{detail}

## 混色与短字幕反例

12 個非空字幕事件加六個空白分隔，包含暗字同列追加、暗字新行、數字 10→18、否定、0.6 秒短字幕與上下移位。兩個混色變更的亮字指紋確實相同；OCR 只收圖片，不知道測試原文。

2 執行緒：舊版完整觀測／當句可用 {h0['exact_ocr_seen']}/{h0['cues']}／{h0['usable_current_display']}/{h0['cues']}；新版開啟觸發為 {h1['exact_ocr_seen']}/{h1['cues']}／{h1['usable_current_display']}/{h1['cues']}。完整回放後的 4 執行緒反例為 {hf['exact_ocr_seen']}/{hf['cues']} 完整 OCR、{hf['usable_current_display']}/{hf['cues']} 當句可用、{hf['usable_within_700ms']}/{hf['cues']} 在 700 ms 內。保留所有失敗與慢句，不將空白分隔算成成功字幕。

離線 100 個固定字形 × 16 個背景，結構誤變更 {stress['white_cue_false_structure_changes']} 次；100 幀移動文字形狀粒子提交 {stress['moving_glyph_shaped_particle_commits']} 次。特徵取樣平均 {stress['extraction_mean_ms']} ms、P95 {stress['extraction_p95_ms']} ms。這不是 1600 次 OCR，也不是所有遊戲的抗粒子驗收。

## 資源

完整 100 句區塊的 app CPU {app_cpu:.2f} core-seconds、自有模型 CPU {model_cpu:.2f} core-seconds；app working-set 採樣最大 {app_peak:.2f} MiB、自有模型 working-set 採樣最大 {model_peak:.2f} MiB。app 包含回放讀檔、複製與紀錄；模型 working-set 包含模型映射。這些是採樣值，不是 RAM 硬上限或純應用邏輯的成本。{gpu_text} **遊戲 FPS／frametime 仍未量測**。

另交錯測試 OpenCV 16／1 執行緒：24 個相同畫面的 OCR 文字都完整且一致，但平均 183.13／186.02 ms、CPU 9.688／9.859 core-seconds，未證明收益，沒有採用強制單執行緒。出貨仍預設 OCR 2 執行緒，4 執行緒只是本輪速度設定，不自動套用。

## 真實 GDI 擷取元件

目前主螢幕各 ROI 20 次擷取，畫素只在記憶體內，沒有保存、OCR 或列印內容；沒有建立可見視窗。量到 CPU 可讀 ndarray 完成：

| ROI | 平均 | P95 |
| --- | ---: | ---: |
{native_rows}

GDI handle 前／後為 {native['gdi_handles_before']}／{native['gdi_handles_after']}，本輪無擷取錯誤。這不是指定遊戲的相容性或 FPS 測試，也不能把獨立元件 P95 相加當成端到端時間。

## 發行与尚未解決

208 項單元／管線／Qt／回放計數檢查；EXE 與隔離 wheel 各有真 OCR／CUDA／Qt 功能自測。打包模組與本輪原始碼一致，舊 a12 封存不改寫。

第一輪 100 句有一筆否定護欄拒絕。獨立真模型診斷得到「尚未穿越過冰川的同伴」，確實保留 have never 的經歷否定，卻被舊護欄誤擋。只為 have/has/had never 且沒有其他命令否定的句型加入尚未／未曾／從未／沒有…過；Never 或 Do not 命令仍保持原門檻，未來不是否定。補上反例後，重新跑整組 100 句，以上是重跑的實測，没有事後改分。冰原被譯成冰川的詞義偏差仍存在，護欄不能驗證這類語意。

物品原字色／圖示／原位與一次性行為做 20 張回歸，仍有卡牌生命值 7 漏辨識；不將預知數字補進 OCR。真正遊戲尚未選定，沒有宣稱真遊戲 0.7 秒全面達標。混色觸發預設關閉，待對實際遊戲驗證後再決定是否升預設。

[100 句逐次資料](assets/verification/replay-mixed-100-t4-a13.json) · [混色反例資料](assets/verification/replay-mixed-20-a13.json) · [發行完整性](assets/verification/release-a13.json)。
'''
    text=text.replace('边','邊').replace('缘','緣').replace('与','與').replace('确认','確認').replace('计','計').replace('没有','沒有')
    (ROOT/'TEST_REPORT_ALPHA13.md').write_text(text,encoding='utf8')
    print(json.dumps({'mean_ms':f['display_latency']['mean_ms'],'p95_ms':f['display_latency']['p95_ms'],'within_700':f['usable_within_700ms'],'missing':len(failures),'slow':len(slow)}))
if __name__=='__main__':main()
