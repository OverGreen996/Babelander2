# 驗證紀錄

**alpha23 動態聊天修正：** 粒子假字與字形抖動不再污染本輪聊天室；三輪動態回放各 100/100，無漏訊息、重複或假字。乾淨背景平均 384ms；動態背景兩輪平均 574ms、P95 1011ms，仍未全數達 700ms。432 項回歸及 EXE／wheel 驗證通過，會漏暗字的縮圖方案未採用。[完整驗證與限制](TEST_REPORT_ALPHA23.md)。

**alpha22 聊天完整延遲：** 相同生成聊天畫面、暖模型四輪對照，平均 **719→362ms**、P95 **1089→490ms**，100ms 組 **200/200** 在 700ms 內；421 項回歸、EXE／wheel 各 37 項通過。動態雜訊增加 CPU 工作約 **3.9 倍**，可調高聊天觀察間隔；尚非真遊戲實測。[完整結果與限制](TEST_REPORT_ALPHA22.md)。

歷史 alpha21：聊天辨識重用已實作，413 項回歸及真引擎測試通過。OCR 四輪平均 405→298ms；完整翻譯平均 839ms，尚未全面達 700ms。[alpha21 驗證與限制](TEST_REPORT_ALPHA21.md)。下列 alpha8–20 為歷史紀錄。

歷史 alpha18：任務卡改成單次原位覆蓋，8 種結構／16 張畫面，兩輪 32 次真 CPU OCR／CUDA Qwen／Qt 回放與 334 項回歸檢查通過。[alpha18 任務卡驗證](TEST_REPORT_ALPHA18.md)。

歷史 alpha17 新增進遊戲前手動預載本機模型、取消與就緒提示；五組真 CUDA 文字請求對照與真載入取消／重試見 [alpha17 驗證](TEST_REPORT_ALPHA17.md)。

歷史 alpha16 新增字幕／聊天框選跟隨同螢幕、同 DPI、同尺寸的視窗平移；等待位置穩定與舊工作退出，單次卡片不重抓。見 [alpha16 驗證與限制](TEST_REPORT_ALPHA16.md)。

歷史 alpha15 加入框選視窗的前景暫停／恢復，手動停止不重開，單次裝備切出取消覆蓋；只讀 Win32 與背景真引擎回放見 [alpha15 驗證與限制](TEST_REPORT_ALPHA15.md)。

歷史 alpha14 加入裝備／卡牌數字局部補辨識，沿用原圖與單一 CPU OCR，不確定時保留原畫素。[alpha14 驗證與限制](TEST_REPORT_ALPHA14.md)。

歷史 alpha13 加入預設關閉的混色暗字觸發試驗，修正經歷否定誤擋；100 句完整 Qt 回放與資源、真實 GDI 元件測量見 [alpha13 驗證與限制](TEST_REPORT_ALPHA13.md)。

歷史 alpha12 改為 10 種獨立資訊結構、20 個案例，包含卡牌與寶石；保留各段原字色與原框線。三輪 57/60 完整檢查通過，仍有一張卡牌生命值 7 漏辨識；182 項回歸通過。[alpha12 驗證與限制](TEST_REPORT_ALPHA12.md)。

歷史 alpha11 的 32 張配色／欄位模板，三輪 96 次真 OCR／CUDA／Qt 全部完整顯示並透過當時字詞／數值、必要標記、原位排版、對比與插圖／純數字畫素檢查。168 項回歸通過；完整更新平均 580 ms、P95 824 ms，81/96 在 700 ms 內，仍非全面達標或完整語意評分。[alpha11 驗證與限制](TEST_REPORT_ALPHA11.md)。

歷史 alpha10 已更正為「單次、原位、保留裝備排版」，撤回 alpha9 的裝備跟讀。159 項回歸通過，8 張小卡真 OCR／CUDA／Qt 平均 442 ms；複雜使用者卡片約 1.24 秒，未全面達到 700 ms。[完整 alpha10 驗證與限制](TEST_REPORT_ALPHA10.md)。

日期：2026-10-08。新增字幕行位置重用與設定開關；**仍未完成真遊戲／通用字色／700 ms 全面驗收**。

