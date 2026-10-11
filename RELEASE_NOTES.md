# Babelander 2 · 譯鄉人 — alpha24

這版加速 OCR 前處理與聊天舊行辨識，保留六種模式、原有模型及預設 2 個 OCR CPU 執行緒。

## 改了什麼

- OCR 偵測前處理改用等值色階查表，保留原動態解析度與輸入張量精度。
- 聊天部分行命中快取後，沿用原批次寬度，避免再次推論已快取的最長行。
- 固定 208 張畫面前後 OCR 文字全部相同，保留小字、暗字、數量與否定句驗收。

## 實測與限制

同一批動態聊天以舊／新／新／舊四輪對照：完整譯文平均 **526→482ms**、P95 **882→796ms**，OCR 單次 P95 **518→474ms**。每輪 100/100 則收到。乾淨背景另測 100 則，平均 **299ms**、P95 **402ms**，全數在 700ms 內。

以上為暖機後生成畫面曝光到完整譯文更新 Qt 的時間，包含觀察等待。動態背景仍未全面達 700ms，完整流程最慢約 **1.20 秒**；因辨識次數增加，應用程序 CPU 每秒用量約升 **3.6%**。沒有宣稱真遊戲 FPS 或全面語意準確率。

439 項回歸、32 項真 OCR 邊界、8 項聊天事件、28 項六模式／生命週期檢查通過。原始 EXE、隔離 wheel 及整理後公開免安裝包各 37 項自檢通過；40 個應用模組與已測原始碼一致。詳見 [完整報告](TEST_REPORT_ALPHA24.md)、[驗證摘要](assets/verification/ocr-chat-a24/summary.json) 與 [公開包自檢](assets/verification/publication-a24.json)。

## 下載

- **`Babelander2-v2.0.0a24-windows-x64.zip`**：一般使用者下載這個。完整解壓後執行 `Babelander2.exe`，保留 `_internal`。首次使用於設定下載本機翻譯資源，或指定已有模型／runtime；ZIP 不包含翻譯模型。
- **`Babelander2-v2.0.0a24-source.zip`**：與 tag 對應的可編輯原始碼及測試素材。
- **`babelander_desktop-2.0.0a24-py3-none-any.whl`**：Windows / Python 3.12 套件，另需相依套件與翻譯資源。
- **`SHA256SUMS.txt`**、**`release-manifest.json`**：附件大小與 SHA-256。其他 source archives 為第三方函式庫對應來源。

[操作說明](docs/QUICKSTART.md) · [README](README.md) · [第三方來源與替換](THIRD_PARTY_SOURCE.md)

個人正常使用免費；自有內容著作權保留，原始碼公開不代表授予開源授權。請見 [LICENSE](LICENSE)，第三方元件依各自授權提供。
