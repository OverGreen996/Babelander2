# alpha8：100 句動態背景、字幕行重用對照

**結論：目前不建議開啟。** 完整反應時間沒有證明收益，開啟輪平均與 P95 更差；另有實際高信心混色截字。功能預設保持關閉。即使早期 OCR-only 平均下降，也不能當成完整翻譯變快。

2026-10-08。兩輪各 100 句，每句 3 秒；同一程序、相同資料與背景 seed，先 control、再開啟行重用。不是隨機交錯的乾淨硬體 A/B，背景系統負載可變；不能只把差值當成改動的因果效果。

真實 PP-OCRv6 Small／ONNX CPU（4 threads）、Qwen3 1.7B Q4_K_M／CUDA、Qt offscreen。兩輪同樣開啟實驗性自適應複查，stable=100 ms、dialog scan=100 ms。模型先暖機，每輪清空 SQLite cache，新 session 不沿用行位置提示。

1450×250、Arial 30 pt、白字黑邊；背景目標 20 FPS 持續變動、無文字背板。合成 capture 取代 GDI。時間從測試文字出現到完整 Qt 更新，包含取樣與穩定確認；不是單看模型時間，也不是螢幕像素呈現時間。

## 實際結果

| 指標 | 行重用關閉 | 行重用開啟 |
| --- | --- | --- |
| 700 ms 內完整 Qt 譯文／100（嚴格原文匹配） | 80 | 59 |
| 700 ms 內完整 Qt 譯文／100（句尾句點容差） | 80 | 60 |
| 完全匹配 OCR 至少看到一次／100 | 100 | 100 |
| 3 秒內可用完整 Qt 譯文／100 | 99 | 96 |
| OCR 次數 | 200 | 196 |
| 模型請求 | 100 | 99 |
| cache hit | 0 | 0 |
| 護欄拒絕次數 | 1 | 1 |
| 字幕切換後才顯示的結果 | 0 | 2 |
| OCR 工作總耗時 ms | 50267.02 | 66036.33 |
| CPU seconds，包含 fixture | 352.765 | 327.563 |
| 完整 Qt 譯文平均 ms | 555.52 | 742.48 |
| P50 ms | 468.34 | 476.59 |
| P95 ms | 1139.97 | 2097.56 |
| Max ms | 1260.73 | 3197.16 |
| 平均 ms（句尾句點容差） | 555.52 | 740.21 |
| OCR 平均 ms | 251.34 | 336.92 |
| OCR P95 ms | 596.7 | 1047.78 |

可用譯文意指有完整目標文字、沒有護欄警告且原文歸屬匹配；**不是人工語意正確率**。平均／P95 的分母只包含該規則下顯示成功的句子，700 ms 覆蓋率固定以全部 100 句為分母。護欄拒絕、沒有顯示與過慢仍保留。

句尾句點容差只忽略英文單字後最後一個 ASCII `.`；不忽略數字／小數、問號、驚嘆號、省略號或文字內容。嚴格指標另列，沒有改寫 alpha6 歷史紀錄。

## 執行路徑

開啟輪 OCR 路徑：`{'full': 119, 'line_reuse': 77}`。完整偵測原因：`{'shape_or_initial': 8, 'episode_recheck': 94, 'new_or_moved_line': 10, 'missing_or_small_line': 7}`。

同組第 1–40 句的 OCR 平均在開啟輪較低，但第 41–100 句反而上升；模型、renderer 與擷取也在後段變慢。整機 CPU 曾有 98.34% 的採樣值。這支持資源競爭可能是因素之一，但不能證明都是外部程式造成，或排除本功能的額外成本；沒有因此刪除較差的後段。

先完整偵測取得可信的橫排行位置；新畫面依當前白字像素更新文字左右邊界，驗證行數與位置後才略過偵測。不是沿用舊文字寬度。相同 glyph episode 的安全複查做完整偵測，讓下句能利用近期行提示。提示最多重用三次／兩秒；變形、移位、新行、彩字、低信心等回到完整 OCR。

每次辨識包含 fallback 的整體耗時；不是只計算成功快速路徑。擷取、OCR、翻譯三個階段及過期 session／epoch 阻擋仍在。

## 開啟輪的慢句與失敗

