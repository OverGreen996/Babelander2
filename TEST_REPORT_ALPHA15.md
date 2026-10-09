# alpha15：切出暫停、切回重新讀取

2026-10-08。本輪新增框選視窗的前景生命週期，保留 alpha14 裝備數字補查、原位／原字色及現有 OCR／Qwen 模型。

## 操作

字幕／聊天框選後，記住外部視窗 HWND、PID、root owner 和當時 client 幾何；不建立遊戲設定檔、不儲存程式名、視窗標題或截圖歷史。框選結束後工作臺最小化，程式不使用 SetForegroundWindow 強迫遊戲回前景。尚未回到所選視窗時，等待前景再開始，狀態顯示於原有工作臺。

| 狀態 | 行為 |
| --- | --- |
| 綁定視窗在前景 | 正常監測；同程序、同 root owner 的 owned popup 可視為同一視窗群 |
| 切到別的視窗、最小化、隱藏／cloaked | 停止擷取／OCR 與新翻譯派送，清掉浮層內容並隱藏；保留使用者要求監測的意圖 |
| 回到原視窗 | 新 generation、新取消 token、新 guard，重新讀取目前畫面；不復活暫停前浮層 |
| 手動停止、清除、改為手動文字翻譯 | 移除自動恢復意圖，切回也不重開 |
| 視窗關閉、PID／owner 改變、視窗位置／大小改變 | 停止並提示重新框選；不猜舊 ROI 的新位置 |
| 已開始的單次裝備／任務／框選覆蓋切出 | 取消與移除，不自動重抓 |
| 第一次單次擷取尚未開始 | 可以等待所選視窗回前景後擷取一次；手動取消後不再執行 |

連續框選跨外部視窗、桌面或無法確認所屬 client 區時不啟動監測。一般未綁定的單次框選仍保持原行為，沒有自動前景暫停保障。關閉／移動／改解析度不是簡單 Alt+Tab，需重新框選。使用者主動隱藏浮層的選擇會保留。

## 管線防呆與資源

UI 200 ms 定時器只有存在綁定工作時才運作，用於浮層與狀態更新。工作端的 FocusCancellation 會在 token.check、每次擷取前後與翻譯等待期間讀取視窗狀態。即使 GUI 定時器尚未執行，也會取消候選與翻譯等待者。觀測到一次離開即鎖住該 guard；快速切出又切回也不能讓舊 generation 繼續，需要建立新 guard。UI 收到結果時再次檢查。

這不是原子的畫面／前景快照：前景仍可能在一次 native 呼叫中途切換，未觀測到的極短切換也可能漏過；擷取後再檢查可拒絕送 OCR，但不能宣稱從未配置任何切換中的畫素。已在跑的 OCR 或 Qwen 仍可能完成，不保證立即中止 CPU／GPU 推論；取消其等待與禁止更新 UI，不重送付費服務。Qt 忙碌時隱藏浮層可能延後，但工作端不依賴 GUI 定時器才能取消。

短暫自動暫停呼叫 cancel(release_model=False)，不要求立即卸載模型。原本 300 秒閒置規則、手動停止、手動卸載仍有效，不無限保留模型。ROI 緩衝、dispatcher、取消與模型 queue 上限沿用原架構，沒有新 capture／OCR worker 或第二顆模型；已取消的協調工作退出後釋放 ROI。

## 背景驗證

- 42 項前景／Qt／管線測試：手動停止不恢復、最小化恢復、視窗失效／幾何變更、API 無結果／錯誤、owned popup、跨視窗拒絕、擷取中途切出不送 OCR、晚到譯文、UI 定時器停用時仍取消、短暫保留與長時閒置卸載、單次卡片只擷取一次，以及 12 輪暫停／恢復後工作與 ROI 收斂。
- 全部既有回歸加上述測試共 **272 項**通過；不把 native 檢查或單次回放混入這個單元測試數量。
- 真 Windows API：只讀當前前景狀態；另建立本程序從未顯示的測試 HWND，檢查 enum、client 幾何、no-activate 移動、destroy 與 unregister。沒有切換使用者前景、按鍵、擷取畫面或修改既有視窗。
- Native 狀態讀取 200 次，平均 **0.1583 ms**、P95 **0.4127 ms**、最大 **1.3158 ms**。這是狀態函數單次成本，不是總 CPU／RAM 保證或完整字幕時間。
- 真 CPU OCR／CUDA Qwen／Qt offscreen，加上受控的前景狀態：第一句正常顯示、暫停後 250 ms 內擷取計數不增加、浮層隱藏、回到同一模型 PID 後讀第二句；第三句真推論進行中暫停，完成後浮層沒有重現。手動停止後回前景也未重開。
- 該次暖機後切回到完整第二句 Qt 更新為 **263.94 ms**，只有 **一個切回案例**，不是平均／P95、也不是遊戲 Alt+Tab 反應時間。
- 測試自有模型與 worker 完整停止；EXE／隔離 wheel 各跑真 OCR／CUDA／Qt 自測，打包模組與凍結原始碼一致。保留 a14，不改寫先前封存。

## 限制與依據

沒有切換正在使用的遊戲來驗證 Alt+Tab，尚無真遊戲／獨占全螢幕／防作弊環境或 FPS、frametime 測量。未重跑 a15 100 句字幕速度，不將 a13 平均 416 ms 當成本版成績。ROI 不會自動跟著搬移或縮放，視窗身分以 HWND／PID／owner 與幾何驗證，不能保證偵測同 PID 中完全同形狀的 HWND 重用。

EnumWindows 綁定針對頂層桌面視窗；未列出的特殊 UWP／overlay 視窗可能無法綁定。GetForegroundWindow 在啟用切換過程可能回 NULL，採暫停；GetAncestor 的 GA_ROOTOWNER 用於辨認 owned root。這些 API 行為依 [Microsoft EnumWindows](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumwindows)、[GetForegroundWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getforegroundwindow)、[GetAncestor](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getancestor)，相容性仍以實測為準。

[真引擎前景回放](assets/verification/window-focus-replay-a15.json) · [只讀 Win32 驗證](assets/verification/window-focus-native-a15.json) · [前景回歸](assets/verification/window-focus-checks-a15.json) · [封存核對](assets/verification/release-a15.json)
