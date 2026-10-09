"""Publish evidence for the paired animated-background monitor benchmark."""
from pathlib import Path
import hashlib
import json
import math
import re
import shutil
import statistics

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'test-results/moving-background-100'
data = json.loads((SOURCE / 'results.json').read_text(encoding='utf-8'))
assert data['completed'] and data['owned_model_stopped'] and data['workers_stopped'] and data['source_unchanged']
assert all(hashlib.sha256((ROOT/'babelander'/name).read_bytes()).hexdigest() == digest
           for name, digest in data['application_source_sha256'].items())
assert all(p['monitor_drained'] and not p['errors'] and p['summary']['sentences_presented'] == 100
           for p in data['phases'].values())
PUBLIC = ROOT/'assets/verification'
PUBLIC.mkdir(exist_ok=True, parents=True)
shutil.copy2(SOURCE/'results.json', PUBLIC/'moving-background-100-a4.json')
shutil.copy2(SOURCE/'corpus.json', PUBLIC/'moving-background-100-corpus-a4.json')
for path in SOURCE.glob('*.png'):
    shutil.copy2(path, ROOT/'assets'/('noise-'+path.name))
static = data['phases']['static_noise']
moving = data['phases']['moving_noise']
a, b = static['summary'], moving['summary']
def stats(values):
    if not values:return None
    values=sorted(values)
    return {'n':len(values),'mean_ms':round(statistics.mean(values),2),
            'p95_ms':round(values[math.ceil(len(values)*.95)-1],2),'max_ms':round(values[-1],2)}
def lexical(text):return re.sub(r'[^a-z0-9%]+',' ',text.casefold()).strip()
def derive(phase):
    onsets={r['case_id']:r['at'] for r in phase['presentations']}
    results={r['event_id']:r for r in phase['results'] if r['translations']}
    displays=[]
    for ui in phase['ui']:
        result=results.get(ui['event_id'])
        if not result or not ui['source']:continue
        # A UI notice's event must match both the recorded translation source
        # and the OCR observation nearest that event's initial capture time.
        source=re.sub(r'\s+',' ',result['translations'][0]['source']).strip()
        if source!=ui['source']:continue
        observations=[o for o in phase['ocr'] if o['text']==source]
        if not observations:continue
        observation=min(observations,key=lambda o:abs(o['at']-result['observed_start']))
        case=observation['case_id']
        displays.append({**ui,'fixture_case_id':case,'fixture_latency_ms':(ui['at']-onsets[case])*1000,
                         'observed_pipeline_ms':(ui['at']-result['observed_start'])*1000,
                         'lexical_ocr_exact':lexical(source)==lexical(data['corpus'][case-1]['text'])})
    ready=[r for r in displays if r['target'] and not r['warning']]
    first={}
    for r in ready:first.setdefault(r['fixture_case_id'],r)
    return {'fixture_linked_deliveries':displays,'displayed_cases':len(first),
            'displayed_within_3_seconds':sum(r['fixture_latency_ms']<3000 for r in first.values()),
            'all_ready_latency':stats([r['fixture_latency_ms'] for r in first.values()]),
            'observed_pipeline':stats([r['observed_pipeline_ms'] for r in ready]),
            'lexical_exact_seen':sum(any(o['case_id']==case['id'] and lexical(o['text'])==lexical(case['text'])
                                        for o in phase['ocr']) for case in data['corpus']),
            'late_displays':sum(r['fixture_case_id']!=r['visible_case_id'] for r in ready),
            'extra_ready_displays':len(ready)-len(first),
            'observation_alignment':'UI event ID + translation source + matching OCR nearest event observed_start'}
derived={name:derive(phase) for name,phase in data['phases'].items()}
(PUBLIC/'moving-background-100-derived-a4.json').write_text(json.dumps(derived,ensure_ascii=False,indent=2),encoding='utf-8')
da,db=derived['static_noise'],derived['moving_noise']
def metric(s, key, field='mean_ms'):
    return f"{s[key][field]:,.2f}" if s[key] else 'N/A'
