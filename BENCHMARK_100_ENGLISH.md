# 100 句全新英文：反應時間實測

日期：2026-10-08；Babelander 2.0.0a4／RTX 3080 Ti／Qwen3-1.7B Q4_K_M／llama.cpp b10896 CUDA。

**模型暖機後，純翻譯平均 107.44 ms；自製英文圖片經 OCR、翻譯至 Qt 介面更新，平均 352.71 ms。**

同一批 100 個全新、不重複的英文句子，短句、劇情、行動指示、條件／數值、長句各 20。與前次 fixture 報告／程式案例檢查無完全相同句子。全數以字幕模式的同一 prompt 執行，沒有改模型／profile／context／thinking 設定。每句翻譯一次，再清空測試快取跑一次 OCR 至 UI；共 200 次實際本機模型請求、快取命中 0 次、付費 API 0 次。

## 時間結果

單位 ms；平均使用算術平均，P50／P95 使用 nearest-rank。表中「回應」包含護欄拒絕的決定時間，有譯文者另列，沒有隱藏失敗的三句。

| 測試路徑 | 平均 | P50 | P95 | 最慢 |
| --- | --- | --- | --- | --- |
| 純翻譯：全部 100 句（含首次載模型） | 124.67 | 102.30 | 172.89 | 1829.94 |
| 純翻譯：模型暖機後 99 句 | 107.44 | 102.30 | 172.89 | 186.34 |
| OCR → 翻譯 → Qt 更新：全部 100 句 | 352.71 | 305.58 | 525.87 | 1184.59 |
| OCR → 翻譯 → Qt 更新：首次 OCR 初始化後 99 句 | 344.31 | 305.58 | 525.87 | 565.45 |
| OCR → 翻譯 → Qt 更新：有可顯示譯文 97 句 | 350.38 | 305.00 | 529.50 | 1184.59 |

首次需要模型的純翻譯耗時 **1829.94 ms**，包含載入；首次 OCR 流程耗時 **1184.59 ms**，此時模型已暖機，包含懶載入 OCR／辨識／翻譯／Qt 更新，不能全部算成 OCR 初始化。暖機後單獨 OCR 階段平均 223.57 ms。整個雙遍流程約 48.48 秒。

| 句型 | 全新句數 | 暖機純翻譯平均 ms | OCR 暖機後整條流程平均 ms |
| --- | --- | --- | --- |
| 短句 | 20 | 71.53（n=19） | 231.43（n=19） |
| 劇情 | 20 | 94.94（n=20） | 306.26（n=20） |
| 行動指示 | 20 | 105.12（n=20） | 297.73（n=20） |
| 條件／數值 | 20 | 111.12（n=20） | 389.30（n=20） |
| 長句 | 20 | 152.71（n=20） | 491.16（n=20） |

## 品質與拒絕

自製圖片的 OCR 空白正規化後逐句完全一致：**100／100**。兩遍均為 **97 句有可顯示譯文、3 句被否定護欄擋下**；這不等於 97% 語意準確率，未對所有譯文做人工標註。

額外針對這三句做 **3 次診斷重跑**，捕捉後端原始輸出，完全不納入上述平均。三句的否定都以「從未／未」表達，現有護欄只接受「不／勿／別／禁止／無須／毋須」，所以否定檢查有誤擋。第 86 句另有 `treasury` 殘留英文，仍有翻譯完整度問題，不能把誤擋解除當成語意品質通過。這次只測量與記錄，沒有變更已測試的應用程式碼。

| 案例 | 英文 | 診斷重跑的繁體正規化輸出 |
| --- | --- | --- |
| 29 | Your father never told me why he burned the final map. | 你父親從未告訴我他為什麼燒毀最後的圖紙。 |
| 86 | The prisoner claims he never entered the treasury, although the guards found a matching piece of his torn coat caught on the inner door. | 囚犯聲稱他從未進入過 treasury，儘管守衛們在內門上發現了與他撕破外套上的一塊匹配的碎片。 |
| 97 | If the signal does not arrive by midnight, assume the rescue failed and lead the remaining survivors to the shelters beneath the old observatory. | 若訊號在午夜前未到達，則假設救援失敗，並帶領餘下倖存者前往舊觀測站下方的避難所。 |

## 測量邊界

使用 Qt **offscreen** 與 1450 × 250 px 自製高對比圖片，字型 Arial 30 pt、CPU OCR、完整原解析度。圖片繪製在計時前完成；擷取替代為記憶體複製，仍使用 Controller／Engine／實際 MainWindow receiver。結束點是 Qt slot 已更新 target／警告；不代表螢幕 compositor 已呈現遊戲浮窗。

**不包含真實 GDI 擷取、遊戲動畫、800 ms 掃描排程或 300 ms 穩定判斷；不能解讀為字幕出現後固定 0.35 秒便看到譯文。** 這是同機、連續單件工作、沒有排隊壓力的測試，模型可能受益於共同 prompt 的後端 prefix cache；不是所有遊戲的平均速度。未開桌面測試視窗、未註冊測試快捷鍵、不讀取使用者畫面／設定，結束後自有模型與 worker 均已停止。

## 可重現資料

- [100 句完整英文](assets/verification/english-100-corpus-a4.json)
- [逐句譯文、OCR 結果與毫秒紀錄](assets/verification/english-100-a4.json)
- [三句護欄診斷重跑](assets/verification/english-100-diagnostics-a4.json)

測試腳本：`probe_100_english.py`；診斷：`probe_100_diagnostics.py`。200 次本機請求屬主測試，另三次為診斷；沒有自動 API 重試。
