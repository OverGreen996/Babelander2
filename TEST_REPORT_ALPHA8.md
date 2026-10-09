# alpha8 驗證紀錄

日期：2026-10-08。新增字幕行位置重用與設定開關；**仍未完成真遊戲／通用字色／700 ms 全面驗收**。

**目前不建議開啟行重用。** 完整動態背景測試，control 平均 555.52 ms、P95 1139.97 ms、80/100 句於 700 ms 內；開啟輪平均 742.48 ms、P95 2097.56 ms、59/100。混色真 OCR 發現兩個高信心截字失敗。這個實驗不能算性能改善驗收通過，預設保持關閉。

| 範圍 | 結果 | 證據 |
| --- | --- | --- |
| 核心邏輯與排程 | 57 項通過 | [core](assets/verification/unit-tests-a8.json) |
| 管線／Qt／取消／有界交接／設定保存 | 41 項通過 | [pipeline](assets/verification/pipeline-a8.json) |
| 資產下載合約 | 12 項通過，合成 transport | [assets](assets/verification/asset-unit-a8.json) |
| 行位置安全條件 | 15 項通過，合成 OCR | [layout](assets/verification/layout-unit-a8.json) |
| 新 EXE 真 Qt、CPU OCR、本機模型、加速設定 | 18 項通過 | [EXE](assets/verification/bundle-selftest-a8.json) |
| 隔離 wheel 真實功能 | 18 項通過，32 個 app 源檔／QSS 相符 | [wheel](assets/verification/wheel-a8.json) |

單元總計 125 項。新增檢查包含同 episode 複查做完整偵測、新 episode 使用近期提示、換行／移位／形狀／彩字／低信心退回、現有字幕框不能限制新句寬度、相鄰行 padding 不截字，以及提示不跨 session、不用於卡片／聊天室。

所有 Qt 測試在 offscreen，沒有測試視窗／全域快捷鍵佔用桌面。EXE／wheel 做功能檢查；完整 100 句背景對照是凍結原始碼測試，**不是 EXE 的 100 句長測**。單元與資產檢查不發真實 API，OCR／模型使用本機資產。

[額外 8 個真 OCR 對照](assets/verification/layout-adversarial-a8.json) 包含 6 個與 full 一致及 2 個混色截字；這組沒有宣稱全數通過，也不混入上面的單元通過數量。

## 完整反應時間

同一組 100 句、每句 3 秒，兩輪都持續背景動畫：control 與行重用。兩輪同樣 4 OCR threads、自適應複查、100 ms 觀察／穩定等待；模型暖機、每輪清 cache。以文字出現到完整 Qt 更新量測，保留 strict source 與句尾句點容差指標、失敗與慢句。

完整數據與限制：[alpha8 動態背景對照](BENCHMARK_LATENCY_A8.md)。固定合成白字不代表通用遊戲 recall 或人工語意正確率；整機 CPU/GPU 負載可變，順序兩輪不視為乾淨因果 A/B，沒有量測實體顯示／GDI／遊戲 frametime。

## 使用與發行

設定 →「OCR 執行緒」可選 1–4；「白字字幕加速（試驗）」控制此功能。按儲存會停止既有工作，下次開始監測使用新值。

**預設仍 2 threads、行重用關閉、自適應複查關閉。** 暗字混在白字旁邊或新暗字行可能漏字，因此沒有自動開啟。較大模型／新的 prompt／DXGI 沒有與此改動混在一起；原文不出現在浮層、沒有新增模型或額外 OCR engine。

- 執行檔：`dist/releases/2.0.0a8/Babelander2/Babelander2.exe`，保留完整 `_internal`。
- 可編輯來源：`dist/Babelander2-2.0.0a8-source.zip`。
- wheel：`dist/babelander_desktop-2.0.0a8-py3-none-any.whl`。
- [源檔凍結](assets/verification/frozen-source-a8.json)；建置模組與來源對照由 `release_snapshot.py` 驗證，校驗資料在 `dist/Babelander2-2.0.0a8-sha256.json`。

舊發行與證據保留：[alpha7](TEST_REPORT_ALPHA7.md)、[alpha6](TEST_REPORT_ALPHA6.md)。仍需真遊戲長測、暗／混色短字幕、特殊字型、語意與數字／時間護欄，以及模型 prompt 的獨立品質／延遲評估。
