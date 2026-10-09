"""Publish negative experimental evidence and selected semantic review."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def run():
    replay=json.loads((ROOT/'test-results/replay-threads-full-a8/results.json').read_text(encoding='utf-8'))
    wake=json.loads((ROOT/'test-results/structural-wakeup-a8.json').read_text(encoding='utf-8'))
    prompt=json.loads((ROOT/'test-results/prompt-candidates-a8/results.json').read_text(encoding='utf-8'))
    assert replay['completed'] and replay['source_unchanged']
    assert prompt['completed'] and prompt['owned_model_stopped'] and prompt['workers_stopped'] and prompt['source_unchanged']
    assert not wake['accepted_for_runtime_trial']
    assert hashlib.sha256((ROOT/'probe_prompt_candidates.py').read_bytes()).hexdigest()==prompt['probe_source_sha256']
    for n,h in replay['application_source_sha256'].items():assert hashlib.sha256((ROOT/'babelander'/n).read_bytes()).hexdigest()==h
    selected={variant:{r['case_id']:r for r in prompt['rows'] if r['variant']==variant and r['arm']<=3}
              for variant in prompt['prompts']}
    notes={
        ('production','unless'):('conditional_loss','「不論是否」刪除了unless允許中斷的例外條件。'),
        ('production','kits'):('unsupported_addition','原文沒有傳送門，輸出新增了此物件。'),
        ('production','actors'):('actor_mismatch','apprentice與master都被翻成師傅，主體錯置。'),
        ('production','midnight'):('time_inversion','原文是午夜之後才回家，輸出否定午夜之後才回家。'),
        ('short_en','unless'):('partial_improvement','unless邏輯修正，但gold變黃色，不能宣稱條件完全保真。'),
        ('short_en','actors'):('selected_improvement','此句學徒與師傅正確區分；不代表全部語意驗收。'),
        ('short_en','midnight'):('time_inversion','時序反轉仍在。'),
        ('short_en','long'):('omitted_details','before morning變成在清晨；damaged railway bridge只剩過橋。正常EOS不保證語意完整。'),
        ('short_zh','unless'):('incomplete_command','輸出未保留interrupt動作，指令不完整。'),
        ('short_zh','midnight'):('time_inversion','時序反轉仍在。'),
    }
    reviews=[]
    for (variant,identifier),(verdict,note) in notes.items():
        row=selected[variant][identifier]
        reviews.append({'variant':variant,'case_id':identifier,'source':row['result']['source'],
                        'target':row['result']['target'],'verdict':verdict,'note':note,
                        'reviewer':'Codex selected-case analysis, not independent human gold annotation'})
    review={'scope':'Selected examples only; no full accuracy or correct-and-timely score.',
            'rows':reviews,'short_en_accepted':False,'short_zh_accepted':False}
    public=ROOT/'assets/verification'
    for name,obj in [('structural-wakeup-a8.json',wake),('prompt-candidates-a8.json',prompt),('prompt-review-a8.json',review)]:
        (public/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'test-results/prompt-candidates-a8/selected-review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# alpha8 優化迭代：有效收益與被淘汰的候選','',
        '2026-10-08。依使用者「速度 > 精準 > 資源」排序，完成公平CPU threads重播、混色觸發候選探索與短prompt比較。測試在背景，沒有桌面搶焦點、快捷鍵或雲端請求。','',
        '## 可重複的速度收益','',
        '| 同100句完整Qt更新 | 2 threads | 4 threads |','| --- | ---: | ---: |',
        '| 平均（成功當句99句） | 499.49 ms | 441.44 ms |',
        '| P95 | 816.41 ms | 677.94 ms |',
        '| 700ms內可用譯文／全部100句 | 83 | 98 |',
        '| 完整OCR至少一次 | 100 | 100 |',
        '| app CPU core-seconds | 138.11 | 237.72 |','',
        '平均快約11.6%，700ms覆蓋增加15個百分點；app CPU工作量約增72.1%，不是免費加速。五個相同20句區塊的平均均較快。模型、prompt、capture、觸發器均固定，adaptive/reuse關閉。','',
        '出貨設定仍2 threads；4可在既有設定頁手動選擇。這是固定合成畫面、CPU OCR／CUDA／Qt offscreen驗證，沒有真遊戲frametime或實際GDI擷取；不自動升預設、不重新打包發行。[完整對照](BENCHMARK_REPLAY_THREADS.md)。','',
        '另12個非空短／混色cue中，兩個白字不變追加暗字的事件，在2／4下都未進OCR。完整試跑的4組短cue還有2筆在空白後才顯示，已留在失敗與過期統計，未當成功。更快OCR不能解沒有喚醒與字幕過短的問題。','',
        '## 次要結構特徵候選：未接入正式管線','',
        '試驗以原像素灰階局部梯度、次亮度範圍、連通元件與有界座標摘要產生次要signature，只準備作喚醒訊號，不裁除OCR文字、不新增模型。','',
        '兩種混色反例各16張背景都偵測到變更，基底與變更各自signature穩定；100句白字×16張背景沒有額外signature抖動，純暗背景一致。這證明在此固定場景有潛力，沒有證明通用文字偵測。','',
        f"但移動次亮度、類字形裝飾形狀產生{wake['moving_mid_luminance_shape_variants']}種signature；單靠此hash會把背景結構移動當成變更。平均特徵成本{wake['timing_ms_mean']:.2f}ms（不含render）。候選未獲runtime驗收，也未改預設；此负例不是已量到真遊戲false wake-up率。[原始紀錄](assets/verification/structural-wakeup-a8.json)。",'',
        '下一個候選可研究有界時間一致性與位置證據，但須同時測短／移動字幕；不能把兩張一致當文字證明，或等待到短字幕消失來換漂亮數據。','',
        '## 短prompt：速度收益不足，品質不合格','',
        '18個固定難例，每個prompt兩輪，次序production→short_en→short_zh→short_zh→short_en→production，共108次Engine請求。單一暖Qwen、同temperature／max_tokens／ctx／GPU，逐請求清SQLite、同三句暖機；一個完整規則案例不經模型，所以模型請求各34筆。直接文字翻譯，不含capture／OCR／Qt。','',
        '| Prompt | Engine平均 ms（36筆，含規則／拒絕） | 模型平均 ms（34筆） | 護欄拒絕／36 |','| --- | ---: | ---: | ---: |']
    for variant,s in prompt['summary'].items():
        lines.append(f"| {variant} | {s['wall_latency']['mean_ms']:.2f} | {s['model_latency']['mean_ms']:.2f} | {s['guard_rejections']} |")
    lines += ['', '短英文prompt改善個別unless／角色主體與What?，但沒有顯著平均速度收益，而且長句遺漏關鍵橋樑與時間資訊；三組午夜not-until時序錯誤都在。短中文prompt還有額外詞庫標記／不完整指令。**兩個候選都不替換正式prompt。** 少拒絕不等於語意正確率提高。','',
        '本輪後端實際回傳token usage、cached_tokens與prompt／predicted timings。100句整管線中prompt平均約20ms，predicted約141～143ms，HTTP約184～188ms；不能期待只縮短已快取prefix就砍掉大部分翻譯成本。非串流TTFT仍未量測。','',
        '## 已核對的品質缺失','',
        '| Prompt／案例 | 譯文 | 核對結果 |','| --- | --- | --- |']
    for row in reviews:lines.append(f"| {row['variant']}／{row['case_id']} | {row['target']} | {row['note']} |")
    lines += ['', '以上是Codex對選定明確案例的語意核對，不是獨立人工標註的整組準確率。其餘未核對譯文不能自動算正確。1.7B維持baseline；後續比較候選模型或受約束翻譯方法，不能承諾只改prompt能修好嚴重時序、反諷與長句丟失。','',
        'three-hour與第一天仍有護欄正規化問題，單獨標識為guard案例；沒有藉放寬中文／數值檢查降低拒絕。','',
        '## 交付與可重跑','',
        '新增重播工具、11項計數回歸、原始結果與本報告。應用源檔、模型、正式prompt、出貨設定及alpha8發行檔維持凍結版本；沒有部署被淘汰捷徑。所有自有模型與worker都已回收，約1.91GiB暫存frame bank已刪除。','',
        '完整重播：python probe_replay_threads.py --output replay-threads-full-a8；特徵探索：python probe_structural_wakeup.py；prompt比較：python probe_prompt_candidates.py。使用本地已驗證資產與V2環境。','',
        '[實際prompt資料](assets/verification/prompt-candidates-a8.json)、[選定語意核對](assets/verification/prompt-review-a8.json)、[三回合規格辯論](DEBATE_ALPHA8.md)。']
    (ROOT/'OPTIMIZATION_EXPERIMENTS_A8.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'report':'OPTIMIZATION_EXPERIMENTS_A8.md','application_unchanged':True,'candidate_prompts_accepted':False,'structural_signature_accepted':False}))


if __name__=='__main__':run()
