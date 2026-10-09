# alpha7 驗證紀錄

日期：2026-10-08。修正確認通知競爭及同畫面 epoch 的 OCR 句尾句點重翻；**700 ms 尚未全面達標**。

## 本版檢查

| 範圍 | 結果 | 證據 |
| --- | --- | --- |
| 核心邏輯與排程 | 57 項通過 | [core](assets/verification/unit-tests-a7.json) |
| 管線／Qt／取消／有界交接 | 39 項通過，含四項新增回歸 | [pipeline](assets/verification/pipeline-a7.json) |
| 資產下載合約 | 12 項通過，合成 transport | [assets](assets/verification/asset-unit-a7.json) |
| 新 EXE 真 Qt、CPU OCR、本機模型 | 17 項通過 | [EXE](assets/verification/bundle-selftest-a7.json) |
| 隔離 wheel 真實功能 | 17 項通過，31 個 app 源檔／QSS 相符 | [wheel](assets/verification/wheel-a7.json) |

新增回歸測試確認：通知先於開始等待仍立即返回；無效通知不提前結束等待；數值、否定、問號／驚嘆號／省略號不合併；同 epoch 句尾英文句點抖動只送一次翻譯。原始 OCR 仍供核對及首次翻譯，不改寫 cache key 或術語。

全部在 offscreen 下執行，沒有測試視窗或快捷鍵覆蓋桌面。單元與資產測試不發真實 API；EXE／wheel 功能檢查使用本機模型。沒有測真實 GDI、遊戲 FPS 或實體螢幕呈現時間。

## 延遲證據的版本

本版尚未重跑 100 句動態背景長測，不能將 alpha6 的平均 558.28 ms、P95 1181.64 ms 或 79/100 句於 700 ms 內就緒，當成 alpha7 的結果。也沒有宣稱每句固定省下 50 ms。

保存的 [alpha6 結果](BENCHMARK_LATENCY_A6.md) 包含兩輪與全部慢句。舊第 47 句的 1881.73 ms 嚴格原文匹配含 OCR 句點歸屬差異：第一筆僅缺英文句尾句點的完整譯文實際於 513.92 ms 更新 Qt；舊報告保留不改。詳見 [慢句分析與下一步](LATENCY_NEXT_STEPS.md)。

## 交付

- 執行檔：`dist/releases/2.0.0a7/Babelander2/Babelander2.exe`，保留完整 `_internal` 資料夾。
- 可編輯來源：`dist/Babelander2-2.0.0a7-source.zip`。
- wheel：`dist/babelander_desktop-2.0.0a7-py3-none-any.whl`。
- [源檔凍結](assets/verification/frozen-source-a7.json)；打包模組／源檔對照由 `release_snapshot.py` 檢查，校驗資料保存於 `dist/Babelander2-2.0.0a7-sha256.json`。

預設 OCR threads=2、自適應複查關閉；沒有修改使用者設定或更換模型。alpha6 發行物與證據仍保留。

## 仍待改善

長句的 OCR 與翻譯計算時間、暗字／混色短字幕 recall、真遊戲 frametime、上一句譯文保留期限、完整語意品質，以及數字／時間護欄正規化、已知反諷／時序錯譯。優先驗證重用字幕行位置與固定短 prompt，依實測決定是否啟用。

[alpha6 歷史驗收](TEST_REPORT_ALPHA6.md)。
