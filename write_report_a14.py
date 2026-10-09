"""Write release notes from actual complete-pipeline and numeric measurements."""
import json,statistics
from pathlib import Path
ROOT=Path(__file__).parent
r=json.loads((ROOT/'test-results/equipment-structures-a14-final/report.json').read_text(encoding='utf8'))
n=json.loads((ROOT/'test-results/equipment-numeric-a14.json').read_text(encoding='utf8'))
cards=[v for v in r['runs'] if v['id']=='battle-card-0']
untouched=[v['numeric_recovery_ms'] for v in r['runs'] if not v.get('numeric_retry')]
table='\n'.join(f"| {s['pass']+1} | {s['usable']}/{s['runs']} | {s['mean_result_ms']} ms | {s['p95_result_ms']} ms | {s['usable_within_700ms']}/{s['runs']} |" for s in r['summary'])
text=f'''# alpha14：裝備／卡牌的數字局部補辨識

2026-10-08。本輪保留 alpha12 的物品外觀與 alpha13 的字幕管線，只處理單次裝備卡的數字補辨識。

## 功能範圍

整張 OCR 完成後，在高信心 Health、Attack、Defense 等有限英文屬性標籤右側，檢查符合原字色與字高的未辨識字形。附近已有低信心的 1～4 位純數字時也可局部重試。最多掃描 16 個屬性區、補查六個候選；每個局部原尺寸不超過 16,384 像素，沿用同一個 CPU OCR 引擎，送原尺寸與 2 倍尺寸兩次批次辨識。只有兩次相同、都是 1～4 位 ASCII 數字且信心至少 0.98 才加入／取代數字行。

這是同模型的尺寸一致性篩選，不是獨立模型交叉驗證；信心不等於正確率。候選只包含幾何位置，不包含預期數值，不把 O 猜成 0。排除已有 OCR 框、實心菱形與部分實心圖形；仍不能保證任意遊戲圖示都不會被 OCR 誤讀。

未確認的漏字候選保留原圖，中文排版不能延伸進入該區。不可靠的既有文字仍遵守原本整卡護欄；不靠猜字讓失敗的卡片顯示。Stop 在兩次辨識間檢查取消，不會把取消工作更新到 UI。幾何摘要／裁切圖只存在當次工作，不新增影像歷史、OCR engine、GPU 模型或使用者設定。

字幕、聊天、一般框選不呼叫這個補辨識功能。單次裝備仍只擷取一次、完整 OCR 一次，局部補查最多兩個批次；不再宣稱所有裝備卡總共只呼叫一次辨識器。

## 完整 OCR／CUDA／Qt 回歸

同一組 10 種資訊結構、20 張 fixture 各跑兩次，共 40 次。背景 Qt offscreen，無桌面擷取、可見視窗或快捷鍵。fixture 畫素雜湊與 alpha13 回歸相同，沒有把真值文字／數值／座標送進正式 Controller 或 OCR。全程 40/40 可繪製、原文與數值檢查通過、原位／原字色／圖示／獨立純數字原畫素保留，沒有持續裝備監測。

| 輪次 | 完整檢查通過 | 平均完整 Qt 更新 | P95 | 700 ms 內 |
| --- | ---: | ---: | ---: | ---: |
{table}

引擎暖機後，首輪清一次翻譯快取，共用欄位仍可能命中；第二輪保留快取。首輪與重跑不能當成模型加速 A/B，數值欄位正確也不代表人工語意完全正確。這是裝備卡成績，不是字幕成績；不將 alpha13 的平均 416 ms 當成 a14 新測量，也沒有真遊戲 FPS／frametime 證據。

原本漏掉生命值 7 的 battle-card-0，兩輪都真正從局部畫素補回 7，沒有注入預知數值。補查分別 {cards[0]['numeric_recovery_ms']:.2f}／{cards[1]['numeric_recovery_ms']:.2f} ms；完整卡片分別 {cards[0]['full_qt_latency_ms']}／{cards[1]['full_qt_latency_ms']} ms。其餘 {len(untouched)} 次沒有新增辨識器請求，候選篩選平均 {statistics.mean(untouched):.2f} ms。字幕分支的程式碼與取消／過期結果回歸一併驗證，但未做 a14 100 句速度重測。

![同一張卡牌的原圖與真實翻譯覆蓋](assets/equipment-recovery-a14/battle-card-0-comparison.png)

## 不同數字與失敗保護

另生成 0、1、2、3、4、5、6、7、8、9、10、18、42、99 共 14 種生命值，每種測一般完整 OCR 和刻意移除數字 OCR 行的情境，共 28 次。刻意移除只用來驗證補辨識，不能當成一般 OCR 偵測率；評分座標只用於判定結果與移除測試行，不送進補辨識。

- {n['exact_recovery_cases']}/28 最終取得正確數字；包含第一次就辨識成功的數字，不能全部算「補回」。
- {n['safe_fallback_cases']}/28 無法確認 0，未加入數字，保留原畫素並限制標籤排版。
- {n['wrong_value_cases']}/28 錯值加入；28/28 原數字畫素保留。
- 圓環、空心菱形、實心菱形、十字與 A 共五個真 OCR 反例，沒有補成数字。這組反例刻意提供固定的第一階段 Health 標籤幾何，測的是補查防誤判，不是完整圖示 OCR 正確率。

## 驗收與限制

230 項單元／管線／Qt／回放計數檢查通過，包含取消、字幕以外分支、候選上限、兩次不一致、低信心／NaN／字母拒絕，以及未確認區域的原畫素與排版保護。EXE 與隔離 wheel 各執行真 OCR／本機 CUDA／Qt 自測；打包模組與本輪凍結原始碼一致，舊 a13 保留。

目前補查限定右側正整數、有限英文屬性標籤與近似原字色。未知標籤、不同色數字、左側數字、負數／小數／百分比、極小字或複雜圖示仍可能漏讀；O／0 無法確認時仍需看原图或手動核對。這些限制不以降低門檻或換更重模型掩蓋。

[完整裝備回歸 JSON](assets/verification/equipment-regression-a14.json) · [數字與圖示反例 JSON](assets/verification/equipment-numeric-a14.json) · [封存核對](assets/verification/release-a14.json)
'''
text=text.replace('装備','裝備').replace('数字','數字').replace('原图','原圖')
(ROOT/'TEST_REPORT_ALPHA14.md').write_text(text,encoding='utf8')
print('wrote TEST_REPORT_ALPHA14.md')
