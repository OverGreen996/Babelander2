"""Paired 100 x 3-second static/moving-noise monitor, offscreen only."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
from pathlib import Path
from bisect import bisect_left
from collections import OrderedDict
from dataclasses import asdict
import ctypes
from ctypes import wintypes
import hashlib
import argparse
import json
import math
import re
import statistics
import subprocess
import tempfile
import threading
import time
from unittest.mock import patch
import cv2
import numpy as np
from PySide6.QtCore import QRect,Qt
from PySide6.QtGui import QFont,QFontDatabase,QFontMetrics,QImage,QPainter,QPainterPath,QColor,QPen
from PySide6.QtWidgets import QApplication
from babelander import __version__
from babelander.controller import Controller
from babelander.engine import Engine
from babelander.settings import Settings
from babelander.security import KeyVault
from babelander.storage import Store
from babelander.types import Mode,Region,Cancellation
from babelander.pipeline import Telemetry
from babelander.monitor import dialogue_text_key
from babelander.window import MainWindow

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',default='moving-background-100')
parser.add_argument('--manifest',default='frozen-source-a4.json')
parser.add_argument('--moving-only',action='store_true')
parser.add_argument('--ocr-threads',type=int,choices=(1,2,3,4),default=2)
parser.add_argument('--adaptive-ocr-recheck',action='store_true')
parser.add_argument('--reuse-dialogue-lines',action='store_true')
parser.add_argument('--compare-line-reuse',action='store_true')
parser.add_argument('--ocr-only',action='store_true')
args=parser.parse_args()
assert Path(args.output).name==args.output and Path(args.manifest).name==args.manifest
OUT=ROOT/'test-results'/args.output
OUT.mkdir(exist_ok=True,parents=True)
from background_corpus_100 import CORPUS
previous=json.loads((ROOT/'test-results/english-100/corpus.json').read_text(encoding='utf-8'))
assert not ({r['text'].casefold() for r in CORPUS}&{r['text'].casefold() for r in previous})
(OUT/'corpus.json').write_text(json.dumps(CORPUS,ensure_ascii=False,indent=2),encoding='utf-8')
assert len(CORPUS)==100
def normalized(text):return re.sub(r'\s+',' ',text).strip()
LOOKUP={normalized(row['text']):row['id'] for row in CORPUS}
PERIOD_LOOKUP={dialogue_text_key(normalized(row['text'])):row['id'] for row in CORPUS}
assert len(PERIOD_LOOKUP)==len(CORPUS)
def stats(values):
    if not values:return None
    ordered=sorted(values)
    return {'n':len(values),'mean_ms':round(statistics.mean(values),2),'p50_ms':round(ordered[math.ceil(len(values)*.5)-1],2),
            'p95_ms':round(ordered[math.ceil(len(values)*.95)-1],2),'max_ms':round(ordered[-1],2)}

class Memory(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in
      ('peak_working','working','peak_pool','pool','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]
K=ctypes.windll.kernel32;PS=ctypes.windll.psapi
K.GetCurrentProcess.restype=wintypes.HANDLE
K.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
PS.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD]
K.GetProcessHandleCount.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
K.GetSystemTimes.argtypes=[ctypes.POINTER(wintypes.FILETIME)]*3
HANDLE=K.GetCurrentProcess()
def resources():
    m=Memory();m.cb=ctypes.sizeof(m);h=wintypes.DWORD();stamps=[wintypes.FILETIME() for _ in range(4)]
    if not PS.GetProcessMemoryInfo(HANDLE,ctypes.byref(m),m.cb):raise ctypes.WinError()
    if not K.GetProcessTimes(HANDLE,*[ctypes.byref(t) for t in stamps]):raise ctypes.WinError()
    K.GetProcessHandleCount(HANDLE,ctypes.byref(h))
    cpu=sum((t.dwHighDateTime<<32)+t.dwLowDateTime for t in stamps[2:])/10000000
    return {'working_mib':round(m.working/1048576,2),'private_mib':round(m.private/1048576,2),
            'cpu_seconds':round(cpu,3),'handles':h.value}

def system_cpu_stamps():
    stamps=[wintypes.FILETIME() for _ in range(3)]
    if not K.GetSystemTimes(*[ctypes.byref(t) for t in stamps]):raise ctypes.WinError()
    return [(t.dwHighDateTime<<32)+t.dwLowDateTime for t in stamps]

APP=QApplication(['Babelander2 moving-noise benchmark'])
for name in ('arial.ttf','segoeui.ttf','msjh.ttc'):
    path=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name
    if path.is_file():QFontDatabase.addApplicationFont(str(path))
assert 'Arial' in QFontDatabase.families()
APP.setStyle('Fusion');APP.setStyleSheet((ROOT/'babelander/theme.qss').read_text(encoding='utf-8'))
FONT=QFont('Arial',30);FM=QFontMetrics(FONT)
PATHS=[]
for row in CORPUS:
    words=row['text'].split();lines=[];line=''
    for word in words:
        candidate=(line+' '+word).strip()
        if FM.horizontalAdvance(candidate)>1390 and line:lines.append(line);line=word
        else:line=candidate
    if line:lines.append(line)
    assert len(lines)<=4
    path=QPainterPath()
    for i,line in enumerate(lines):path.addText(24,55+i*50,FONT,line)
    PATHS.append(path)
YY,XX=np.mgrid[0:32,0:182].astype(np.float32)
def render(case_index,step,color='white',dy=0):
    # Identical seed, noise spectrum and typography; only time varies between
    # static and moving. No opaque band protects the text from the background.
    rng=np.random.default_rng(7127+step)
    wave=24*np.sin(XX*.12+step*.08)+18*np.cos(YY*.31-step*.05)
    grain=rng.normal(0,15,XX.shape)
    small=np.stack([72+wave+grain,53+wave*.8+grain,42-wave*.3+grain],axis=2)
    background=cv2.resize(np.clip(small,0,170).astype(np.uint8),(1450,250),interpolation=cv2.INTER_LINEAR)
    image=QImage(background.data,1450,250,1450*3,QImage.Format.Format_BGR888)
    painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(0,dy)
    painter.setPen(QPen(QColor('black'),4));painter.setBrush(QColor('black'));painter.drawPath(PATHS[case_index])
    # Fill after the outline: Qt's centered stroke otherwise obscures the
    # interiors of narrow Arial glyphs, silently creating black subtitles.
    painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(color));painter.drawPath(PATHS[case_index]);painter.end()
    return background

preview=render(0,0)
assert np.count_nonzero(preview.min(axis=2)>230)>1000, 'Subtitle fill is not visibly white'
QImage(preview.data,1450,250,4350,QImage.Format.Format_BGR888).save(str(OUT/'fixture-preflight.png'))

frozen=json.loads((ROOT/'test-results'/args.manifest).read_text(encoding='utf-8-sig'))
assert all(hashlib.sha256((ROOT/'babelander'/n).read_bytes()).hexdigest()==digest for n,digest in frozen.items())
if args.ocr_only:
    from babelander.ocr import OCR
    from babelander.subtitle_layout import SubtitleLayout
    from babelander.monitor import dialogue_text_key
    ocr=OCR(lambda:Settings(ocr_threads=args.ocr_threads));token=Cancellation();layout=SubtitleLayout()
    previous_frame=render(0,0);previous_lines=ocr.recognize(previous_frame,token)
    rows=[]
    for index,case in enumerate(CORPUS):
        image=render(index,index*60)
        layout.learn(previous_frame,previous_lines)
        def run(reuse):
            started=time.perf_counter()
            lines=ocr.recognize(image,token,layout=layout if reuse else None)
            return lines,(time.perf_counter()-started)*1000
        # Alternate order rather than always giving the second path warm caches.
        if index%2:fast,fast_ms=run(True);full,full_ms=run(False)
        else:full,full_ms=run(False);fast,fast_ms=run(True)
        full_text=normalized(' '.join(l.text for l in full));fast_text=normalized(' '.join(l.text for l in fast))
        rows.append({'case_id':case['id'],'source':case['text'],'full_text':full_text,'fast_text':fast_text,
                     'full_ms':full_ms,'fast_ms':fast_ms,'fast_path':layout.last_path,'reason':layout.last_reason,
                     'full_exact':full_text==case['text'],'fast_exact':fast_text==case['text'],
                     'full_period_tolerant':dialogue_text_key(full_text)==dialogue_text_key(case['text']),
                     'fast_period_tolerant':dialogue_text_key(fast_text)==dialogue_text_key(case['text'])})
        previous_frame,previous_lines=image,full
        if index%20==19:print(json.dumps({'ocr_only_cases':index+1}),flush=True)
    adversarial=[]
    seed=render(0,0);seed_lines=ocr.recognize(seed,token)
    for name,options in [('yellow',{'color':'yellow'}),('dim_gray',{'color':'#a0a0a0'}),('moved',{'dy':100}),('white',{})]:
        layout.learn(seed,seed_lines);image=render(0,1,**options)
        full=ocr.recognize(image,token);fast=ocr.recognize(image,token,layout=layout)
        adversarial.append({'fixture':name,'full_text':normalized(' '.join(l.text for l in full)),
                            'fast_text':normalized(' '.join(l.text for l in fast)),
                            'path':layout.last_path,'reason':layout.last_reason})
    result={'version':__version__,'application_source_sha256':frozen,'threads':args.ocr_threads,
            'scope':'100 single rendered frames, alternate full/reuse order, hint learned from previous full frame. Real CPU OCR only; not full translation latency or runtime recall.',
            'rows':rows,'adversarial':adversarial,'summary':{'full_latency':stats([r['full_ms'] for r in rows]),
            'reuse_latency':stats([r['fast_ms'] for r in rows]),'full_exact':sum(r['full_exact'] for r in rows),
            'reuse_exact':sum(r['fast_exact'] for r in rows),'full_period_tolerant':sum(r['full_period_tolerant'] for r in rows),
            'reuse_period_tolerant':sum(r['fast_period_tolerant'] for r in rows),
            'reused':sum(r['fast_path']=='line_reuse' for r in rows)},
            'source_unchanged':all(hashlib.sha256((ROOT/'babelander'/n).read_bytes()).hexdigest()==digest for n,digest in frozen.items())}
    (OUT/'ocr-only.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result['summary']));raise SystemExit(not result['source_unchanged'])
report={'version':__version__,'corpus':CORPUS,'duration_per_sentence_seconds':3,'sentences_per_phase':100,
        'scan_ms':Settings().scan_ms,'dialog_scan_ms':getattr(Settings(),'dialog_scan_ms',Settings().scan_ms),
        'stable_ms':Settings().stable_ms,'profile':'fast','font':'Arial 30 pt, white glyphs with 4 px black outline',
        'ocr_threads':args.ocr_threads,
        'adaptive_ocr_recheck':args.adaptive_ocr_recheck,
        'reuse_dialogue_lines':args.reuse_dialogue_lines,'compare_line_reuse':args.compare_line_reuse,
        'roi':[1450,250],'animation_fps_target':20,'noise_seed':7127,'noise_std':15,'opaque_text_backplate':False,
        'qt_platform':APP.platformName(),'real_desktop_capture':False,'cloud_requests':0,'phases':{},'completed':False,
        'scope':'Static and moving versions of the same synthetic noisy scene, each 100 sentences x 3 s. Production monitor and real CPU OCR/CUDA/Qt. Measured fixture appearance to UI, including default polling and stability. No GDI capture/compositor/game FPS claim; app CPU includes fixture rendering.',
        'application_source_sha256':frozen}
report['system_load_samples']=[]
load_stop=threading.Event()
def sample_system_load():
    before=system_cpu_stamps()
    while not load_stop.wait(15):
        after=system_cpu_stamps();delta=[a-b for a,b in zip(after,before)];before=after
        total=delta[1]+delta[2]
        row={'at_perf_counter':time.perf_counter(),'cpu_interval_seconds':15,
             'whole_system_cpu_percent':round(100*(total-delta[0])/total,2) if total else None}
        try:
            query=subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,memory.used,clocks.sm','--format=csv,noheader,nounits'],
                                 capture_output=True,text=True,timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
            values=query.stdout.strip().splitlines()[0].split(',')
            row.update(gpu_instant_percent=float(values[0]),gpu_total_memory_mib=float(values[1]),gpu_clock_mhz=float(values[2]))
        except Exception as error:row['gpu_sample_error']=type(error).__name__
        report['system_load_samples'].append(row)
load_sampler=threading.Thread(target=sample_system_load,name='Babelander2-benchmark-system-load',daemon=True)
def save():
    (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
def log(data):print(json.dumps(data,ensure_ascii=False),flush=True)

with tempfile.TemporaryDirectory(prefix='Babelander2-moving-noise-') as directory:
    settings=Settings(hotkeys={},ocr_threads=args.ocr_threads,adaptive_ocr_recheck=args.adaptive_ocr_recheck,reuse_dialogue_lines=args.reuse_dialogue_lines,model_path=str(ROOT/'test-results/asset-install/assets/downloads/Qwen_Qwen3-1.7B-Q4_K_M.gguf'),
        server_path=str(next((ROOT/'test-results/asset-install/assets').glob('llama-b10896-*/llama-server.exe'))))
    store=Store(directory);vault=KeyVault(directory);engine=Engine(settings,store,vault,directory)
    controller=Controller(engine,store,settings);window=MainWindow(controller,store,settings,vault,directory)
    engine.acquire_client('paired-background-benchmark')
    mutex=threading.RLock();state={'phase':None,'frame':None,'case_id':None,'started':0,'capture':None,'capture_meta':OrderedDict()}
    phase=None;owned=None
    recognize=controller.ocr.recognize
    def capture(region):
        with mutex:
            at=time.perf_counter();frame=state['frame'].copy()
            row={'at':at-state['started'],'case_id':state['case_id'],'frame_sha256':hashlib.sha256(frame).hexdigest()}
            state['capture']=row;state['phase']['captures'].append(row)
            state['capture_meta'][id(frame)]=row
            while len(state['capture_meta'])>64:state['capture_meta'].popitem(last=False)
            return frame
    def ocr(frame,token,layout=None,layout_key=None):
        # With independent capture, the most recent capture can be newer than
        # the OCR input. Bind metadata to that exact image, never global latest.
        with mutex:meta=dict(state['capture_meta'].pop(id(frame)))
        at=time.perf_counter();lines=recognize(frame,token,layout=layout,layout_key=layout_key);ended=time.perf_counter();elapsed=(ended-at)*1000
        text=normalized(' '.join(line.text for line in lines))
        row={**meta,'ms':elapsed,'text':text,'exact':text==CORPUS[meta['case_id']-1]['text'],
             'confidence':min((line.confidence for line in lines),default=0)}
        if layout is not None:row.update(path=layout.last_path,reason=layout.last_reason)
        with mutex:
            row.update(ocr_started_at=at-state['started'],ocr_completed_at=ended-state['started'],
                       captured_to_ocr_start_ms=(at-state['started']-meta['at'])*1000)
            state['phase']['ocr'].append(row)
        return lines
    controller.ocr.recognize=ocr
    def producer(result):
        with mutex:
            if state['phase'] is None:return
            state['phase']['results'].append({'at':time.perf_counter()-state['started'],'event_id':result.event_id,
                'observed_start':result.emitted_at-result.total_ms/1000-state['started'],
                'stages':dict(result.stages),'translations':[asdict(t) for t in result.translations]})
    controller.result.connect(producer,Qt.ConnectionType.DirectConnection)
    def ui(mode):
        with mutex:
            if state['phase'] is None:return
            page=window.pages[Mode.DIALOG]
            source=normalized(page.source.toPlainText());target=page.target.toPlainText()
            state['phase']['ui'].append({'at':time.perf_counter()-state['started'],'visible_case_id':state['case_id'],
                'source_case_id':LOOKUP.get(source),'source':source,'target':target,
                'period_source_case_id':PERIOD_LOOKUP.get(dialogue_text_key(source)),
                'event_id':controller.revisions[Mode.DIALOG],
                'warning':page.ocr_note.text() if not page.ocr_note.isHidden() else ''})
    controller.delivery.connect(ui)
    controller.failed.connect(lambda mode,message,generation:state['phase']['errors'].append({'message':message,'generation':generation}) if state['phase'] else None)
    try:
        # Cold initialization is outside both timed monitor phases.
        recognize(render(0,0),Cancellation())
        engine.request('Prepare the observation instruments beside the quiet laboratory.',Mode.DIALOG,Cancellation())
        report['owned_model_pid']=engine.local.process.pid
        load_sampler.start()
        save()
        phases=('moving_control','moving_line_reuse') if args.compare_line_reuse else (('moving_noise',) if args.moving_only else ('static_noise','moving_noise'))
        for name in phases:
            settings.reuse_dialogue_lines=name=='moving_line_reuse' if args.compare_line_reuse else args.reuse_dialogue_lines
            moving=name.startswith('moving_')
            window.clear_workspace(Mode.DIALOG);APP.processEvents();store.clear_cache();controller.metrics=Telemetry()
            phase={'name':name,'reuse_dialogue_lines':settings.reuse_dialogue_lines,'presentations':[],'captures':[],'ocr':[],'results':[],'ui':[],'resources':[],
                   'errors':[],'render_frames':0,'render_ms':0,'summary':{}}
            report['phases'][name]=phase
            frame=render(0,0);started=time.perf_counter();initial_cpu=resources()['cpu_seconds']
            with mutex:state.update(phase=phase,frame=frame,case_id=1,started=started,capture=None)
            phase['presentations'].append({'case_id':1,'at':0.0})
            QImage(frame.data,1450,250,4350,QImage.Format.Format_BGR888).save(str(OUT/f'{name}-case-1.png'))
            next_frame=0;next_sample=0;next_log=0;last_index=0
            with patch('babelander.controller.capture',side_effect=capture):
                window.regions[Mode.DIALOG]=Region(0,0,1450,250);window.toggle_monitor(Mode.DIALOG)
                while time.perf_counter()-started<300:
                    elapsed=time.perf_counter()-started;index=min(99,int(elapsed/3))
                    if index!=last_index or (moving and elapsed>=next_frame):
                        at=time.perf_counter();frame=render(index,int(elapsed*20) if moving else 0)
                        phase['render_ms']+=(time.perf_counter()-at)*1000;phase['render_frames']+=1
                        with mutex:
                            state['frame']=frame;state['case_id']=index+1
                            if index!=last_index:phase['presentations'].append({'case_id':index+1,'at':time.perf_counter()-started})
                        if index in (0,49,99) and index!=last_index:
                            QImage(frame.data,1450,250,4350,QImage.Format.Format_BGR888).save(str(OUT/f'{name}-case-{index+1}.png'))
                        last_index=index;next_frame=elapsed+.05
                    if elapsed>=next_sample:
                        phase['resources'].append({'at':elapsed,**resources()});next_sample=elapsed+30
                    if elapsed>=next_log:
                        log({'phase':name,'elapsed':round(elapsed,1),'sentences_presented':len(phase['presentations']),
                             'ocr_calls':len(phase['ocr']),'nonempty_ui_results':sum(bool(r['target']) for r in phase['ui'])})
                        next_log=elapsed+30;save()
                    APP.processEvents();time.sleep(.003)
                    if phase['errors']:break
                phase['text_end_at']=time.perf_counter()-started
                phase['capture_streams']=[stream.snapshot() for stream in controller.capture_streams.values()]
                window.stop(Mode.DIALOG)
                # Drain cancelled monitor and queued notifications before reusing
                # this warmed engine for the second independent session.
                deadline=time.monotonic()+10
                while controller.live and time.monotonic()<deadline:APP.processEvents();time.sleep(.01)
                APP.processEvents()
            phase['monitor_drained']=not bool(controller.live)
            if phase['errors'] or len(phase['presentations'])!=100 or not phase['monitor_drained']:
                raise RuntimeError('Incomplete phase: '+name)
            phase['metrics']=controller.metrics.snapshot()
            phase['cpu_seconds']=round(resources()['cpu_seconds']-initial_cpu,3)
            # Link observations to their known synthetic sentence onset.
            onsets={r['case_id']:r['at'] for r in phase['presentations']}
            captures=phase['captures'];times=[r['at'] for r in captures]
            outcomes=[]
            for case in CORPUS:
                case_id=case['id'];observations=[r for r in phase['ocr'] if r['case_id']==case_id]
                exact=[r for r in observations if r['exact']]
                display=[r for r in phase['ui'] if r['source_case_id']==case_id and r['target'] and not r['warning']]
                period_display=[r for r in phase['ui'] if r['period_source_case_id']==case_id and r['target'] and not r['warning']]
                warnings=[r for r in phase['ui'] if r['source_case_id']==case_id and r['warning']]
                outcomes.append({'case_id':case_id,'introduced_at':onsets.get(case_id),'ocr_calls':len(observations),
                    'exact_ocr_seen':bool(exact),'any_ocr_seen':bool(observations),'usable_display':bool(display),
                    'usable_display_within_3_seconds':any(r['at']-onsets[case_id]<3 for r in display),
                    'display_latency_ms':(display[0]['at']-onsets[case_id])*1000 if display else None,
                    'period_tolerant_display_latency_ms':(period_display[0]['at']-onsets[case_id])*1000 if period_display else None,
                    'first_exact_ocr_latency_ms':(exact[0]['ocr_completed_at']-onsets[case_id])*1000 if exact else None,
                    'display_count':len(display),'warning_count':len(warnings)})
            for result in phase['results']:
                idx=min(len(captures)-1,bisect_left(times,result['observed_start']))
                if captures:result['observed_case_id']=captures[idx]['case_id']
            phase['outcomes']=outcomes
            durations=[phase['presentations'][i+1]['at']-r['at'] for i,r in enumerate(phase['presentations'][:-1])]
            if phase['presentations']:durations.append(phase['text_end_at']-phase['presentations'][-1]['at'])
            translated=[t for r in phase['results'] for t in r['translations']]
            phase['summary']={'sentences_presented':len(onsets),'exact_ocr_seen':sum(r['exact_ocr_seen'] for r in outcomes),
                'not_observed_by_ocr':sum(not r['any_ocr_seen'] for r in outcomes),
                'never_exact_ocr':sum(not r['exact_ocr_seen'] for r in outcomes),
                'usable_display':sum(r['usable_display'] for r in outcomes),
                'usable_display_within_3_seconds':sum(r['usable_display_within_3_seconds'] for r in outcomes),
                'usable_display_within_700_ms':sum(r['display_latency_ms'] is not None and r['display_latency_ms']<=700 for r in outcomes),
                'display_latency':stats([r['display_latency_ms'] for r in outcomes if r['display_latency_ms'] is not None]),
                'period_tolerant_display_latency':stats([r['period_tolerant_display_latency_ms'] for r in outcomes if r['period_tolerant_display_latency_ms'] is not None]),
                'period_tolerant_display_within_700_ms':sum(r['period_tolerant_display_latency_ms'] is not None and r['period_tolerant_display_latency_ms']<=700 for r in outcomes),
                'first_exact_ocr_latency':stats([r['first_exact_ocr_latency_ms'] for r in outcomes if r['first_exact_ocr_latency_ms'] is not None]),
                'ocr_call_latency':stats([r['ms'] for r in phase['ocr']]),'ocr_calls':len(phase['ocr']),
                'ocr_exact_call_count':sum(r['exact'] for r in phase['ocr']),
                'captures':len(captures),'ocr_wall_work_ms':round(sum(r['ms'] for r in phase['ocr']),2),
                'duplicate_display_results':sum(max(0,r['display_count']-1) for r in outcomes),
                'nonexact_source_display_results':sum(bool(r['source'] and r['target'] and not r['source_case_id']) for r in phase['ui']),
                'display_after_sentence_changed':sum(bool(r['target'] and r['source_case_id'] and r['source_case_id']!=r['visible_case_id']) for r in phase['ui']),
                'backend_requests':sum(t['backend_state'] in ('cold','warm') for t in translated),
                'cache_hits':sum(t['cache_hit'] for t in translated),'guard_rejections':sum(bool(t['warning']) for t in translated),
                'cpu_seconds_including_fixture':phase['cpu_seconds'],
                'sentence_duration_min_s':round(min(durations),3),'sentence_duration_max_s':round(max(durations),3),
                'render_frames':phase['render_frames'],'render_wall_ms':round(phase['render_ms'],2)}
            with mutex:state['phase']=None
            log({'phase_completed':name,'summary':phase['summary']});save()
        report['completed']=True
    except Exception as error:
        report['fatal_error']={'type':type(error).__name__,'message':str(error)}
    finally:
        load_stop.set()
        if load_sampler.ident is not None:load_sampler.join(6)
        owned=engine.local.process;engine.release_client('paired-background-benchmark')
        window.close();controller.join();store.close();APP.processEvents()
        report['owned_model_stopped']=owned is not None and owned.poll() is not None
        report['workers_stopped']=not engine.release_worker.is_alive() and all(not t.is_alive() for q in engine.queues.values() for t in q.threads)
        report['source_unchanged']=all(hashlib.sha256((ROOT/'babelander'/n).read_bytes()).hexdigest()==digest for n,digest in frozen.items())
        save()
log({'completed':report['completed'],'owned_model_stopped':report['owned_model_stopped'],'workers_stopped':report['workers_stopped']})
raise SystemExit(not(report['completed'] and report['owned_model_stopped'] and report['workers_stopped'] and report['source_unchanged']))
