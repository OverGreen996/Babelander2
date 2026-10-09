# Babelander 2 · 譯鄉人 — alpha23

這是第二代的首次獨立公開發布，包含可編輯原始碼、Windows x64 免安裝包與驗證資料。第一代儲存庫保留在 [OverGreen996/Babelander](https://github.com/OverGreen996/Babelander)。

## 這一版

- 六種模式：即時字幕、原位裝備卡、原位任務卡、聊天室、中文回覆與框選翻譯。
- 修正動態聊天背景的微小幾何假字，以及有周圍訊息佐證時的字形／標點抖動去重。
- 預設保留 2 OCR 執行緒；沒有為速度犧牲暗字／短訊息辨識，也沒有加入更大的模型。
- 新增視覺 README、目前版本的 Qt 介面圖、卡牌／寶石展示與快速開始文件。

## 下載

- **`Babelander2-v2.0.0a23-windows-x64.zip`**：一般使用者下載這個。完整解壓後執行 `Babelander2.exe`，保留 `_internal`。首次使用在設定內下載本機翻譯資源，或指定自己的相容模型／runtime。翻譯模型不包含在 ZIP。
- **`Babelander2-v2.0.0a23-source.zip`**：與發布 tag 對應的可編輯原始碼及測試素材。
- **`babelander_desktop-2.0.0a23-py3-none-any.whl`**：Python 套件；Windows 與 Python 3.12，仍需相依套件及翻譯資源。
- **`SHA256SUMS.txt`**：所有上傳附件的 SHA-256。第三方 source archives 是對應函式庫來源，不是額外應用程式。

## 驗證與限制

alpha23 已通過 432 項回歸、六模式／恢復 28 項驗證、原始封裝 EXE 與 wheel 各 37 項自檢及 5 分鐘生成字幕長跑。公開免安裝包移除未使用的 Qt PDF／QML／Quick／Virtual Keyboard／軟體 OpenGL 元件後，再次通過 **37 / 37** 背景自檢；EXE 與應用程式模組未修改。

公開 EXE SHA-256：`0f1eded6aeecc2059f75a7e2926bfb11a8378d0dd0674bffb24f4d3aed742723`。

暖機後，生成聊天畫面曝光到完整譯文更新 Qt：乾淨背景 100 則平均 **384ms**；動態背景預設 2 執行緒 200 則平均 **574ms、P95 1011ms**。目前**尚未全數達到 700ms**；沒有據此保證真遊戲 FPS、全部遊戲相容或語意完全正確。

詳見 [README](README.md)、[alpha23 完整報告](TEST_REPORT_ALPHA23.md)、[公開包自檢摘要](assets/verification/publication-a23.json) 與 [操作說明](docs/QUICKSTART.md)。

個人正常使用免費；自有內容著作權保留。原始碼公開不代表授予開源授權，請見 [LICENSE](LICENSE)。第三方元件依各自授權提供，對應來源與替換說明見 [THIRD_PARTY_SOURCE.md](THIRD_PARTY_SOURCE.md)。
