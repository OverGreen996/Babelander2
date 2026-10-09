"""Publish completed replay evidence without changing frozen application code."""
import hashlib
import json
from pathlib import Path
import statistics
from replay_analysis import stats

ROOT=Path(__file__).resolve().parent
RAW=ROOT/'test-results/replay-threads-full-a8/results.json'


def generate():
    r=json.loads(RAW.read_text(encoding='utf-8'))
    for key in ('completed','owned_model_stopped','workers_stopped','source_unchanged','temporary_frames_removed'):
        assert r[key],key
    for name,digest in r['application_source_sha256'].items():
        assert hashlib.sha256((ROOT/'babelander'/name).read_bytes()).hexdigest()==digest,name
    for name,digest in r['harness_source_sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    assert all(s['cues']==100 for s in r['summary'].values())
    assert all(p['monitor_drained'] and not p['errors'] for p in r['phases'])
    def f(x):return 'N/A' if x is None else f'{x:.2f}'
    lines=['# alpha8：公平重播與 OCR 2／4 執行緒比較','',
           '2026-10-08。實際 PP-OCRv6 Small／ONNX CPU、Qwen3 1.7B Q4_K_M／CUDA、完整 Qt offscreen 更新。應用源檔與 alpha8 凍結一致；本輪未修改模型、prompt、觸發器或使用者設定。','',
           '每組同樣 100 句、每句 3 秒；固定亂數洗牌，20 句一區塊，以 2→4、4→2 交錯次序測五個區塊。兩组 adaptive/reuse 都關閉、dialog_scan=100 ms、一般 scan=800 ms、stable=100 ms。不是全部 2 跑完才跑全部 4，也沒有同時跑兩套 OCR／模型。','',
           '移動暗雜訊與白字黑描邊預先產生：每句 16 張影像、20 FPS 循環播放，原像素 1450×250；測量時沒有 Qt／OpenCV 動畫繪製。以單一 mmap 分段讀取，另計 I/O／producer deadline。暖機每組固定三張 OCR 與三句模型請求，SQLite 每組清空；llama prefix/KV cache沒有宣稱清空，實際 cached tokens／timings 另存。','',
           '**仍是合成擷取，不是 GDI／DXGI 或真遊戲 FPS 測試。** 時間從該 cue 實際發布到完整譯文 Qt 更新，非實體螢幕像素／首字。循環背景、亂序句子和新重播方式與舊 alpha8 benchmark不同，不能把新舊平均差全部歸因4執行緒。','',
           '| 指標 | 2 threads | 4 threads |','| --- | ---: | ---: |']
    a,b=r['summary']['2'],r['summary']['4']
    metrics=[('700 ms 內可用完整譯文／100',a['usable_within_700ms'],b['usable_within_700ms']),
             ('當句仍顯示時取得完整譯文／100',a['usable_current_display'],b['usable_current_display']),
             ('至少一次完整 OCR／100',a['exact_ocr_seen'],b['exact_ocr_seen']),
             ('OCR 前未觀測／100',a['unobserved'],b['unobserved']),
             ('完整 Qt 平均 ms',f(a['display_latency']['mean_ms']),f(b['display_latency']['mean_ms'])),
             ('完整 Qt P50 ms',f(a['display_latency']['p50_ms']),f(b['display_latency']['p50_ms'])),
             ('完整 Qt P95 ms',f(a['display_latency']['p95_ms']),f(b['display_latency']['p95_ms'])),
             ('完整 Qt Max ms',f(a['display_latency']['max_ms']),f(b['display_latency']['max_ms'])),
             ('平均／P95 分母',a['display_latency']['n'],b['display_latency']['n']),
             ('OCR 次數',a['ocr_calls'],b['ocr_calls']),
             ('OCR 平均 ms',f(a['ocr_call_latency']['mean_ms']),f(b['ocr_call_latency']['mean_ms'])),
             ('OCR P95 ms',f(a['ocr_call_latency']['p95_ms']),f(b['ocr_call_latency']['p95_ms'])),
             ('護欄拒絕',a['guard_rejections'],b['guard_rejections']),
             ('快取命中',a['cache_hits'],b['cache_hits']),
             ('舊原文跨 cue 晚顯示',a['late_source_display'],b['late_source_display'])]
    lines += [f'| {name} | {x} | {y} |' for name,x,y in metrics]
    lines += ['', '可用表示當句顯示期間的完整原文歸屬、目標文字非空且現有護欄通過；**不是人工語意正確率**。原文只允許已定義的英文單字末尾句點容差，不忽略否定、數字、問號、驚嘆號或省略號。平均／P95只計成功當句結果；所有100句保留在700ms覆蓋率分母。', '',
              '## 配對結果與區塊負載','',
              '| 區塊（相同20句） | 測量順序 | 2 threads：平均／P95／700ms句數 | 4 threads：平均／P95／700ms句數 |',
              '| --- | --- | --- | --- |']
    block_phases=[p for p in r['phases'] if p['label'].startswith('block-')]
    for i in range(5):
        ps=[p for p in block_phases if p['label'].startswith(f'block-{i+1}-')]
        cells={}
        for p in ps:
            s=p['summary'];d=s['display_latency']
            cells[p['threads']]=f"{f(d['mean_ms'])}／{f(d['p95_ms'])}／{s['usable_within_700ms']}"
        lines.append(f"| {i+1} | {'→'.join(str(p['threads']) for p in ps)} | {cells[2]} | {cells[4]} |")
    mapped={t:{o['cue_id']:o for p in block_phases if p['threads']==t for o in p['outcomes']} for t in (2,4)}
    paired=[(mapped[4][k]['display_latency_ms']-v['display_latency_ms']) for k,v in mapped[2].items()
            if v['display_latency_ms'] is not None and mapped[4][k]['display_latency_ms'] is not None]
    lines += ['',f"兩組皆成功當句顯示的配對 {len(paired)} 句：4 threads 比 2 threads 更快 {sum(x<0 for x in paired)} 句；配對差值（4−2）平均 {f(statistics.mean(paired))} ms。缺失句未塞入0ms，也沒有自動移除失敗後重測來改善覆蓋率。",'',
              '## 混色與短字幕保留集','',
              '另各組18個畫面狀態（12個非空 cue＋6個空白分隔）：暗字同列追加、暗字新行、數字10→18、新增否定、0.6秒短字幕、字幕上下移位。基底1.6秒、變更0.6秒、空白0.6秒。這是小型固定反例集，不是通用遊戲 recall。兩個混色變更的 bright hash 經預檢確實維持相同。','',
              '| 字幕事件 | 2 threads | 4 threads |','| --- | --- | --- |']
    hp={t:{o['cue_id']:o for p in r['phases'] if p['threads']==t and p['label'].startswith('holdout-') for o in p['outcomes'] if o['source']} for t in (2,4)}
    def outcome(o):
        if not o['any_ocr']:return 'OCR前未觀測'
        if not o['exact_ocr']:return 'OCR內容不完整'
        if o['display_latency_ms'] is None:return '未在當句期間顯示可用譯文'
        return f"{f(o['display_latency_ms'])} ms"
    for key,o in hp[2].items():lines.append(f"| {key} | {outcome(o)} | {outcome(hp[4][key])} |")
    lines += ['', '**增加執行緒不能修復沒有喚醒 OCR 的變更。** 混色後綴與新暗字行的事件結果要獨立報告；即使白字100句平均低於700ms，也不能算短／混色字幕全面達標。','',
              '## 真後端時間與資源','',
              'OCR列保留 RapidOCR 回傳的 det／cls／rec 秒數；它們不是所有 preprocessing／postprocessing 的總成本。llama回應保留 usage、prompt_tokens_details.cached_tokens、prompt_ms、predicted_ms等實際欄位；沒回傳就N/A，非串流 TTFT仍沒有量測。','',
              '| 實測平均 ms（非独立P95相加） | 2 threads | 4 threads |','| --- | ---: | ---: |']
    for name,extract in [
        ('OCR backend det',lambda p:[o['backend_det_cls_rec_seconds'][0]*1000 for o in p['ocr'] if o.get('backend_det_cls_rec_seconds') and o['backend_det_cls_rec_seconds'][0] is not None]),
        ('OCR backend rec',lambda p:[o['backend_det_cls_rec_seconds'][2]*1000 for o in p['ocr'] if o.get('backend_det_cls_rec_seconds') and o['backend_det_cls_rec_seconds'][2] is not None]),
        ('llama prompt',lambda p:[x['backend_timings']['prompt_ms'] for x in p['backend'] if x.get('backend_timings')]),
        ('llama predicted',lambda p:[x['backend_timings']['predicted_ms'] for x in p['backend'] if x.get('backend_timings')]),
        ('HTTP request',lambda p:[x['request_ms'] for x in p['backend']]),
        ('frame producer deadline miss',lambda p:[x['deadline_miss_ms'] for x in p['producer'] if 'deadline_miss_ms' in x])]:
        cells=[]
        for t in (2,4):
            v=[x for p in block_phases if p['threads']==t for x in extract(p)]
            cells.append(f(statistics.mean(v)) if v else 'N/A')
        lines.append(f'| {name} | {cells[0]} | {cells[1]} |')
    for t in (2,4):
        ps=[p for p in block_phases if p['threads']==t]
        app_cpu=sum(p['process_cpu_seconds'] for p in ps)
        model_cpu=sum(p['model_resources_after']['cpu_seconds']-p['model_resources_before']['cpu_seconds'] for p in ps)
        samples=[x for x in r['system_load'] if x.get('phase') in {p['label'] for p in ps}]
        app_peak=max([x['app']['working_mib'] for x in samples if x.get('app')]+[p['resources_after']['working_mib'] for p in ps])
        model_peak=max([x['model']['working_mib'] for x in samples if x.get('model')]+[p['model_resources_after']['working_mib'] for p in ps])
        lines += ['',f'{t} threads：測量區塊 app CPU {f(app_cpu)} core-seconds、owned模型程序 CPU {f(model_cpu)} core-seconds；app working-set採樣最大 {f(app_peak)} MiB、模型 working-set採樣最大 {f(model_peak)} MiB。']
    samples=r['system_load']
    cpus=[x['whole_system_cpu_percent'] for x in samples if x.get('whole_system_cpu_percent') is not None]
    vrams=[x['gpu_whole_memory_mib'] for x in samples if x.get('gpu_whole_memory_mib') is not None]
    lines += ['',f'整機 CPU 間隔採樣範圍 {f(min(cpus))}～{f(max(cpus))}%；整機 GPU總使用顯存採樣 {f(min(vrams))}～{f(max(vrams))} MiB。CPU間隔可能跨區塊，GPU為瞬時整機值，不能歸成本程式獨占，也不能拿來宣稱遊戲有足夠餘裕。' if cpus and vrams else '部分整機資源採樣不可用，見原始資料。',
              '',f"預生成 frame bank占磁碟 {r['frame_bank_bytes']/1048576:.2f} MiB，完成後已移除；以單一16張mmap分段讀取，不把所有影像同時載入RAM。app CPU包含producer讀檔、複製與記錄，沒有即時動畫renderer；採樣最大值不是native RAM硬上限。",'',
              '## 決策與限制','',
              '這份對照只決定候選是否值得進真遊戲驗收；不自動升4 threads預設。出貨仍2 threads、reuse/adaptive關閉，alpha8既有 EXE／wheel／source ZIP 沒有被重新封裝。', '',
              '下一刀針對混色觸發盲點作單變項實驗，保留完整輸入，量暗字新增到OCR喚醒與完整Qt更新。短prompt之後依實際prompt／decode成本及品質保留集比較，不能用截短長句或放寬原文護欄刷速度。', '',
              '11項 replay 計數回歸通過（未觀測、過期顯示、拒絕、空譯文、重复事件、700ms邊界、句尾句點容差、缺失延遲、禁止語意正確率宣稱）。初版小試跑因category標籤缺失停止，已修正；第二次2句試跑確認流程，兩者均不混入正式100句數據。', '',
              '自有模型與worker均已停止、臨時frame bank已移除、凍結應用源檔一致。完整新重播尚未測真遊戲 GDI／FPS／frametime、HDR／特殊字型、實體螢幕延遲，也未完成全部譯文人工語意標註。', '',
              '[完整原始資料](assets/verification/replay-threads-full-a8.json)、[三回合辯論](DEBATE_ALPHA8.md)、[舊版完整延遲](BENCHMARK_LATENCY_A8.md)。']
    public=ROOT/'assets/verification/replay-threads-full-a8.json'
    public.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'BENCHMARK_REPLAY_THREADS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'summary':r['summary'],'holdout_summary':r['holdout_summary'],'report':'BENCHMARK_REPLAY_THREADS.md'}))


if __name__=='__main__':generate()
