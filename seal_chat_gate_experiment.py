"""Preserve rejected experiments without replacing the released alpha22."""
from pathlib import Path
import json,hashlib,shutil,zipfile
ROOT=Path(__file__).resolve().parent;PUBLIC=ROOT/'assets/verification/chat-noise-experiment'
def read(name):return json.loads((ROOT/name).read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
original=read('dist/Babelander2-2.0.0a22-sha256.json')
baseline=read('assets/verification/chat-poll-a22/summary.json')
actual={p.name:sha(p) for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}
assert actual==baseline['application_sha256']
exe=ROOT/'dist/releases/2.0.0a22/Babelander2/Babelander2.exe'
source=ROOT/'dist/Babelander2-2.0.0a22-source.zip'
assert sha(exe)==original['exe_sha256'] and sha(source)==original['source_zip_sha256']
resources=read('test-results/chat-gate-resources.json')
edges=read('test-results/chat-gate-edges.json')
flashes=[read('test-results/chat-gate-flash.json'),read('test-results/chat-gate-flash-reversed.json')]
stress=read('test-results/chat-gate-live/report.json')
candidate=sha(ROOT/'chat_gate_experiment.py')
assert all(r['candidate_sha256']==candidate for r in [resources,edges,stress,*flashes])
assert resources['passed'] and all(f['owned_model_stopped'] for f in flashes)
assert all(not f['recall_not_worse'] for f in flashes)
grouped={}
for scene in ('jitter14','waves','translucent','particles'):
    row={}
    for enabled in (False,True):
        runs=[r for r in resources['runs'] if r['scene']==scene and r['enabled']==enabled]
        row[str(enabled)]={'cpu_core_seconds':sum(r['cpu_core_seconds'] for r in runs),
                           'ocr_calls':sum(r['ocr_calls'] for r in runs)}
    row['cpu_reduction_percent']=100*(1-row['True']['cpu_core_seconds']/row['False']['cpu_core_seconds'])
    grouped[scene]=row
latency=[e['shown_to_qt_ms'] for f in flashes for r in f['runs'] if not r['enabled'] for e in r['events']]
summary={'decision':'rejected_for_default','production_version':'2.0.0a22','production_core_unchanged':True,
    'released_exe_unchanged':True,'released_source_zip_unchanged':True,'candidate_sha256':candidate,
    'resource_scope':'Shared warmed real CPU OCR, 12s x two balanced phases per setting per scene. Translation stub; no GPU/FPS/VRAM conclusion. Same-process RAM has allocator/thread history and is not causal memory evidence.',
    'resources':grouped,'recognizable_edge_changes':edges['recognizable_changes'],
    'missed_200ms_flash_cases':edges['missed_200ms_flash'],
    'real_flash_control_latencies_ms':latency,'real_flash_candidate_events':0,
    'flash_orders':['control/candidate','candidate/control'],
    'stress_discovery_only':True,'stress_timings_valid_for_acceptance':False,
    'stress_limitations':'Particle decorations are recognized as symbols; unknown source IDs contaminate result counts. Existing count-based block drain may cancel the final real message after spurious results exceed the count. Captured animation phase uses an absolute clock and is not anchored to each exposure. Do not use this run as a 100-message full latency or recall benchmark.',
    'real_desktop_capture':False,'foreground_control_calls':0,'paid_api_calls':0}
PUBLIC.mkdir(parents=True,exist_ok=True)
paths={'resources.json':'chat-gate-resources.json','edges.json':'chat-gate-edges.json',
    'flash.json':'chat-gate-flash.json','flash-reversed.json':'chat-gate-flash-reversed.json',
    'stress-discovery.json':'chat-gate-live/report.json','noise-discovery.json':'chat-gate-discovery.json'}
for destination,name in paths.items():shutil.copy2(ROOT/'test-results'/name,PUBLIC/destination)
(PUBLIC/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
table='\n'.join(f"| {name} | {r['False']['cpu_core_seconds']:.2f} → {r['True']['cpu_core_seconds']:.2f}s | {r['cpu_reduction_percent']:.1f}% | {r['False']['ocr_calls']} → {r['True']['ocr_calls']} |" for name,r in grouped.items())
text=f'''# 抗雜訊聊天觸發器實驗：未採用

本輪候選沒有通過「不增加漏讀」的驗收，正式版保留 alpha22。`babelander/` 全部 40 個 Python／QSS 檔案、已封存 EXE 和 alpha22 原始碼 ZIP 的 SHA 均與發布紀錄一致。候選只在測試時注入，沒有新增設定或更換正式引擎。

## 候選與資源結果

每 100ms 觀察。候選以半尺寸 RGB 的 3／15px 局部濾波差比較筆畫結構，OCR 已確認的行位置採較敏感門檻，全區域仍檢查新行；400ms 定期完整 OCR。觸發器用低解析特徵，真正 OCR 保留原圖。只保留一份特徵與位置 mask，通常約 1.08MiB，適用 ROI 上限 1,048,576 畫素；其他格式／更大區域回原本流程。濾波使用現有 Pillow 依賴，不調整全域 OpenCV 執行緒、不新增模型或 OCR 引擎。

同一個已預熱 CPU OCR、每場景 control/candidate/candidate/control，每段 12 秒，各組合計約 24 秒。翻譯明確 stub，不能拿此表當完整翻譯或 GPU 資源測試。

| 生成場景 | 程序 CPU 核心秒 | CPU 減少 | OCR 次數 |
| --- | ---: | ---: | ---: |
{table}

jitter14 為逐畫素、各 RGB 通道獨立 ±14 雜訊；不能推廣成所有遊戲的背景雜訊。waves 是移動平滑光影，translucent 是光影疊加至文字，particles 是移動亮方粒子。較強 ±24 雜訊會回完整辨識。相同程序的 RAM 受 native allocator 與新協調執行緒歷史影響，未據此宣稱 RAM 增減；沒有 VRAM／遊戲 FPS 量測。

## 決定性反例：短暫暗字

舊行 `Jo: GG` 保持亮色，新行 `Rin: Need keys x5.` 使用 RGB(30,34,40)，背景 RGB(16,20,26)，只出現約 200ms。此文字是實際 RapidOCR 能辨識的內容，原版能送到本機模型並顯示有效譯文。

實際 CPU OCR → 暖 CUDA Qwen → Qt，正序與反序各跑一次：

- 原版兩次都收到新訊息，完整顯示分別 **{'／'.join(f'{v:.2f}ms' for v in latency)}**，均在 700ms 內。
- 候選兩次都未產生新訊息事件；觸發器把它當成細微變化略過。400ms 的安全複查來不及補救已消失的文字。
- 31 組數量、否定、新行、彩字、捲動、亮底、小字等訊號測試，實際完整 OCR 有 30 組文字變化；其中 **{len(edges['missed_200ms_flash'])} 組**在候選的 200ms 視窗內未觸發。這不是全面語意正確率評分。

因此節省 CPU 的收益不足以接受本候選。提高門檻、延長複查或只測高對比白字，都不能解決這個反例。

## 另外發現的壓測問題

四輪真引擎動態聊天探索沒有通過完整功能驗收。亮粒子能被既有 OCR 認成 `■` 等符號，污染聊天事件；這不是只調觸發器能解決的問題。

這也暴露測試工具限制：區塊排空以收到的結果數判斷，假字結果超過門檻後可能提早停止，取消最後一則真正訊息；動畫 phase 使用絕對時鐘，沒有對齊每則曝光。該批原始 JSON 保留，但它的平均／P95 與缺句數**不能作為正式 100 則延遲或召回對照**。alpha22 原本乾淨畫面的驗收仍保留，不能推廣成這批新動態場景也通過。

## 重現與下一個突破點

在 v2 以 `.venv/Scripts/python.exe` 執行 `probe_chat_gate_edges.py`、`probe_chat_gate_flash.py` 及後者加 `--reverse`。flash 的程式結束碼 1 表示候選召回驗收失敗，並非模型啟動失敗；所有測試模型都已回收，沒有桌面擷取、前景控制或付費 API。

下一個版本需要先修好兩件事：以實際事件及工作狀態判定壓測排空，避免假字污染統計；再建立能分辨弱字形與雜訊的「不確定就辨識」判斷，並把本輪 200ms 暗字反例固定為必要驗收。粒子誤讀還需要獨立檢查幾何／文字組合，不能直接丟棄所有符號，因為聊天室也可能有合法標點或表情。

[原始數據與決策](assets/verification/chat-noise-experiment/summary.json)。完整實驗及可編輯程式另備份至 `dist/Babelander2-2.0.0a22-noise-experiment-source.zip`，原 alpha22 封存不覆寫。
'''
(ROOT/'TEST_REPORT_CHAT_NOISE_EXPERIMENT.md').write_text(text,encoding='utf8')
scripts=['chat_gate_experiment.py','chat_gate_fixtures.py','probe_chat_gate_discovery.py',
    'probe_chat_gate_edges.py','probe_chat_gate_flash.py','probe_chat_gate_resources.py',
    'probe_chat_gate_suite.py','probe_chat_poll.py','seal_chat_gate_experiment.py','TEST_REPORT_CHAT_NOISE_EXPERIMENT.md']
overlays={name:ROOT/name for name in scripts}
overlays.update({p.relative_to(ROOT).as_posix():p for p in PUBLIC.iterdir() if p.is_file()})
backup=ROOT/'dist/Babelander2-2.0.0a22-noise-experiment-source.zip';index={}
with zipfile.ZipFile(source) as old,zipfile.ZipFile(backup,'w',zipfile.ZIP_DEFLATED) as new:
    for name in old.namelist():
        if name.removeprefix('Babelander2/') in overlays:continue
        data=old.read(name);new.writestr(name,data);index[name]=hashlib.sha256(data).hexdigest()
    for name,path in overlays.items():
        data=path.read_bytes();name='Babelander2/'+name;new.writestr(name,data);index[name]=hashlib.sha256(data).hexdigest()
with zipfile.ZipFile(backup) as archive:
    assert all(hashlib.sha256(archive.read(name)).hexdigest()==digest for name,digest in index.items())
manifest={'passed':True,'decision':'rejected_for_default','production_core_unchanged':True,
    'production_exe_sha256':sha(exe),'original_source_zip_sha256':sha(source),
    'experiment_source_zip_sha256':sha(backup),'experiment_source_files':index,'summary':summary}
(ROOT/'dist/chat-noise-experiment-sha256.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'sealed':True,'adopted':False,'core_unchanged':True,'source_files':len(index),
                  'flash_control_ms':latency,'backup_sha256':sha(backup)}))
