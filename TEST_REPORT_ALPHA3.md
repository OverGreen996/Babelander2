# 第二代測試紀錄

日期：2026-10-07–08；Windows 11 x64、Python 3.12.14、RTX 3080 Ti、Qwen3-1.7B Q4_K_M、llama.cpp CUDA。

**本輪版本 2.0.0a3：最終 EXE 已完成 1800 秒背景監測，589 次結果，所有預設檢查通過。** 最終長測使用 Qt offscreen 自製圖片、真正 OCR 與 CUDA，沒有實際桌面擷取，也不是遊戲驗收。

alpha 3 本輪先完成真正桌面的原生 UI 核對，再因使用者要求不佔用桌面，將最終 EXE／隔離 wheel 自測及長測改為 Qt offscreen。核心回歸重跑；六模式／API／下載／OCR 基準及模型生命週期報告沿用 alpha 2，沒有把它們算成新請求或新測量。

新增畫面核對：最近一次 ROI 的縮圖、行框、每行信心、縮放與停止後編輯。每模式只保留最近一次記憶體快照，縮圖上限 1600 × 1000 px，不寫入使用者歷史或磁碟；對話框凍結開啟時內容，避免核對到一半更換畫面。空白辨識也可核對。

監測只對暫時畫面存取失敗重試，依序等待 1、2 秒；連續第三次失敗停止，取消可中斷等待。資源配置錯誤、OCR 和翻譯服務錯誤不重試。快取改為 SQLite 原子遞增的存取順序，修正相同時間戳與倒退時鐘下的淘汰問題，保留既有資料。

## 實際執行結果

| 層級 | 結果 | 報告 |
| --- | --- | --- |
| 核心回歸 | 57 個測試通過 | [unit-tests.json](assets/verification/unit-tests.json) |
| 原生 UI 與真正桌面擷取 | 61 個檢查通過，含六模式、全域快捷鍵、九頁與兩種視窗尺寸 | [audit.json](assets/verification/audit.json) |
| 真實 OCR／CUDA／六模式 | 全部完成，沒有保留原文警告 | [real-local.json](assets/verification/real-local.json) |
| Google／Azure／DeepL | 6 次真實請求成功；重複文字沒有額外請求 | [real-cloud.json](assets/verification/real-cloud.json) |
| 打包 EXE 2.0.0a3 | 17 個檢查通過，含畫面核對、Qt、OCR、繁體轉換、卡片條件、低信心護欄與下載／卸載操作 | [packaged.json](assets/verification/packaged.json) |
| OCR 改善 | 五種素材各三次暖機後取中位數，兩種設定辨識文字均一致 | [ocr-benchmark.json](assets/verification/ocr-benchmark.json) |
| 資源生命週期 | 300 次真實擷取，GDI 物件 6 → 6；3 次模型載入中取消皆回收自有程序 | [lifecycle.json](assets/verification/lifecycle.json) |
| 下載核心／Qt 操作 | 12 個故障合約測試、6 個原生 worker 檢查 | [asset-unit.json](assets/verification/asset-unit.json)、[asset-ui.json](assets/verification/asset-ui.json) |
| 真實資產續傳／安裝 | 三個上游資產各續傳最後 64 KiB，再完整雜湊、解壓、執行版本檢查 | [real-assets.json](assets/verification/real-assets.json) |
| 模型中斷／卸載／重載 | 7 個真實 CUDA 生命週期檢查通過 | [model-lifecycle.json](assets/verification/model-lifecycle.json) |
| alpha 2 原始 30 分鐘監測 | 1800 秒、589 次結果；暖機後 GDI 21–25，私有記憶體 663.2–714.8 MB，零監測錯誤；翻譯警告項失敗，保留原紀錄 | [soak.json](assets/verification/soak.json) |
| 修正後相同循環複測 | 180 秒、59 次結果，所有檢查通過 | [soak-retest.json](assets/verification/soak-retest.json) |
| alpha 3 最終 EXE 背景 30 分鐘 | 1800 秒、589 次結果，零警告、零錯誤；Qt offscreen／真實 OCR／CUDA，關閉後 worker／自有模型停止 | [soak-frozen-a3-background.json](assets/verification/soak-frozen-a3-background.json) |
| 額外翻譯樣本 | 22 句，22 句通過結構檢查、0 句保留原文 | [quality.json](assets/verification/quality.json) |
| 獨立 wheel | 安裝到別處，隔離匯入後通過自測；檔案逐一吻合目前原始碼 | [wheel.json](assets/verification/wheel.json) |

核心測試包括過期結果與歷史、字幕優先與卡片讓出模型、空白字幕清除及同句再次出現、聊天重複／捲動、同文請求合併與取消、例外後 worker 存活、500 個併發送件、容量與關閉、DPAPI、快取／詞庫、用量上限、逾時只送一次、名稱與數字／時間單位／常見否定保護。

