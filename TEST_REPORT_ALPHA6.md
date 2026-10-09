# alpha6 驗證紀錄

日期：2026-10-08。此版是開發版本，**700 ms 尚未全面達標**。

## 實際完成的檢查

| 範圍 | 結果 | 證據 |
| --- | --- | --- |
| 核心邏輯與排程 | 57 項通過 | [core](assets/verification/unit-tests-a6.json) |
| 管線／Qt／取消／有界交接 | 35 項通過 | [pipeline](assets/verification/pipeline-a6.json) |
| 資產下載合約 | 12 項通過，合成 transport | [assets](assets/verification/asset-unit-a6.json) |
| 新 EXE 真 Qt、CPU OCR、本機模型 | 17 項通過 | [EXE](assets/verification/bundle-selftest-a6.json) |
| 隔離 wheel 真實功能 | 17 項通過，31 個 app 源檔／QSS 相符 | [wheel](assets/verification/wheel-a6.json) |

全部在 offscreen 下執行，沒有測試視窗或測試快捷鍵覆蓋桌面；單元與資產測試不發真實 API，本輪 EXE／wheel 功能檢查使用本機模型。沒有測真實 GDI、遊戲 FPS 或實體螢幕呈現時間。

動態背景另做原始碼 100 句 × 3 秒實測：4 threads＋實驗性複查，平均 558.28 ms、P95 1181.64 ms，79/100 句在 700 ms 內有無警告且原文匹配的完整 Qt 譯文；OCR 201 次，100 句都至少一次完全匹配。不是人工語意正確率；拒絕與未及時顯示留在分母。2 threads 輪保留其較差結果，不刪除。背景有外部重負載，兩輪不能當成乾淨 A/B，詳見 [完整測試與限制](BENCHMARK_LATENCY_A6.md)。

這個 100 句測試不是 EXE 的 100 句長測。新 EXE／wheel 只完成上列功能檢查；舊 alpha4 的長測和 API 驗收仍是歷史資料，沒有移用成 alpha6 通過證據。

## 交付與設定

- 執行檔：`dist/releases/2.0.0a6/Babelander2/Babelander2.exe`。保留完整 `_internal` 資料夾。
- 可編輯來源：`dist/Babelander2-2.0.0a6-source.zip`，不包含模型、使用者資料與測試暫存。
- wheel：`dist/babelander_desktop-2.0.0a6-py3-none-any.whl`。
- 預設 OCR threads=2、自適應複查關閉；測得的 558 ms 使用 4 threads＋自適應複查，不能當成預設設定的延遲。新設定的字幕觀察與 stable 都為 100 ms，舊設定檔的 stable 值保持。

原始碼凍結及打包對照另由 `release_snapshot.py` 檢查；發行 SHA-256：

```text
EXE   91b869973e56f10d9d85292143c511c5ce1fb2b5bf9999bb09811f698cd18fdb
wheel ffd42559c987f68c545b19156820032244f02d14c7f8bf1b0d0e66aa313993b1
```

## 未完成的驗收

真遊戲下的 700 ms 覆蓋率／frametime、暗字與混色短字幕 recall、上一句暫留期限、完整語意標註、HDR／特殊字體仍未完成。數字／時間護欄正規化錯配，以及已知口語時序／反諷錯譯仍需修正；沒有因速度優先放寬成可顯示嚴重錯譯。

[alpha4 歷史驗收](TEST_REPORT_ALPHA4.md)、[alpha5 原型紀錄](BENCHMARK_LATENCY_A5.md)。
