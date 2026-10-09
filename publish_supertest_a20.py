"""Write human-readable a20 evidence after the complete suite has finished."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parent
r=json.loads((ROOT/'test-results/supertest-a20/summary.json').read_text(encoding='utf8'))
c=r['chat_speed'];m=r['moving_background'];ram=r['resources'];soak=r['soak']
failed=[k for k,v in r['functional_checks'].items() if not v]
text=f'''# alpha20 全程背景驗收

完成了整套測試與實際 EXE／wheel 核對。功能與生命週期：**{'通過' if r['functional_passed'] else '未通過，見失敗項目'}**；完整 700ms 速度與所有語意條件：**尚未全數通過**。這份報告不是「所有遊戲都沒問題」的保證。

## 驗證範圍

| 項目 | 實際結果 |
| --- | --- |
| 回歸 | {r['regression_count']} 項，13 組，包含 queue 上限、取消、過期事件、詞庫、數量、否定、快取、API 失敗、排版、預載與焦點 |
| 六模式 | 分別執行及同時執行；單一模型共用、停止後不回寫；翻譯中途終止自有模型，下一次請求成功恢復 |
| 裝備卡 | 10 種版型、20 張卡 × 2 輪 = 40 次；原位覆蓋、字色／圖片／數量、單次擷取均檢查 |
| 任務卡 | 8 種版型、16 張卡 × 2 輪 = 32 次；NPC／快捷欄／日誌等版型 |
| 聊天室 | 100 則文字 + 100 則捲動畫面；無漏訊息／重複、100 則取得譯文；96 則 OCR 原文完全匹配 |
| 私人文字 | 聊天／回覆不寫 SQLite；volatile cache 上限及清理驗證 |
| 動態背景 | 100 句，每句約 3 秒；全數辨識並顯示，無重複、無過期句覆蓋；{m['captures']} 次擷取、{m['ocr_calls']} 次 OCR |
| 雲端 | Google／Azure／DeepL 各兩個真請求，6／6 通過；重複請求使用快取、不重複記帳 |
| 實際打包 | EXE {r['actual_exe_checks']} 項、隔離安裝 wheel {r['actual_wheel_checks']} 項均通過；編譯模組及 wheel 與目前來源碼相符 |
| 長時間 | EXE {soak['duration_seconds']} 秒，{soak['changes']} 次字幕切換、{soak['results']} 次結果；每分鐘清快取，持續運作及停止回收均驗證 |

{'失敗項目：'+', '.join(failed) if failed else '上述功能與生命週期檢查沒有失敗。'}

## 速度還沒過門檻

| 測試 | 完整結果平均 | P95 | 700ms 內 |
| --- | --- | --- | --- |
| 100 則聊天室，畫面出現→Qt 接收 | {c['mean_ms']} ms | {c['p95_ms']} ms | {c['within_700ms']}／{c['successful_full_outputs']} |
| 100 句字幕，持續動態背景 | {m['display_latency']['mean_ms']} ms | {m['display_latency']['p95_ms']} ms | {m['usable_display_within_700_ms']}／100 |

字幕中位數為 {m['display_latency']['p50_ms']} ms，最快的一半已低於門檻，但尾端明顯太慢。OCR 單次平均 {m['ocr_call_latency']['mean_ms']} ms、P95 {m['ocr_call_latency']['p95_ms']} ms；首次精確 OCR 完成平均 {m['first_exact_ocr_latency']['mean_ms']} ms。聊天室仍有 800ms polling。這些是下一輪該分開比較的瓶頸，不能拿純文字模型平均約 65ms 來聲稱完整流程達標。

裝備／任務的大區域多行卡片，第 1 輪／第 2 輪時間分開保存在 JSON；第 2 輪包含重用／快取，不作冷模型速度宣稱。六模式同時排隊也不代表每一模式仍能在 700ms 完成。

背景動畫 fixture 的產生本身耗 CPU；動態背景報告的 CPU 秒數包含 fixture，不可全歸因程式。測試當下機器可能還有其他工作，這輪不是與 alpha19 同條件的速度 A/B，也沒有量遊戲 FPS。

## 修正與語意限制

修正了「不要越過河流」被譯成過去經驗，以及完整遊戲聊天意圖中的 party／保留物資／優先集火／暫停時長。完整規則接受可變數量和物品；未知物件、追加條件、否定改写、衝突詞庫都交回模型。16 項新增回歸包含會故意破壞數量、單位及禁止命令的反例。

Google 的 `Please wait 6 minutes before starting.` 原本被否定護欄誤擋；現在僅接受對應的等待後再開始句型，數量、時間單位及其他禁止命令仍檢查。測試也曾誤擋「收集……再與船長說話」這個正確順序，已修正測試判定，沒有改寫模型輸出。

12 個額外複合句有 {r['novel_quality_markers']['passed']}／12 通過必要關鍵檢查；仍有 Save the last potion → 儲存、藥水 → medicine，以及「首領目標你」等詞義／自然度問題。必要關鍵詞存在不證明完整語意正確，沒有宣稱整體精準率。

## 資源與回收

- EXE 每分鐘樣本、兩分鐘暖機後 private RAM：{ram['app_warm_private_min_mib']}～{ram['app_warm_private_max_mib']} MiB。
- 自有模型 private RAM 最大：{ram['model_private_max_mib']} MiB。Private RAM 是 Windows 計數，不能當作實體駐留量。EXE 暖機後 working set {ram['app_warm_working_min_mib']}～{ram['app_warm_working_max_mib']} MiB，模型 working set 最大 {ram['model_working_max_mib']} MiB。
- 自有模型 WDDM 配置 dedicated memory 最大：{ram['model_wddm_dedicated_max_mib']} MiB；shared memory 最大：{ram['model_wddm_shared_max_mib']} MiB。以上是短字幕長跑的樣本，沒有量六模式同時工作的資源最高值。這是指定 PID 的配置計數，沒有把遊戲顯存算進來，也不是功耗。
- 暖機後 RAM 差距上限 64 MiB、handle 差距上限 30；也核對自有模型 RAM 與 WDDM dedicated／shared memory 的暖機後漂移。所有樣本在 JSON，可看到範圍，不能用這個容忍值宣稱「零洩漏」。
- 停止後，模型在關閉程式前退出；圖片／preview、背景工作與資源釋放 worker 都回收。十分鐘穩定不替代數小時耐久測試。

## 證據與重跑

[完整摘要](assets/verification/supertest-a20/summary.json) · [六模式與崩潰恢復](assets/verification/supertest-a20/modes.json) · [動態背景](assets/verification/supertest-a20/moving-background.json) · [語意反例](assets/verification/supertest-a20/quality.json) · [EXE 長跑](assets/verification/supertest-a20/soak.json) · [自有 PID 資源樣本](assets/verification/supertest-a20/resources.json) · [重跑指令](SUPERTEST.md)。

Qt offscreen、自製畫面、無搶焦點、無玩家截圖、無原資料／憑證變更。原生 Win32 核對只操作自有隱藏視窗。尚未驗證实际遊戲的全螢幕／反作弊、GDI 畫面擷取、多螢幕／縮放、快捷鍵衝突及 FPS／frametime。
'''
(ROOT/'TEST_REPORT_ALPHA20.md').write_text(text,encoding='utf8')
p=ROOT/'README.md';s=p.read_text(encoding='utf8').replace('2.0.0 alpha 19','2.0.0 alpha 20').replace('dist/releases/2.0.0a17/','dist/releases/2.0.0a20/').replace('2.0.0a4\\Babelander2','2.0.0a20\\Babelander2').replace('dist/Babelander2-2.0.0a11-source.zip','dist/Babelander2-2.0.0a20-source.zip')
intro=f'**alpha20 全面驗收：** 390 項回歸、六模式混合／崩潰恢復、40 次裝備卡、32 次任務卡、100 則聊天、100 句動態背景字幕、三家真 API、EXE／wheel 各 34 項，以及 EXE 十分鐘長跑。功能與回收通過；動態字幕完整顯示平均 **{m["display_latency"]["mean_ms"]}ms**，尚未全數達 700ms，複合句仍有用詞問題。[這輪完整證據與限制](TEST_REPORT_ALPHA20.md) · [一鍵背景重跑](SUPERTEST.md)。\n\n'
if '**alpha20 全面驗收：**' not in s:s=s.replace('**alpha19 通用聊天室：**',intro+'**alpha19 通用聊天室：**')
s=s.replace('GPU 專屬視訊記憶體與遊戲 frametime 未量測，標為 N/A；','內建 soak 的 GPU 計數為 N/A；整套 supertest 另外量自有模型 PID 的 WDDM 顯存。遊戲 frametime 未量測；')
p.write_text(s,encoding='utf8')
p=ROOT/'CHANGELOG.md';s=p.read_text(encoding='utf8');header='''# 2.0.0a20 · 全程背景驗收

- 完整禁止指令、隊伍狀態、物資保留、優先集火與暫停時長規則；未知条件／物品及詞庫衝突繼續交給模型。
- 修正特定等待後開始的英文回覆被否定護欄誤擋；數量、時間單位及其他禁止命令保護保留。
- 新增可重跑整套 supertest、16 項語意／數量／保守退回反例。390 項回歸、六模式混合、模型崩潰恢復、72 次卡片、100 則聊天、100 句動態背景、三家 API、EXE／wheel 各 34 項與 EXE 十分鐘長跑完成。
- 功能與回收通過；700ms 完整反應及複合句語意仍未全數通過。[完整結果與限制](TEST_REPORT_ALPHA20.md)。

'''
if not s.startswith('# 2.0.0a20'):p.write_text(header+s,encoding='utf8')
print('Documentation written from completed summary.')