def simple(key, suffix=''):
    return f"| {key} | {a[key]}{suffix} | {b[key]}{suffix} |"
def percentile(values):
    if not values: return 'N/A'
    values=sorted(values)
    return f"{statistics.mean(values):.2f} / {values[math.ceil(len(values)*.95)-1]:.2f}"
def stages(phase, key):
    return percentile([r['stages'][key] for r in phase['results'] if key in r['stages']])
def case_list(phase, key):
    return ', '.join(str(o['case_id']) for o in phase['outcomes'] if not o[key]) or '無'
def warnings(phase):
    rows=derived[phase['name']]['fixture_linked_deliveries']
    return '\n'.join(f"| {phase['name']} | {r['fixture_case_id']} | {r['warning']} |"
                     for r in rows if r['warning']) or f"| {phase['name']} | — | 無 |"
def working(phase, field):
    values=[r[field] for r in phase['resources']]
    return f'{min(values):.2f}–{max(values):.2f}'
ratio = b['ocr_calls']/a['ocr_calls'] if a['ocr_calls'] else 0
motion = []
for phase in (static, moving):
    by_case={}
    for capture in phase['captures']:
        by_case.setdefault(capture['case_id'],set()).add(capture['frame_sha256'])
    motion.append(sum(len(hashes)>1 for hashes in by_case.values()))
