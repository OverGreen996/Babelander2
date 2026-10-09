# alpha8：公平重播與 OCR 2／4 執行緒比較

2026-10-08。實際 PP-OCRv6 Small／ONNX CPU、Qwen3 1.7B Q4_K_M／CUDA、完整 Qt offscreen 更新。應用源檔與 alpha8 凍結一致；本輪未修改模型、prompt、觸發器或使用者設定。

每組同樣 100 句、每句 3 秒；固定亂數洗牌，20 句一區塊，以 2→4、4→2 交錯次序測五個區塊。兩组 adaptive/reuse 都關閉、dialog_scan=100 ms、一般 scan=800 ms、stable=100 ms。不是全部 2 跑完才跑全部 4，也沒有同時跑兩套 OCR／模型。

移動暗雜訊與白字黑描邊預先產生：每句 16 張影像、20 FPS 循環播放，原像素 1450×250；測量時沒有 Qt／OpenCV 動畫繪製。以單一 mmap 分段讀取，另計 I/O／producer deadline。暖機每組固定三張 OCR 與三句模型請求，SQLite 每組清空；llama prefix/KV cache沒有宣稱清空，實際 cached tokens／timings 另存。

**仍是合成擷取，不是 GDI／DXGI 或真遊戲 FPS 測試。** 時間從該 cue 實際發布到完整譯文 Qt 更新，非實體螢幕像素／首字。循環背景、亂序句子和新重播方式與舊 alpha8 benchmark不同，不能把新舊平均差全部歸因4執行緒。

| 指標 | 2 threads | 4 threads |
| --- | ---: | ---: |
| 700 ms 內可用完整譯文／100 | 83 | 98 |
| 當句仍顯示時取得完整譯文／100 | 99 | 99 |
| 至少一次完整 OCR／100 | 100 | 100 |
| OCR 前未觀測／100 | 0 | 0 |
| 完整 Qt 平均 ms | 499.49 | 441.44 |
| 完整 Qt P50 ms | 462.20 | 429.08 |
| 完整 Qt P95 ms | 816.41 | 677.94 |
| 完整 Qt Max ms | 916.38 | 812.71 |
| 平均／P95 分母 | 99 | 99 |
| OCR 次數 | 257 | 279 |
| OCR 平均 ms | 209.99 | 161.22 |
| OCR P95 ms | 397.21 | 327.05 |
| 護欄拒絕 | 1 | 1 |
| 快取命中 | 0 | 0 |
| 舊原文跨 cue 晚顯示 | 0 | 0 |

可用表示當句顯示期間的完整原文歸屬、目標文字非空且現有護欄通過；**不是人工語意正確率**。原文只允許已定義的英文單字末尾句點容差，不忽略否定、數字、問號、驚嘆號或省略號。平均／P95只計成功當句結果；所有100句保留在700ms覆蓋率分母。

## 配對結果與區塊負載

| 區塊（相同20句） | 測量順序 | 2 threads：平均／P95／700ms句數 | 4 threads：平均／P95／700ms句數 |
| --- | --- | --- | --- |
| 1 | 2→4 | 486.74／728.42／17 | 381.75／525.64／20 |
| 2 | 4→2 | 497.37／816.41／17 | 437.39／633.19／20 |
| 3 | 2→4 | 525.59／840.27／16 | 515.23／683.47／19 |
| 4 | 4→2 | 470.53／725.17／17 | 418.81／679.58／19 |
| 5 | 2→4 | 515.78／732.02／16 | 452.87／663.41／20 |

兩組皆成功當句顯示的配對 99 句：4 threads 比 2 threads 更快 75 句；配對差值（4−2）平均 -58.06 ms。缺失句未塞入0ms，也沒有自動移除失敗後重測來改善覆蓋率。

## 混色與短字幕保留集

另各組18個畫面狀態（12個非空 cue＋6個空白分隔）：暗字同列追加、暗字新行、數字10→18、新增否定、0.6秒短字幕、字幕上下移位。基底1.6秒、變更0.6秒、空白0.6秒。這是小型固定反例集，不是通用遊戲 recall。兩個混色變更的 bright hash 經預檢確實維持相同。

