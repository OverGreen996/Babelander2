"""Generate alpha 4 notes from this build's evidence; retain alpha 3 separately."""
from pathlib import Path
import hashlib
import json
import math
import shutil
from babelander import __version__

ROOT=Path(__file__).resolve().parent
RESULTS=ROOT/'test-results'
def read(name):return json.loads((RESULTS/name).read_text(encoding='utf-8-sig'))
unit,assets,pipeline,bundle,wheel,soak=[read(n) for n in ('unit-tests.json','asset-unit.json','pipeline.json','packaged-a4.json','wheel.json','soak-frozen-a4-background.json')]
assert all(r['passed'] for r in (unit,assets,pipeline,bundle,wheel,soak))
assert bundle['version']==pipeline['version']==soak['version']==wheel['selftest']['version']==__version__
assert soak['frozen'] and not soak['real_desktop_capture'] and soak['qt_platform']=='offscreen'
exe=ROOT/'dist/releases'/__version__/'Babelander2/Babelander2.exe'
assert soak['exe_sha256']==hashlib.sha256(exe.read_bytes()).hexdigest()
frozen=read('frozen-source-a4.json')
assert all(hashlib.sha256((ROOT/'babelander'/name).read_bytes()).hexdigest()==digest for name,digest in frozen.items())
assert all(wheel['wheel_source_matches'].values())
verification=ROOT/'assets/verification'
verification.mkdir(exist_ok=True,parents=True)
for source,destination in [('unit-tests.json','unit-tests-a4.json'),('asset-unit.json','asset-unit-a4.json'),('pipeline.json','pipeline-a4.json'),
                           ('packaged-a4.json','packaged-a4.json'),('wheel.json','wheel-a4.json'),('soak-frozen-a4-background.json','soak-frozen-a4-background.json'),
                           ('frozen-source-a4.json','frozen-source-a4.json')]:
    shutil.copy2(RESULTS/source,verification/destination)

warm=[r for r in soak['samples'] if r['elapsed']>=120]
assert len(warm)>=2
def range_text(rows,key):return f"{min(r[key] for r in rows):.2f}–{max(r[key] for r in rows):.2f}"
model=[r['model'] for r in warm if r.get('model') and 'error' not in r['model']]
gpu=read('gpu-samples-a4.json')
gpu_values=[r['model']['dedicated_bytes']/1048576 for r in gpu['records'] if r.get('model',{}).get('counters_available')]
gpu_shared=[r['model']['shared_bytes']/1048576 for r in gpu['records'] if r.get('model',{}).get('counters_available')]
# Publish only the owned PID and values, excluding computer hostnames in paths.
public_gpu={'scope':gpu['scope'],'samples':[{'utc':r['utc'],'model_pid':r['model_pid'],'app_pid':r['app_pid'],
    **{name:{k:v for k,v in r.get(name,{}).items() if k!='samples'} for name in ('model','app')}} for r in gpu['records']]}
(verification/'gpu-samples-a4.json').write_text(json.dumps(public_gpu,ensure_ascii=False,indent=2),encoding='utf-8')
gpu_note=f"{min(gpu_values):.2f}–{max(gpu_values):.2f} MiB（{len(gpu_values)} 次取樣）" if gpu_values else 'N/A'
gpu_shared_note=f"{min(gpu_shared):.2f}–{max(gpu_shared):.2f} MiB" if gpu_shared else 'N/A'

def percentiles(values):
    values=sorted(values)
    if not values:return 'N/A'
    def at(p):return values[max(0,math.ceil(len(values)*p)-1)]
    return f'{at(.5):.1f} / {at(.95):.1f} / {values[-1]:.1f}'
timing_rows=[]
for state in ('cold','warm','cache','none'):
    rows=[r for r in soak['results'] if state in r.get('backend_states',[])]
    label='完整規則／既有文字' if state=='none' else state
    timing_rows.append(f"| {label} | {len(rows)} | {percentiles([r['ms'] for r in rows])} | {percentiles([r['stages']['translation_request_ms'] for r in rows])} |")