UI 另外驗證過期錯誤不能停止新工作、舊狀態不能覆蓋新狀態、浮層手動隱藏後仍維持隱藏、恢復互動、聊天清除、回覆 Enter 與草稿、框選轉換、Win32 快捷鍵派送、視窗排除擷取及所有 worker 關閉。

第二輪加驗真正多行 OCR 條件與 Otherwise 同組、浮層空白像素 alpha=0／文字不降低透明度、標題拖曳、座標與大小對話框、背景與位置保存、移除螢幕後恢復可見位置、低信心原文可編輯、浮層核對提示與忙碌時 Enter 不重複送件。原生 audit 和長測同時執行，使用分開的示範視窗區域與不同的快捷鍵組；UI 時間數字含並行負載，不作純推論基準。

## OCR 真正改善了什麼

RapidOCR 的預設 `min` 將短邊放大到 736 px，對狹長字幕增加大量處理像素；新版使用 `max` 長邊限制。以下是同機、自製白底黑字 Arial、14–28 pt、單行與多行素材的暖機後結果：

| 素材 | 調整前中位數 ms | 調整後中位數 ms | 比值 | 辨識內容 |
| --- | ---: | ---: | ---: | --- |
| card-multiline-18 | 1279.26 | 203.89 | 6.27× | 一致 |
| chat-14 | 684.30 | 102.98 | 6.64× | 一致 |
| dialog-28 | 587.81 | 113.25 | 5.19× | 一致 |
| equipment-22 | 706.90 | 121.05 | 5.84× | 一致 |
| quest-16 | 723.47 | 122.23 | 5.92× | 一致 |

每個數值是 3 次暖機後測量的中位數。這不包含 OCR 初次載入，也不是所有遊戲畫面、特殊字體或背景的準確率證明。

## 真正桌面的最新 UI 流程

| 模式 | 工作總計 ms | OCR ms | 快取命中 |
| --- | ---: | ---: | --- |
| dialog | 1217 | 880 | 1/1 |
| equipment | 128 | 125 | 1/1 |
| quest | 128 | 127 | 1/1 |
| chat | 1491 | 106 | 0/1 |
| reply | 83 | 0 | 0/1 |
| screen | 1 | 0 | 1/1 |
| reply | 0 | 0 | 1/1 |
| equipment | 294 | 290 | 2/2 |
| reply | 54 | 0 | 0/1 |

此 audit 設定掃描 300 ms、穩定等待 150 ms；程式預設分別為 800 ms、300 ms。字幕總計包含辨識、穩定等待與工作處理，首次 OCR 包含模型載入。卡片／字幕部分命中持久快取；**這些數據不可直接當成模型推論基準**。

## 真實雲端

| 引擎 | 功能 | 請求到返回 ms | 結構檢查 | 重複請求走快取 |
| --- | --- | ---: | --- | --- |
| google | dialog | 236.13 | 通過 | 是 |
| google | reply | 113.03 | 通過 | 是 |
| azure | dialog | 875.37 | 通過 | 是 |
| azure | reply | 278.38 | 通過 | 是 |
| deepl | dialog | 888.66 | 通過 | 是 |
| deepl | reply | 888.11 | 通過 | 是 |

每家 2 次、共 6 次小量示範文字；每家請求 49 個輸入字元。本輪使用獨立暫存 V2 用量帳，不改第一代帳目。金鑰由既有 DPAPI 檔案於程序內解密，沒有複製、匯出或儲存到新版。樣本不能推論服務商長期延遲或可靠度。

## 打包與原始碼

最後的 EXE 用新的虛擬環境建置，實際跑通 Qt、包內 OCR 與外部模型；測試退出碼 0，沒有匯入第一代應用模組或依賴路徑。`release_snapshot.py` 另逐一核對打包模組的編譯內容與目前原始碼，建立 EXE／wheel／源碼 ZIP 的 SHA-256 紀錄於 `test-results/artifacts.json`。

第一輪打包受到 PATH 的第三方 ICU 同名 DLL 污染，Qt 匯入失敗；限制建置 PATH 後修好。TensorRT／ONNX 量化工具屬本輪未使用的可選套件，不納入 CPU OCR 的功能驗收。

## 長時間監測與模型回收

alpha 2 的 30 分鐘使用自製白底視窗與真正 GDI 擷取。alpha 3 最終長測改用 Qt offscreen 自製圖片，沒有桌面視窗或全域快捷鍵；兩者皆採 300 ms 掃描、150 ms 穩定等待，每 3 秒更換文字，每分鐘清除測試快取，持續要求本機 CUDA 翻譯。報告保存程序 RSS／私有記憶體、控制代碼與結果數；閾值預先設定。背景測試移除 GDI 驗收項，改驗證 offscreen 平台，沒有將未執行的 GDI 路徑列為通過。

本輪原先的桌面長測在約 25 分鐘中斷：使用者要求不要阻擋操作，且後段框選區曾被其他視窗遮住，產生 20 次低信心警告。保留中斷狀態與資源紀錄；意外混入的非測試視窗原文已移除，不匯出。見 [桌面長測中斷紀錄](assets/verification/soak-desktop-a3-interrupted.json)。它不算完成或通過。