| 字幕事件 | 2 threads | 4 threads |
| --- | --- | --- |
| mixed_inline-base | 388.00 ms | 178.05 ms |
| mixed_inline-changed | OCR前未觀測 | OCR前未觀測 |
| mixed_new_line-base | 451.41 ms | 390.55 ms |
| mixed_new_line-changed | OCR前未觀測 | OCR前未觀測 |
| number-base | 540.89 ms | 554.54 ms |
| number-changed | 未在當句期間顯示可用譯文 | 未在當句期間顯示可用譯文 |
| negative-base | 597.90 ms | 485.61 ms |
| negative-changed | 547.91 ms | 536.94 ms |
| short-base | 302.94 ms | 807.92 ms |
| short-changed | 237.84 ms | 505.16 ms |
| moved-base | 308.67 ms | 525.54 ms |
| moved-changed | 308.26 ms | 未在當句期間顯示可用譯文 |

**增加執行緒不能修復沒有喚醒 OCR 的變更。** 混色後綴與新暗字行的事件結果要獨立報告；即使白字100句平均低於700ms，也不能算短／混色字幕全面達標。

## 真後端時間與資源

OCR列保留 RapidOCR 回傳的 det／cls／rec 秒數；它們不是所有 preprocessing／postprocessing 的總成本。llama回應保留 usage、prompt_tokens_details.cached_tokens、prompt_ms、predicted_ms等實際欄位；沒回傳就N/A，非串流 TTFT仍沒有量測。

| 實測平均 ms（非独立P95相加） | 2 threads | 4 threads |
| --- | ---: | ---: |
| OCR backend det | 102.12 | 83.21 |
| OCR backend rec | 105.78 | 76.03 |
| llama prompt | 20.09 | 20.75 |
| llama predicted | 141.24 | 143.41 |
| HTTP request | 183.75 | 188.11 |
| frame producer deadline miss | 9.00 | 8.81 |

2 threads：測量區塊 app CPU 138.11 core-seconds、owned模型程序 CPU 17.02 core-seconds；app working-set採樣最大 278.95 MiB、模型 working-set採樣最大 1490.41 MiB。

4 threads：測量區塊 app CPU 237.72 core-seconds、owned模型程序 CPU 17.66 core-seconds；app working-set採樣最大 286.48 MiB、模型 working-set採樣最大 1490.43 MiB。

整機 CPU 間隔採樣範圍 24.22～89.40%；整機 GPU總使用顯存採樣 4612.00～6045.00 MiB。CPU間隔可能跨區塊，GPU為瞬時整機值，不能歸成本程式獨占，也不能拿來宣稱遊戲有足夠餘裕。

預生成 frame bank占磁碟 1958.10 MiB，完成後已移除；以單一16張mmap分段讀取，不把所有影像同時載入RAM。app CPU包含producer讀檔、複製與記錄，沒有即時動畫renderer；採樣最大值不是native RAM硬上限。

## 決策與限制

這份對照只決定候選是否值得進真遊戲驗收；不自動升4 threads預設。出貨仍2 threads、reuse/adaptive關閉，alpha8既有 EXE／wheel／source ZIP 沒有被重新封裝。

下一刀針對混色觸發盲點作單變項實驗，保留完整輸入，量暗字新增到OCR喚醒與完整Qt更新。短prompt之後依實際prompt／decode成本及品質保留集比較，不能用截短長句或放寬原文護欄刷速度。

11項 replay 計數回歸通過（未觀測、過期顯示、拒絕、空譯文、重复事件、700ms邊界、句尾句點容差、缺失延遲、禁止語意正確率宣稱）。初版小試跑因category標籤缺失停止，已修正；第二次2句試跑確認流程，兩者均不混入正式100句數據。

自有模型與worker均已停止、臨時frame bank已移除、凍結應用源檔一致。完整新重播尚未測真遊戲 GDI／FPS／frametime、HDR／特殊字型、實體螢幕延遲，也未完成全部譯文人工語意標註。

[完整原始資料](assets/verification/replay-threads-full-a8.json)、[三回合辯論](DEBATE_ALPHA8.md)、[舊版完整延遲](BENCHMARK_LATENCY_A8.md)。