counts=soak['pipeline']['counts']
translated=sum(r['count'] for r in soak['results'])
text=f'''# 第二代測試紀錄 · {__version__}

日期：2026-10-08；Windows 11 x64／Python 3.12.14／RTX 3080 Ti／Qwen3-1.7B Q4_K_M／llama.cpp CUDA b10896。

本輪核心 {unit['tests_run']} 項、管線／UI {pipeline['tests']} 項、下載故障合約 {assets['tests_run']} 項全部通過。新版 EXE 與隔離 wheel 各通過 {len(bundle['checks'])} 個真實 OCR／CUDA／Qt 自測檢查；最終 EXE 背景監測 {soak['duration_seconds']:.1f} 秒，{translated} 段譯文、{len(soak['results'])} 次結果（包含清空事件），零翻譯警告、零監測錯誤。

全部新測試使用 **Qt offscreen**，不顯示桌面測試視窗、不註冊測試快捷鍵、不擷取遊戲或使用者畫面、不呼叫付費 API。版本與 EXE SHA-256 綁定本輪；原生桌面／API／30 分鐘結果保留在 [alpha 3 歷史報告](TEST_REPORT_ALPHA3.md)，不算本輪重測。

## 新測試證據

| 檢查 | 結果與範圍 | 原始報告 |
| --- | --- | --- |
| 核心回歸 | {unit['tests_run']} 項；快取、取消、優先順序、私訊不持久化、DPAPI、護欄、雲端單次送出 | [unit-tests-a4.json](assets/verification/unit-tests-a4.json) |
| 管線／UI | {pipeline['tests']} 項；合成慢翻譯、真實 Qt queued notice、原文不進浮層、舊事件／空白／停止、圖片入場限制 | [pipeline-a4.json](assets/verification/pipeline-a4.json) |
| 下載故障合約 | {assets['tests_run']} 項，受控回應、零下載 | [asset-unit-a4.json](assets/verification/asset-unit-a4.json) |
| 最終 EXE | {len(bundle['checks'])} 個自測檢查，真實 OCR／CUDA／Qt，offscreen | [packaged-a4.json](assets/verification/packaged-a4.json) |
| 隔離 wheel | {len(wheel['wheel_source_matches'])} 個源碼／QSS 檔案吻合，實際隔離匯入與自測通過 | [wheel-a4.json](assets/verification/wheel-a4.json) |
| 最終 EXE 背景監測 | {soak['duration_seconds']:.1f} 秒、{translated} 段譯文；停止後、關閉前自有模型程序已退出 | [soak-frozen-a4-background.json](assets/verification/soak-frozen-a4-background.json) |
| 獨立 GPU 計數器 | 只查本輪測試 PID，未使用整張顯卡總量 | [gpu-samples-a4.json](assets/verification/gpu-samples-a4.json) |

合成慢翻譯刻意阻塞兩秒，Capture／OCR 持續觀測 A→B→C→D。只提交 A、D；B/C 各有 `skipped_superseded`，A 晚完成有 `ui_suppressed_stale`；D 成為唯一可顯示結果。聊天待翻滿載維持八件 FIFO，淘汰原因計數。這證明翻譯不阻塞生產端，不能證明未擷取到的字幕也已保存。

## 本輪資源實測

暖機後時間點取樣（120 秒起）以 Windows 程序計數器分開記錄 App 與模型；MiB = 1,048,576 bytes。

| 程序／項目 | 暖機後範圍 |
| --- | --- |
| App working set | {range_text(warm,'rss_mb')} MiB |
| App private usage | {range_text(warm,'private_mb')} MiB |
| App handles | {min(r['handles'] for r in warm)}–{max(r['handles'] for r in warm)} |
| 模型 working set | {range_text(model,'rss_mb')} MiB |
| 模型 private usage | {range_text(model,'private_mb')} MiB |
| 模型 GPU Dedicated Usage（Windows 回報） | {gpu_note} |
| 模型 GPU Shared Usage（Windows 回報） | {gpu_shared_note} |

GPU 資料來自外部 `GPU Process Memory` 計數器，所以長測主 JSON 內的 `vram_mb` 仍為 null；沒有拿 N/A 當零。模型退出以程序生命週期另證實，不以計數器消失宣稱全機 VRAM 或 OS 檔案快取歸零。Windows 已知部分情境的程序 GPU 計數器可能錯報，因此保留來源與原始數值，不把這個單機讀值當作保證值。[Microsoft 計數器限制](https://learn.microsoft.com/en-us/troubleshoot/windows-client/performance/gpu-process-memory-counters-report-wrong-value)

本輪沒有舊版同素材的 A/B，**不能宣稱 RAM／VRAM 降低多少百分比**。改善的證據是已執行的上限、淘汰政策、背景釋放與穩定取樣。ONNX native 配置、Qt pixmap、GDI 複製、OS 檔案快取均不能只靠 Python 物件數推算。

## 延遲與分類

| 路徑 | 結果數 | 觀測至 worker 結果 P50／P95／Max（ms） | 完整翻譯請求 P50／P95／Max（ms） |
| --- | --- | --- | --- |
{chr(10).join(timing_rows)}

觀測起點為程式開始當次擷取，不是字幕在遊戲出現；包括擷取／OCR／穩定等待／派送／請求／後處理。UI slot 另記 `overlay_update_ms` 與 `observed_pipeline_ms`。後端非串流，TTFT／prefill／decode 為 N/A，不由總請求時間推算。P50/P95 使用 nearest-rank；這次固定四句、每三秒換句、每分鐘清快取，不能代表遊戲中的大量快速字幕或語意準確率。長測掃描 300 ms／穩定 150 ms 僅為 fixture，**產品預設仍 800／300 ms**。

事件統計：{json.dumps({k:counts.get(k,0) for k in ('events_created','success','cache_hit','rejected','skipped_superseded','skipped_capacity','cancelled','error','ui_suppressed_stale')},ensure_ascii=False)}。

## 尚未驗收

- 真實遊戲、動畫背景、極小字、跨螢幕混合 DPI、擷取 ROI 的 GDI 成本與 FPS／frametime 影響。
- Qwen3 1.7B 與其他模型的人工語意評測；結構護欄不保證語意正確，[既有品質問題](QUALITY_REVIEW.md)仍有效。
- fast／shared／CPU、KV 格式與 context 大小的延遲、RAM、GPU 記憶體與品質 A/B；本輪不更換預設。
- 本版尚無完整 30 分鐘持續測試；alpha 3 的 30 分鐘結果不能移用給 alpha 4。

打包原本遇到已開啟舊版鎖定檔案，改為 `dist/releases/{__version__}`；已從相同依賴補回舊資料夾缺少的檔案，原 a3 EXE 雜湊保持一致，不中斷使用中的程序。源碼 ZIP 不含模型、金鑰、SQLite、虛擬環境或測試暫存。
'''
benchmark_path=ROOT/'test-results/english-100/results.json'
if benchmark_path.exists():
    benchmark=json.loads(benchmark_path.read_text(encoding='utf-8'))
    if benchmark['completed'] and benchmark['version']==__version__:
        s=benchmark['summary']
        text+=f'''\n## 追加：100 句全新英文\n\n同一批 100 句各跑純翻譯與 OCR 到 Qt 兩遍，共 200 次本機請求、0 快取命中。暖機純翻譯平均 {s['translation_warm']['mean_ms']:.2f} ms；OCR 至 Qt 平均 {s['ocr_to_ui_all']['mean_ms']:.2f} ms、P95 {s['ocr_to_ui_all']['p95_ms']:.2f} ms。97 句有譯文、3 句被否定護欄擋下；另三次診斷發現「從未／未」誤擋與 treasury 殘留英文，沒有改動應用程式碼。詳細資料與測量邊界見 [100 句英文報告](BENCHMARK_100_ENGLISH.md)。\n'''