已核對兩個中斷測試的暫存 SQLite，只替換非固定示範句的原文／譯文：共 22 筆歷史，未改實際 Babelander 使用者資料。診斷目錄保留；清理結果見 [測試文字遮蔽紀錄](assets/verification/temp-redaction.json)。

另一次背景嘗試只有 60 秒的進度，程序結束但沒有最終報告；原因未確認，沒有保留退出碼，因此不算通過。記錄於 [未完成的背景嘗試](assets/verification/soak-background-a3-incomplete.json)。最後另以等待子程序結束的監督程序重跑完整長測，保留退出碼。

原先 alpha 2 長測期間另有程式修改，因此原紀錄不代表最終 EXE。alpha 3 已先凍結程式、建置 EXE，再由同一個 EXE 執行包內長測，期間不修改應用模組；報告含 frozen 標記、版本、EXE SHA-256，每個應用源碼 SHA-256 也核對一致。

最終 EXE 背景長測：暖機後控制代碼 551–560，私有記憶體 635.5–664.1 MB。固定四句每三秒循環，並非隨機遊戲文字、Win32 擷取或翻譯準確率評測。

另以 Win32 EnumWindows 唯讀核對該背景測試 PID，快照檢查為 0 個可見頂層視窗；不讀取其他應用內容。見 [背景視窗核對](assets/verification/background-ui.json)。首次 offscreen 嘗試沒有載入字型，文字呈方塊、OCR 空白；明確載入本機 Windows Arial／Segoe UI／微軟正黑體後重新打包，自測與長測均用這個修正版本。

工作台長測的記憶體統計不含獨立 llama.cpp 程序與 GPU 顯存。另在長測啟動後開始唯讀旁觀，只記錄該測試 PID 的自有模型子程序：觀測 1813 秒，共有 59 筆記錄，私有記憶體 1999.2–2001.6 MB。原始 nvidia-smi 顯存欄位也保存，null／N/A 代表資料不可用，不能當作零；不宣稱完整 30 分鐘顯存驗收。見 [模型資源旁觀紀錄](assets/verification/soak-model-resources-a3.json)。

模型生命週期測試真正終止自有子程序、重啟、卸載和重載；自動閒置路徑以調整最後請求時間觸發，沒有宣稱另等足 5 分鐘。

## 真正找到的品質缺失

額外 22 句測試找到簡體混入，已加入 OpenCC `s2twp` 正規化；使用者明確指定的詞庫目標保持原樣，包含刻意使用的簡體專名。轉換庫和字典已隨 EXE 打包並實測。

初測觀察到 Qwen3-1.7B 的字面譯法，例如 portal → 門口、maintenance window → 維護窗戶，以及帶座標回覆遺漏否定。調整保留命令、時序與情境詞義的提示後，這些本輪樣本改善；仍有「如果 boss 目標你」等不自然句型。數值與條件結構檢查不能發現所有語意錯誤，22/22 結構通過不是翻譯準確率。下一步仍應以人工標註資料比較模型與提示。

原先 30 分鐘共 147 次保留原文警告，時間規律對應固定的第三句。原始長測未保存每次警告原因，因此另跑診斷：真正 OCR 信心 99.714%，模型把 `Do not enter the dungeon yet.` 回成 `尚未進入地牢。`，將禁令改成狀態。護欄確實擋下，但這句沒有正常翻譯。追加提示仍不穩定，因此新增有限、完整匹配的 `Do not enter/leave ... yet` 規則，尊重詞庫、不套用含額外條件的句子；先複測 180 秒，再由 alpha 3 最終 EXE 跑完整 30 分鐘通過。**原始失敗報告完整保留；新版結果存為獨立報告。**

下載器的真實網路驗證每檔從既有已驗證內容保留前段，再由上游續傳最後 64 KiB；之後對整檔驗證 SHA-256，完整安裝並由最終 EXE 使用該模型／runtime 翻譯。從零寫入的 HTTP 路徑有受控回應測試，本輪沒有重新經網路下載全部 1.93 GB。

## 待驗與功能差距

- 各款真實遊戲的無邊框擷取、浮層排除與聊天捲動。
- 混合 DPI 多螢幕、不同 GPU／CPU及真正遊戲的長測。
- 高信心 OCR 誤讀、特殊卡片分組和更大的人工語意評測集。
- 裝備／任務原卡完整色彩、裝飾與位置重建。
- 第二代遠端 OTA、安裝器、發行簽章及異地源碼備份。

詳細下一步見 [ARCHITECTURE.md](ARCHITECTURE.md)。不會用「結構檢查通過」宣稱每句翻譯語意都正確。
具體樣本與參考譯法見 [QUALITY_REVIEW.md](QUALITY_REVIEW.md)，原始模型輸出完整保留。
