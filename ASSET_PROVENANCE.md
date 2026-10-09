# 展示素材來源

- `docs/assets/hero.svg`：為 Babelander 2 撰寫的向量插畫，包含虛構盾牌及英中對照。以 `docs/render_readme_assets.py` 繪製並輸出 PNG；封面是品牌示意，不是 OCR 或效能測試。
- `docs/assets/workspace.png`：目前 alpha23 的真實 Qt 工作台，使用暫存資料夾、預填示例文字與 offscreen 渲染。未擷取使用者桌面、未使用私人訊息、未啟動模型。
- `assets/equipment-structures-a12/`：自行生成多種裝備、卡牌、寶石與模組結構，經本機 OCR／翻譯／Qt 繪製的歷史測試。生成器為 `equipment_game_fixtures.py`；原始結果未修飾。
- `assets/quest-structures-a18/`：自行生成任務追蹤、終端、日誌等版型，經實際引擎處理。生成器為 `quest_fixtures.py`；展示不表示已在商業遊戲測試。
- 其餘 `assets/` 圖片與資料主要為開發中生成的測試素材、輸出及驗證證據。版本與結果範圍應以對應 `TEST_REPORT_ALPHA*.md` 為準。

不使用上述虛構素材宣稱與任何遊戲工作室合作，也不以展示圖片代替翻譯品質或實機相容性驗收。