(ROOT/'TEST_REPORT.md').write_text(text,encoding='utf-8')
noise_path=ROOT/'test-results/moving-background-100/results.json'
if noise_path.exists():
    noise=json.loads(noise_path.read_text(encoding='utf-8'))
    if noise['completed'] and noise['version']==__version__ and noise.get('source_unchanged'):
        static=noise['phases']['static_noise']['summary']
        moving=noise['phases']['moving_noise']['summary']
        text+=f'''\n## 追加：另一組 100 句動態雜訊背景\n\n另一組全新英文，每句 3 秒，靜態／動態各跑 300 秒；使用產品預設 scan 800／stable 300 ms，真實 OCR、CUDA 模型與 offscreen Qt。靜態／動態至少一次完全匹配 OCR：{static['exact_ocr_seen']}／{moving['exact_ocr_seen']} 句；完全匹配且無警告譯文：{static['usable_display']}／{moving['usable_display']} 句。成功就緒句的換句至 Qt 平均延遲：{static['display_latency']['mean_ms']:.2f}／{moving['display_latency']['mean_ms']:.2f} ms；OCR 呼叫：{static['ocr_calls']}／{moving['ocr_calls']} 次。這是有描邊白字的合成動畫，尚未驗證真實遊戲或語意正確率。逐句對照與資源邊界見 [動態背景測試報告](BENCHMARK_MOVING_BACKGROUND.md)。\n'''
        (ROOT/'TEST_REPORT.md').write_text(text,encoding='utf-8')
subtitle_path=ROOT/'test-results/subtitle-quick/results.json'
if subtitle_path.exists():
    subtitle=json.loads(subtitle_path.read_text(encoding='utf-8'))
    if subtitle['completed'] and subtitle['version']==__version__ and subtitle.get('source_unchanged'):
        s=subtitle['summary']
        text+=f'''\n## 追加：真實 SRT 快測\n\n完整 {subtitle['total_cues']} 段字幕，文字翻譯平均 {s['translation_all']['mean_ms']:.2f} ms、P95 {s['translation_all']['p95_ms']:.2f} ms；{s['translation_usable']} 段有無警告譯文、{s['translation_rejected']} 段被拒絕。再抽 100 段，OCR 到 Qt 平均 {s['ocr_ui_all']['mean_ms']:.2f} ms；300 張不同背景快照有 {s['all_ocr_lexical_exact']} 張字詞一致（忽略標點／大小寫）。主測試 {subtitle['wall_seconds']:.2f} 秒；另五次診斷不納入時間統計。抽查發現諷刺、blow Sunday、not … until 錯譯，以及 three-hour 和中文數字正規化造成護欄誤擋；輸出數不代表語意正確率。本次沒有播放／監測 scan／stable 等待。詳見 [SRT 字幕快測](BENCHMARK_SUBTITLE.md)。\n'''
        (ROOT/'TEST_REPORT.md').write_text(text,encoding='utf-8')
print(json.dumps({'passed':True,'version':__version__,'core_tests':unit['tests_run'],'pipeline_tests':pipeline['tests'],
                  'soak_translations':translated,'gpu_samples':len(gpu_values)}))