**目前不建議開啟行重用。** 完整動態背景測試，control 平均 555.52 ms、P95 1139.97 ms、80/100 句於 700 ms 內；開啟輪平均 742.48 ms、P95 2097.56 ms、59/100。混色真 OCR 發現兩個高信心截字失敗。這個實驗不能算效能改善驗收透過，預設保持關閉。

| 範圍 | 結果 | 證據 |
| --- | --- | --- |
| 核心邏輯與排程 | 57 項透過 | [core](assets/verification/unit-tests-a8.json) |
| 管線／Qt／取消／有界交接／設定儲存 | 41 項透過 | [pipeline](assets/verification/pipeline-a8.json) |
| 資產下載合約 | 12 項透過，合成 transport | [assets](assets/verification/asset-unit-a8.json) |
| 行位置安全條件 | 15 項透過，合成 OCR | [layout](assets/verification/layout-unit-a8.json) |
| 新 EXE 真 Qt、CPU OCR、本機模型、加速設定 | 18 項透過 | [EXE](assets/verification/bundle-selftest-a8.json) |
| 隔離 wheel 真實功能 | 18 項透過，32 個 app 源檔／QSS 相符 | [wheel](assets/verification/wheel-a8.json) |

單元總計 125 項。新增檢查包含同 episode 複查做完整偵測、新 episode 使用近期提示、換行／移位／形狀／彩字／低信心退回、現有字幕框不能限制新句寬度、相鄰行 padding 不截字，以及提示不跨 session、不用於卡片／聊天室。

所有 Qt 測試在 offscreen，沒有測試視窗／全域快捷鍵佔用桌面。EXE／wheel 做功能檢查；完整 100 句背景對照是凍結原始碼測試，**不是 EXE 的 100 句長測**。單元與資產檢查不發真實 API，OCR／模型使用本機資產。

[額外 8 個真 OCR 對照](assets/verification/layout-adversarial-a8.json) 包含 6 個與 full 一致及 2 個混色截字；這組沒有宣稱全數透過，也不混入上面的單元透過數量。

## 完整反應時間

同一組 100 句、每句 3 秒，兩輪都持續背景動畫：control 與行重用。兩輪同樣 4 OCR threads、自適應複查、100 ms 觀察／穩定等待；模型暖機、每輪清 cache。以文字出現到完整 Qt 更新量測，保留 strict source 與句尾句點容差指標、失敗與慢句。

完整資料與限制：[alpha8 動態背景對照](BENCHMARK_LATENCY_A8.md)。固定合成白字不代表通用遊戲 recall 或人工語意正確率；整機 CPU/GPU 負載可變，順序兩輪不視為乾淨因果 A/B，沒有量測實體顯示／GDI／遊戲 frametime。

## 使用與發行

設定 →「OCR 執行緒」可選 1–4；「白字字幕加速（試驗）」控制此功能。按儲存會停止既有工作，下次開始監測使用新值。

**預設仍 2 threads、行重用關閉、自適應複查關閉。** 暗字混在白字旁邊或新暗字行可能漏字，因此沒有自動開啟。較大模型／新的 prompt／DXGI 沒有與此改動混在一起；原文不出現在浮層、沒有新增模型或額外 OCR engine。

- 執行檔：`dist/releases/2.0.0a8/Babelander2/Babelander2.exe`，保留完整 `_internal`。
- 可編輯來源：`dist/Babelander2-2.0.0a8-source.zip`。
- wheel：`dist/babelander_desktop-2.0.0a8-py3-none-any.whl`。
- [源檔凍結](assets/verification/frozen-source-a8.json)；建置模組與來源對照由 `release_snapshot.py` 驗證，校驗資料在 `dist/Babelander2-2.0.0a8-sha256.json`。

舊發行與證據保留：[alpha7](TEST_REPORT_ALPHA7.md)、[alpha6](TEST_REPORT_ALPHA6.md)。仍需真遊戲長測、暗／混色短字幕、特殊字型、語意與數字／時間護欄，以及模型 prompt 的獨立品質／延遲評估。
