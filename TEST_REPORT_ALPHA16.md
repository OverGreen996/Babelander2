# alpha16：框選區跟隨遊戲視窗平移

2026-10-08。字幕與聊天的框選區維持相對 client 的實體像素偏移，視窗在同一螢幕平移後不用重新框選。保留 alpha15 的前景暫停／恢復、手動停止、一次性裝備覆蓋，以及既有 OCR／Qwen。

## 行為與邊界

| 情況 | 行為 |
| --- | --- |
| 同視窗、同螢幕、同回報 DPI、同 client 尺寸，只有位置改變 | 先暫停與清掉浮層，確認新位置穩定後移動 ROI，再以新 generation 辨識 |
| 持續拖動 | 每次座標改變重新計時；只保留每模式一件幾何候選，不跑新 OCR |
| 位置穩定 | 至少 200 ms 後再次觀察相同座標；舊協調工作退出後才能建立新工作 |
| 已移動但不在前景 | 可以確認新 ROI，仍等原視窗回前景才辨識 |
| 回到原位置 | 恢復原 ROI，不累積偏移 |
| 手動停止 | 清除候選及恢復意圖，後續位置變化不重開 |
| client 尺寸、DPI、螢幕或螢幕邊界改變 | 停止，要求重新框選；不按比例縮放 ROI |
| ROI 超出原 client 或新 ROI 超出同一螢幕 | 不推算，不擷取，要求重新框選 |
| 裝備／任務／一般框選的單次工作 | 視窗移動取消覆蓋，不跟隨、不重抓；尚未開始的單次擷取也不推算新位置 |

正常字幕浮層維持使用者設定位置，跟隨的是**擷取框選區**。不強迫遊戲或工作臺到前景、不新增設定頁或遊戲設定檔。

## 管線與資源

`WindowBinding` 新增 monitor handle、window DPI 與 monitor bounds，只有記憶體中的視窗身分與幾何資訊。`rebase_region` 驗證身分、尺寸、DPI、螢幕與 ROI 界限，只加上 client 原點差值，保留 ROI 寬高。未取得完整資訊就拒絕自動跟隨。

工作端原 guard 在位置／顯示資訊改變後失效，擷取前後、OCR／翻譯等待與 UI 發布繼續檢查。新 ROI 使用新 guard、新 generation；過期譯文不能顯示。已執行的 OCR／Qwen 仍可能完成，不宣稱立即中止推論。

`Controller.working(mode)` 計入執行及排隊中的協調工作；完成、取消 Future 或提交失敗均釋放計數與原 admission slot。移動恢復等舊協調工作退出，避免在連續拖動時累積替代工作。不等待共享 Qwen 已執行推論結束，模型排程仍沿用原上限。

沿用既有 200 ms UI 前景定時器與 capture worker，沒有新增定時器、背景執行緒、OCR 引擎、模型或圖片歷史。每模式最多一件移動候選。短暫暫停保留模型、長時閒置卸載規則維持。

## 實測

- **290 項回歸通過**：核心 59、資產 12、管線 43、排版 15、裝備 60、字幕觸發 11、回放統計 11、裝備數字補查 19、前景／移動 60。前景組新增 18 項，涵蓋負座標、12 次往返無漂移、視窗身分／DPI／螢幕拒絕、舊模型結果、手動停止、卡片不重抓，以及舊 OCR 未退出時不能重開。
- 真 Win32 API **10 項**通過：只操作自有從未顯示的 HWND，讀取 client／monitor／DPI、以 NOACTIVATE 移動 50 px，驗證 ROI 平移及隱藏視窗拒絕，再銷毀及取消類別註冊。沒有切換前景、按鍵、讀取使用者畫面或修改既有視窗。
- Native 狀態函數讀取 200 次，平均 **0.0319 ms**、P95 **0.0687 ms**、最大 **0.1494 ms**。這是單次元件成本，不是總資源消耗或完整翻譯時間，也不與 a15 不同時刻的讀取測量宣稱加速。
- 真 CPU OCR／CUDA Qwen／Qt offscreen，前景與移動使用受控 fixture：**12 項**通過。移動前後保持同一模型程序，捕捉到的新 ROI 正確，第三句完整更新，舊結果不重現，手動停止不重開。
- 單次暖機後切回到完整 Qt 為 **239.05 ms**；單次觀測視窗移動到完整新譯文為 **531.93 ms**，包含位置穩定等待。兩者各一個案例，**不是平均／P95、不是遊戲實測**，沒有拿 a13 的 100 句數據當成本版成績。
- 打包 EXE、隔離 wheel 各通過 **20 項**真 OCR／CUDA／Qt 自測；凍結 37 個應用檔案與編譯模組／wheel 原始檔一致。測試自有模型及 worker 完整停止。

## 尚未驗證

沒有操作正在使用的遊戲或測試真實多螢幕拖動；遊戲 Alt+Tab、DPI 切換、獨占全螢幕、防作弊及 FPS／frametime 仍需實測。Win32 前景與幾何讀取不是原子快照，未觀察到的瞬間變化可能漏過；擷取後 guard 再檢查，但不能保證從未配置切換期間畫素。

window DPI 依目標視窗 DPI awareness 回報，不能偵測所有遊戲內 UI 縮放、相同幾何下的字幕重新排版，或同 PID／同形狀的 HWND 重用。遇到內容位置變更仍需重新框選。monitor 改變、尺寸／縮放改變不做自動縮放或跨螢幕跟隨。

API 依據：[Microsoft MonitorFromWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-monitorfromwindow)、[GetMonitorInfoW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getmonitorinfow)、[GetDpiForWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getdpiforwindow)。GetDpiForWindow 的結果依視窗 DPI awareness；monitor bounds 使用虛擬桌面座標，可為負數。

[前景／移動回歸](assets/verification/window-focus-checks-a16.json) · [真引擎背景回放](assets/verification/window-move-replay-a16.json) · [Win32 核對](assets/verification/window-focus-native-a16.json) · [發行核對](assets/verification/release-a16.json)
