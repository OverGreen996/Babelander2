"""Identical 100 pre-rendered chat frames, isolated ABBA CPU OCR comparison."""
import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--child', choices=('full', 'reuse'))
parser.add_argument('--round', type=int, default=0)
parser.add_argument('--out', default='chat-incremental-a21')
args = parser.parse_args()
out = ROOT / 'test-results' / args.out
out.mkdir(parents=True, exist_ok=True)
if args.child:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from bootstrap import prepare
    prepare()
    import numpy as np
    from dataclasses import asdict
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase
    from babelander.ocr import OCR
    from babelander.chat_ocr import ChatRecognitionCache
    from babelander.types import Cancellation
    from babelander.chat import messages
    from babelander.controller import new_chat_lines
    from chat_fixtures import chat_frame
    from replay_resources import process
    app = QApplication(['Offscreen chat OCR comparison'])
    for font in ('arial.ttf', 'msjh.ttc'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
    # Fixture rendering is outside the timed run, never in the capture worker.
    frames = [chat_frame(list(range(max(i // 20 * 20, i - 3), i + 1)))[1] for i in range(100)]
    engine, token, cache = OCR(), Cancellation(), ChatRecognitionCache()
    engine.recognize(frames[0], token)
    baseline_mem = process()
    samples, memory, previous = [], [], []
    cpu_start = time.process_time()
    for i, frame in enumerate(frames):
        if i % 20 == 0:
            cache.clear()
            previous = []
        at = time.perf_counter()
        lines = engine.recognize(frame, token, chat_cache=cache if args.child == 'reuse' else None)
        elapsed = (time.perf_counter() - at) * 1000
        current = [line.text for line in messages(lines)]
        events = new_chat_lines(previous,current)
        previous = current
        samples.append({'index': i, 'ocr_ms': elapsed, 'lines': [asdict(l) for l in lines],
                        'new_events':events,
                        'reuse': dict(cache.last) if args.child == 'reuse' else {},
                        'frame_sha256': hashlib.sha256(frame.tobytes()).hexdigest()})
        memory.append(process())
        if i % 20 == 19:
            print(json.dumps({'round': args.round, 'config': args.child, 'completed': i+1}), flush=True)
    report = {'config': args.child, 'round': args.round, 'samples': samples,
              'cpu_core_seconds': time.process_time()-cpu_start,
              'latency': {'mean_ms': float(np.mean([s['ocr_ms'] for s in samples])),
                          'p95_ms': float(np.percentile([s['ocr_ms'] for s in samples], 95)),
                          'max_ms': max(s['ocr_ms'] for s in samples)},
              'recognition_reused': sum(s['reuse'].get('reused', 0) for s in samples),
              'recognition_crops': sum(s['reuse'].get('crops', 0) for s in samples),
              'recognition_inferred': sum(s['reuse'].get('inferred', 0) for s in samples),
              'warm_memory': baseline_mem,
              'private_max_mib': max(m['private_mib'] for m in memory),
              'working_max_mib': max(m['working_mib'] for m in memory),
              'shared_engine_context_cleared': engine.engine.chat_context is None}
    cache.clear()
    report['session_cache_cleared'] = not cache.entries and cache.scope is None
    (out / f'{args.round}-{args.child}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k != 'samples'}), flush=True)
else:
    frozen = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*.py')}
    env = os.environ.copy(); env['PYTHONIOENCODING']='utf-8'
    configs = ('full', 'reuse', 'reuse', 'full')
    for i, config in enumerate(configs):
        subprocess.run([sys.executable, __file__, '--child', config, '--round', str(i), '--out', args.out],
                       cwd=ROOT, env=env, check=True, timeout=240, creationflags=subprocess.CREATE_NO_WINDOW)
    runs = [json.loads((out/f'{i}-{c}.json').read_text(encoding='utf8')) for i,c in enumerate(configs)]
    first = runs[0]['samples']
    mismatches = []
    for r in runs[1:]:
        for base, sample in zip(first, r['samples']):
            if ([l['text'] for l in base['lines']] != [l['text'] for l in sample['lines']]
                    or [l['box'] for l in base['lines']] != [l['box'] for l in sample['lines']]):
                mismatches.append({'round':r['round'],'index':sample['index'],
                                   'full':base['lines'],'candidate':sample['lines']})
    event_mismatches = [{'round':r['round'],'index':a['index'],'full':a['new_events'],'candidate':b['new_events']}
                        for r in runs[1:] for a,b in zip(first,r['samples']) if a['new_events']!=b['new_events']]
    result = {'scope': '100 identical pre-rendered frames, five scrolling styles, isolated ABBA processes, two CPU OCR threads. OCR time only, no model/GPU/desktop capture. Raw old-line recognition differences are retained separately from emitted new-message differences.',
              'runs':runs, 'mismatches':mismatches,
              'event_mismatches':event_mismatches,
              'frames_identical':all([s['frame_sha256'] for s in r['samples']]==[s['frame_sha256'] for s in first] for r in runs),
              'source_sha256':frozen,'source_unchanged':frozen=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*.py')}}
    (out/'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({'raw_mismatches':len(mismatches),'event_mismatches':len(event_mismatches),'frames_identical':result['frames_identical'],'source_unchanged':result['source_unchanged']}), flush=True)
    raise SystemExit(bool(event_mismatches) or not result['frames_identical'] or not result['source_unchanged'])