| 句號 | 完整 Qt 延遲 ms（嚴格） | 原文 |
| --- | --- | --- |
| 50 | 961.24 | Carry the sealed container upright throughout the journey across the dunes. |
| 51 | 1687.69 | Check the lower decks for passengers who missed the evacuation announcement. |
| 52 | 2494.09 | Leave a wooden marker wherever the underground trail divides into two paths. |
| 53 | 1071.91 | Draw the creature toward the shallow pool beside the ruined amphitheater. |
| 55 | 989.26 | Deliver the replacement lens to the lookout stationed above the canyon. |
| 56 | 745.22 | Use the maintenance hatch to reach the control room beneath the arena. |
| 57 | 728.05 | Help the apprentice arrange the colored stones around the damaged sundial. |
| 59 | 860.79 | Collect the fallen branches and reinforce the shelter before the hail arrives. |
| 64 | 897.41 | The drone scans a radius of 14 meters for 8 seconds. |
| 65 | 1010.42 | Deliver 5 medical kits before the countdown reaches 01:30. |
| 66 | 3197.16 | Do not cross the painted line while the examination lamp is flashing. |
| 67 | 914.45 | Your critical chance increases by 12% while your health remains above 75%. |
| 68 | 2749.72 | The special ammunition pierces 2 targets but deals 30% less damage afterward. |
| 69 | 1709.26 | You cannot equip this relic until your reputation reaches level 9. |
| 70 | 1066.5 | After collecting 11 fragments, return to the excavation supervisor. |
| 71 | 781.33 | If the scanner detects movement, remain still for at least 4 seconds. |
| 72 | 1389.51 | The protective field lasts 16 seconds unless its generator is destroyed. |
| 73 | 1004.2 | Do not spend the last repair charge before checking the rear engine. |
| 74 | 1519.04 | Each rescued worker adds 25 seconds to the remaining evacuation time. |
| 75 | 1054.44 | This recipe requires 3 mushrooms, 2 bottles of water, and 1 copper pot. |
| 80 | 未取得 | Do not interrupt the ritual unless the outer circle changes from gold to violet. |
| 81 | 1258.27 | The curator insists that the damaged painting depicts a real location, although the coastline in the background resembles nothing on our modern maps. |
| 82 | 890.91 | We could follow the smugglers through the caves, but the rising tide would trap anyone who failed to reach the second exit before nightfall. |
| 83 | 1397.23 | She accepted the assignment because it offered a chance to find her missing teacher, rather than because she believed the promised reward would ever be paid. |
| 84 | 1118.6 | The caretaker asked us to repair the broken fountain before searching the mansion, explaining that its running water kept the restless spirits calm. |
| 85 | 1033.66 | Although the new armor protected him from the explosion, its weight prevented him from escaping the flooded compartment without help from the other divers. |
| 86 | 837.54 | I left the package beside the red doorway as instructed, yet the woman who collected it claimed she had expected us to arrive several days earlier. |
| 87 | 746.74 | If you decide to reopen the laboratory, make sure the ventilation system is working before disturbing any of the dust covering the experimental equipment. |
| 88 | 1117.88 | The envoy brought a proposal that seemed generous at first, but accepting its final condition would leave the border villages entirely dependent on foreign supplies. |
| 89 | 1060.69 | Our scout believes the tracks belong to a wounded animal, though their perfectly even spacing suggests that someone may be trying to lure us into an ambush. |
| 90 | 1127.99 | Before activating the beacon, gather everyone inside the reinforced shelter and check that the emergency shutters can still close over the damaged western windows. |
| 91 | 1220.56 | The singer recognized the stolen instrument by a tiny scratch near its handle, a detail she had described to the investigators before they found the suspect. |
| 92 | 未取得 | You are free to take the mountain route, provided that you bring enough climbing equipment for the companions who have never crossed an ice field before. |
| 93 | 1172.37 | The captain refused to abandon the cargo until we showed him that the cracked containers were leaking a substance capable of dissolving the ships wooden hull. |
| 94 | 902.53 | We assumed the apprentice had misunderstood the instructions, until the master admitted that he had deliberately given her an incomplete version of the spell. |
| 95 | 1091.82 | If the creatures remain quiet after the music stops, lower your weapons slowly and allow the youngest one to approach the food placed near the entrance. |
| 96 | 1325.01 | The abandoned tram still runs between the two settlements, but nobody knows who repairs its engine or why it always stops at the empty hillside station. |
| 97 | 1084.8 | She would have recognized the impostor sooner if the council had allowed her to examine the signature on the treaty instead of keeping it locked away. |
| 98 | 2530.35 | The device can locate buried metal objects, but it cannot distinguish valuable artifacts from ordinary scrap without a separate reading from the portable analyzer. |
| 99 | 2097.56 | After the storm passes, send a messenger to each neighboring village so that we can learn which roads are safe enough for the supply convoys to use. |
| 100 | 未取得 | We have enough medicine to stabilize the injured passengers tonight, but finding a doctor before morning will require someone to cross the damaged railway bridge. |

## 使用範圍

設定 → OCR 執行緒可選 1–4；「白字字幕加速（試驗）」可開關，儲存會停止既有監測，重新開始才使用新設定。**預設仍是 2 threads、行重用關閉、自適應複查關閉**；本表不能當成預設設定的速度。

全暗字幕與黃色字幕會回到完整 OCR，但暗字混在白字旁邊／新暗字行仍可能被快速路徑截掉，因此沒有自動開啟。固定白字場景的測試不能當成通用遊戲 recall 驗收。沒有新增模型或第二套 OCR session，提示只保存有界座標／hash／時間，不保存原文或影像歷史；沒有測本功能的獨立 native RAM／VRAM 上限。

額外 8 個真 OCR 圖片案例中，白字、較寬白字、新白字行、移位、黃字、全暗字與完整 OCR 的結果相符；混色新暗字行及同一行暗字後綴則都只輸出 `Open the gate`，漏掉 `before midnight`，信心仍約 0.998。**這是實際失敗，不是 8 項通過。** 見 [混色發現紀錄](assets/verification/layout-adversarial-a8.json)。

系統 CPU 每約 15 秒一筆、GPU 使用率／總顯存為瞬時整機值，存在原始資料；沒有把 GPU 總使用率當成本程式用量。CPU seconds 含背景 renderer，不是純 app pipeline。未測真遊戲 FPS／frametime、HDR、特殊字體與語意品質。

初版排程試跑在完成前中止，保存於 `test-results/moving-background-a8-initial-interrupted`，不算通過、不混入本表。早期 OCR-only 試作保存於 `test-results/ocr-layout-a8`，也不作為本版完整翻譯延遲。

[原始兩輪資料](assets/verification/moving-background-a8-line-ab.json)、[源檔凍結](assets/verification/frozen-source-a8.json)、[本版功能驗證](TEST_REPORT.md)。