text = f'''# 動態背景測試：另一組全新 100 句 · {data['version']}

日期：2026-10-08。每句維持 **3 秒**；相同 100 句分別跑靜態雜訊與動態雜訊，各 300 秒，共 10 分鐘。這 100 句與前次英文測試完全不重複，包含短句、劇情、指令、數值條件、長句各 20 句。

使用目前應用程式的真實監測排程、RapidOCR CPU、Qwen3 1.7B Q4_K_M／CUDA 與 Qt 接收端；設定仍為 **scan 800 ms／stable 300 ms／fast／thinking off**。OCR 與模型先暖機，兩個階段各清一次測試快取；未修改產品程式碼、未呼叫雲端、未碰使用者設定。使用 Qt offscreen，沒有桌面測試視窗。

## 配對結果

「譯文就緒」指原文完全匹配該句、Qt target 非空且無護欄警告；不代表人工確認語意正確。時間從 fixture 實際換句開始，包含等待下一次掃描、OCR、穩定等待、翻譯、Qt 接收。

| 項目 | 靜態雜訊 | 動態雜訊 |
| --- | ---: | ---: |
| 顯示句數 | {a['sentences_presented']} | {b['sentences_presented']} |
| 無警告的譯文輸出（含 OCR 認錯） | {da['displayed_cases']}/100 | {db['displayed_cases']}/100 |
| 全部無警告輸出的首筆平均延遲 | {metric(da,'all_ready_latency')} ms | {metric(db,'all_ready_latency')} ms |
| 全部無警告輸出的首筆 P95 延遲 | {metric(da,'all_ready_latency','p95_ms')} ms | {metric(db,'all_ready_latency','p95_ms')} ms |
| 至少一次完全正確 OCR | {a['exact_ocr_seen']}/100 | {b['exact_ocr_seen']}/100 |
| 忽略標點與大小寫後至少一次字詞完全一致 | {da['lexical_exact_seen']}/100 | {db['lexical_exact_seen']}/100 |
| 完全沒被 OCR 看到 | {a['not_observed_by_ocr']} | {b['not_observed_by_ocr']} |
| 原文完全匹配且譯文就緒 | {a['usable_display']}/100 | {b['usable_display']}/100 |
| 3 秒內譯文就緒 | {a['usable_display_within_3_seconds']}/100 | {b['usable_display_within_3_seconds']}/100 |
| 換句至譯文平均 | {metric(a,'display_latency')} ms | {metric(b,'display_latency')} ms |
| 換句至譯文 P95 | {metric(a,'display_latency','p95_ms')} ms | {metric(b,'display_latency','p95_ms')} ms |
| 換句至譯文 Max | {metric(a,'display_latency','max_ms')} ms | {metric(b,'display_latency','max_ms')} ms |
| OCR 單次平均 | {metric(a,'ocr_call_latency')} ms | {metric(b,'ocr_call_latency')} ms |
| OCR 單次 P95 | {metric(a,'ocr_call_latency','p95_ms')} ms | {metric(b,'ocr_call_latency','p95_ms')} ms |
| 擷取次數 | {a['captures']} | {b['captures']} |
| OCR 次數 | {a['ocr_calls']} | {b['ocr_calls']} |
| OCR 完全匹配次數 | {a['ocr_exact_call_count']} | {b['ocr_exact_call_count']} |
| OCR 累計 wall time | {a['ocr_wall_work_ms']/1000:.2f} s | {b['ocr_wall_work_ms']/1000:.2f} s |
| 模型請求數 | {a['backend_requests']} | {b['backend_requests']} |
| 快取命中 | {a['cache_hits']} | {b['cache_hits']} |
| 護欄擋下結果數 | {a['guard_rejections']} | {b['guard_rejections']} |
| 同一完全匹配句的額外譯文顯示 | {a['duplicate_display_results']} | {b['duplicate_display_results']} |
| OCR 原文不完全匹配但有 target 的顯示 | {a['nonexact_source_display_results']} | {b['nonexact_source_display_results']} |
| 原句已換掉才收到譯文 | {a['display_after_sentence_changed']} | {b['display_after_sentence_changed']} |

延遲只納入成功就緒的句子（靜態 n={a['display_latency']['n'] if a['display_latency'] else 0}、動態 n={b['display_latency']['n'] if b['display_latency'] else 0}）；沒有把漏句／拒絕當成 0 ms。P95 使用 nearest-rank。

動態背景 OCR 次數是靜態的 **{ratio:.2f} 倍**。這是實際額外辨識工作量；OCR wall time 是實際經過時間，不能直接當作 CPU 核心耗時、整機 CPU 百分比或顯存增幅。

動態有 {b['display_after_sentence_changed']} 筆結果到達時，fixture 已換到下一句。現有事件防呆以「已接受的 OCR 事件」判斷最新，不等於 fixture 當下仍顯示該句；下一句尚未被掃描／接受時，前句仍可能晚到。因此模型快、事件 ID 正確，都不足以保證每 3 秒字幕的即時體驗。需另改善掃描、stable 排程與擷取後的時效判斷；這是本次發現，尚未修正。

「全部無警告輸出」以 event ID、translation source 與該事件最近的匹配 OCR 觀測連結 fixture，包含原文字母認錯的結果；因此與原文完全匹配的統計分開，不能當成翻譯準確率。字詞一致指忽略標點／大小寫後逐字比對，不是語意評分。其逐筆對照見 [事件對照](assets/verification/moving-background-100-derived-a4.json)。

## 排程與資源

| 平均／P95（ms） | 靜態雜訊 | 動態雜訊 |
| --- | ---: | ---: |
| stability_wait_ms | {stages(static,'stability_wait_ms')} | {stages(moving,'stability_wait_ms')} |
| translation_request_ms | {stages(static,'translation_request_ms')} | {stages(moving,'translation_request_ms')} |
| observed_pipeline_ms（無警告輸出，含 Qt 接收） | {metric(da,'observed_pipeline')} / {metric(da,'observed_pipeline','p95_ms')} | {metric(db,'observed_pipeline')} / {metric(db,'observed_pipeline','p95_ms')} |

上述管線時間起點為程式第一次捕捉候選圖；與「fixture 換句至譯文」不同，不含換句後等待首次掃描的時間。非串流請求沒有可靠 TTFT／prefill／decode，本報告不推算。

| 資源／fixture | 靜態雜訊 | 動態雜訊 |
| --- | ---: | ---: |
| App working set 30 秒取樣 | {working(static,'working_mib')} MiB | {working(moving,'working_mib')} MiB |
| App private usage 30 秒取樣 | {working(static,'private_mib')} MiB | {working(moving,'private_mib')} MiB |
| App CPU 秒（包含 fixture） | {a['cpu_seconds_including_fixture']:.3f} | {b['cpu_seconds_including_fixture']:.3f} |
| 合成場景繪製次數（不含初始一張） | {a['render_frames']} | {b['render_frames']} |
| 合成場景繪製 wall time | {a['render_wall_ms']/1000:.3f} s | {b['render_wall_ms']/1000:.3f} s |
| 實際每句停留範圍 | {a['sentence_duration_min_s']}–{a['sentence_duration_max_s']} s | {b['sentence_duration_min_s']}–{b['sentence_duration_max_s']} s |
| 同一句內捕捉到多個不同像素雜湊的句數 | {motion[0]} | {motion[1]} |

App CPU 包含同程序 20 FPS 合成動畫的成本；因此不能把差值全部歸因於產品監測。這輪沒有重測模型 RAM 或 GPU VRAM；以前的顯存取樣不冒充本次讀值。

## 未就緒句子與警告

靜態沒有任何完全匹配 OCR：{case_list(static,'exact_ocr_seen')}。動態：{case_list(moving,'exact_ocr_seen')}。

靜態沒有完全匹配且無警告的譯文：{case_list(static,'usable_display')}。動態：{case_list(moving,'usable_display')}。缺失包括辨識錯誤、護欄拒絕與時間不足，需要分別判讀；不能一律算背景造成。

| 階段 | 句號 | UI 警告 |
| --- | --- | --- |
{warnings(static)}
{warnings(moving)}

目前護欄警告中的「已保留原文」指主介面核對內容；浮層仍只顯示譯文，失敗時為空白。沒有為了通過測試而自動重試或更換模型。

## 場景與測量邊界

1450 × 250 ROI，Arial 30 pt 白字、4 px 黑描邊，沒有不透明字幕底板。背景是低解析雜訊放大、移動正弦波與逐幀不同的隨機雜訊；動態目標 20 FPS。靜態使用相同色彩／雜訊參數，但停止動畫。這是一種有描邊、可讀字幕的測試，不涵蓋所有遊戲背景、字體、粒子或極小字。

![靜態雜訊第 50 句](assets/noise-static_noise-case-50.png)

![動態雜訊第 50 句的其中一幀](assets/noise-moving_noise-case-50.png)

這些 PNG 只是場景樣本；不同 frame hash 與繪製數才是動畫持續變動的證據。繪字先畫黑描邊再填白字，啟動前檢查至少 1,000 個明亮白色像素。本次以合成 ndarray 替代 GDI 擷取，Qt 不在桌面合成顯示；**不測實際遊戲擷取成本、GPU 遊戲競爭、FPS／frametime 或實體螢幕可見延遲**。相同 100 句重跑靜／動以隔離背景影響，並非 200 句不同英文。早先舊 corpus，以及描邊遮住白字的未完成階段均已中斷保存診斷，沒有納入本表。

兩階段 monitor 均完整排空，測試自有模型／工作執行緒退出，30 個應用程式原始檔雜湊維持不變。逐句原文、OCR、target、警告、時戳與數字計數保存在 [完整結果](assets/verification/moving-background-100-a4.json)；[新 100 句語料](assets/verification/moving-background-100-corpus-a4.json)可重現。所有文字皆為測試產生，沒有使用者聊天或遊戲擷取。
'''
(ROOT/'BENCHMARK_MOVING_BACKGROUND.md').write_text(text,encoding='utf-8')
print(json.dumps({'published': True, 'static': a, 'moving': b},ensure_ascii=False))
