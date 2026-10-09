"""Bounded disk-frame replay, real OCR/Qwen/Qt, balanced 2/4-thread blocks.

No desktop capture, visible windows, hotkeys, changed user settings or cloud.
Frames are prepared before timing and streamed through one memory mapping.
"""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import argparse
from collections import OrderedDict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
import tempfile
import threading
import time
from unittest.mock import patch
import cv2
import numpy as np
import requests
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics, QImage, QPainter, QPainterPath, QColor, QPen
from PySide6.QtWidgets import QApplication
from rapidocr import RapidOCR
from babelander import __version__
from babelander.controller import Controller
from babelander.engine import Engine
from babelander.monitor import bright_signature
from babelander.pipeline import Telemetry
from babelander.security import KeyVault
from babelander.settings import Settings
from babelander.storage import Store
from babelander.types import Mode, Region, Cancellation
from babelander.window import MainWindow
from background_corpus_100 import CORPUS
from replay_analysis import summarize, aggregate, stats
from replay_resources import Sampler, process

ROOT=Path(__file__).resolve().parent
W,H,FPS,BANK_FRAMES=1450,250,20,16
APP=QApplication(['Babelander2 bounded replay'])
APP.setStyle('Fusion')
APP.setStyleSheet((ROOT/'babelander/theme.qss').read_text(encoding='utf-8'))
for name in ('arial.ttf','segoeui.ttf','msjh.ttc'):
    font_path=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name
    if font_path.is_file():QFontDatabase.addApplicationFont(str(font_path))
assert 'Arial' in QFontDatabase.families()
FONT=QFont('Arial',30);FM=QFontMetrics(FONT)


def log(row):print(json.dumps(row,ensure_ascii=True),flush=True)


def normalized(text):return ' '.join(text.split())


def text_parts(text,color='white',y=55):
    lines=[];line=''
    for word in text.split():
        new=(line+' '+word).strip()
        if line and FM.horizontalAdvance(new)>1390:lines.append(line);line=word
        else:line=new
    if line:lines.append(line)
    assert len(lines)<=4
    return [{'text':s,'x':24,'y':y+i*50,'color':color} for i,s in enumerate(lines)]


def background(step):
    yy,xx=np.mgrid[0:32,0:182].astype(np.float32)
    rng=np.random.default_rng(7127+step)
    wave=24*np.sin(xx*.12+step*.08)+18*np.cos(yy*.31-step*.05)
    grain=rng.normal(0,15,xx.shape)
    small=np.stack([72+wave+grain,53+wave*.8+grain,42-wave*.3+grain],axis=2)
    return cv2.resize(np.clip(small,0,170).astype(np.uint8),(W,H),interpolation=cv2.INTER_LINEAR)


def render(parts,step):
    frame=background(step)
    image=QImage(frame.data,W,H,W*3,QImage.Format.Format_BGR888)
    painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    for part in parts:
        path=QPainterPath();path.addText(part['x'],part['y'],FONT,part['text'])
        painter.setPen(QPen(QColor('black'),4));painter.setBrush(QColor('black'));painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(part['color']));painter.drawPath(path)
    painter.end()
    return frame


def holdouts():
    rows=[]
    def add(identifier,text,duration,parts,category):
        rows.append({'id':identifier,'text':text,'duration':duration,'parts':parts,'category':category})
    for index,(noun,kind) in enumerate([('copper','mixed_inline'),('silver','mixed_new_line')]):
        base=f'Open the {noun} gate'
        add(f'{kind}-base',base,1.6,text_parts(base),kind)
        suffix={'text':'before midnight.','color':'#9b9b9b','x':24+FM.horizontalAdvance(base)+20,'y':55}
        if kind=='mixed_new_line':suffix.update(x=24,y=105)
        add(f'{kind}-changed',base+' before midnight.',.6,text_parts(base)+[suffix],kind)
        add(f'{kind}-blank','',.6,[],kind)
    for identifier,a,b,category in [
        ('number','Carry 10 crystals.','Carry 18 crystals.','digit_change'),
        ('negative','You can enter the archive.','You cannot enter the archive.','negation_change'),
        ('short','Follow the northern trail.','Watch the cliff edge.','short_cue')]:
        add(identifier+'-base',a,1.6,text_parts(a),category)
        add(identifier+'-changed',b,.6,text_parts(b),category)
        add(identifier+'-blank','',.6,[],category)
    add('moved-base','Bring the bronze lantern.',1.6,text_parts('Bring the bronze lantern.'),'moved')
    add('moved-changed','Place it beside the ladder.',.6,text_parts('Place it beside the ladder.',y=155),'moved')
    add('moved-blank','',.6,[],'moved')
    return rows


class FrameBank:
    """Exactly one read-only mmap; OS file cache is not a claimed RSS limit."""
    def __init__(self,root):self.root=root;self.files={};self.mapping=None;self.identifier=None
    def prepare(self,rows):
        for index,row in enumerate(rows):
            path=self.root/(str(index)+'.npy')
            bank=np.lib.format.open_memmap(path,mode='w+',dtype=np.uint8,shape=(BANK_FRAMES,H,W,3))
            for step in range(BANK_FRAMES):bank[step]=render(row['parts'],step)
            bank.flush();del bank
            self.files[row['id']]=path
            if index%20==19:log({'precomputed_cues':index+1})
    def load(self,identifier):
        new=np.load(self.files[identifier],mmap_mode='r')
        # Read the first frame before publishing to isolate its file-read wait.
        first=new[0].copy()
        old=self.mapping;self.mapping=new;self.identifier=identifier
        return first,old
    def close(self):
        if self.mapping is not None:self.mapping._mmap.close();self.mapping=None


def save(path,report):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)


def run(args):
    assert Path(args.output).name==args.output
    out=ROOT/'test-results'/args.output;out.mkdir(parents=True,exist_ok=True)
    result_path=out/'results.json'
    assert Path(args.manifest).name==args.manifest
    frozen=json.loads((ROOT/'test-results'/args.manifest).read_text(encoding='utf-8-sig'))
    def unchanged():return all(hashlib.sha256((ROOT/'babelander'/n).read_bytes()).hexdigest()==v for n,v in frozen.items())
    assert unchanged(), 'Frozen application changed: create a new source manifest first'
    rows=[dict(r,id=str(r['id']),category=r['group'],duration=3.,parts=text_parts(r['text'])) for r in CORPUS]
    rng=random.Random(80371);rng.shuffle(rows)
    if args.limit:rows=rows[:args.limit]
    tests=holdouts() if not args.no_holdouts else []
    if args.holdouts_only:rows=[]
    report={'schema_version':1,'version':__version__,'completed':False,'application_source_sha256':frozen,
            'harness_source_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in
                                     ('probe_replay_threads.py','replay_analysis.py','replay_resources.py','verify_replay.py','background_corpus_100.py')},
            'scope':'Precomputed looping moving frames, real CPU OCR/CUDA Qwen/Qt offscreen. Synthetic capture replaces GDI. Not game FPS, compositor latency or semantic accuracy.',
            'config':{'adaptive_ocr_recheck':False,'reuse_dialogue_lines':False,'dialog_scan_ms':100,
                      'scan_ms':800,'stable_ms':100,'roi':[W,H],'fps':FPS,'bank_frames_per_cue':BANK_FRAMES,
                      'phase_order_rule':'alternating AB/BA by block, equal same-cue exposure; no simultaneous engines',
                      'qwen_max_tokens':320,'thinking':False,'prompt':'production v2-prompt-6','seed':80371},
            'cache_policy':'SQLite cleared per arm. Persistent single llama slot; identical three-request warmup per arm. Model prefix/KV cache not claimed empty; response usage/timings recorded when returned.',
            'fixture_memory_policy':'one 16-frame mmap plus one published frame, bounded capture metadata 64; native buffers/OS file cache/RSS not guaranteed by this',
            'corpus':rows,'holdout_corpus':tests,'phases':[],'system_load':[],
            'game_frametime':None,'semantic_correct_coverage':None}
    save(result_path,report)
    report['config']['mixed_text_trigger']=args.mixed_trigger
    if args.threads:report['config']['phase_order_rule']='single selected thread count, sequential blocks; no simultaneous engines'
    # Bank and settings directories are explicitly owned under the output root.
    with tempfile.TemporaryDirectory(prefix='frames-',dir=out) as bank_dir, tempfile.TemporaryDirectory(prefix='app-',dir=out) as app_dir:
        assert Path(bank_dir).resolve().is_relative_to(out.resolve())
        assert Path(app_dir).resolve().is_relative_to(out.resolve())
        bank=FrameBank(Path(bank_dir));bank.prepare(rows+tests)
        report['frame_bank_bytes']=sum(p.stat().st_size for p in bank.files.values())
        report['precomputed_fixture_sample_hashes']={r['id']:hashlib.sha256(render(r['parts'],0)).hexdigest() for r in rows+tests}
        if tests:
            report['mixed_bright_signature_preflight']={kind:bright_signature(render(tests[i]['parts'],0))==bright_signature(render(tests[i+1]['parts'],0))
                                                      for i,kind in ((0,'mixed_inline'),(3,'mixed_new_line'))}
            assert all(report['mixed_bright_signature_preflight'].values()), 'Mixed fixtures must really preserve bright hash'
        assets=ROOT/'test-results/asset-install/assets'
        settings=Settings(hotkeys={},ocr_threads=2,mixed_text_trigger=args.mixed_trigger,model_path=str(assets/'downloads/Qwen_Qwen3-1.7B-Q4_K_M.gguf'),
                          server_path=str(next(assets.glob('llama-b10896-*/llama-server.exe'))))
        settings.validate();store=Store(app_dir);vault=KeyVault(app_dir)
        engine=Engine(settings,store,vault,app_dir);controller=Controller(engine,store,settings)
        window=MainWindow(controller,store,settings,vault,app_dir)
        engine.acquire_client('bounded-replay-benchmark')
        mutex=threading.RLock();meta=OrderedDict();tls=threading.local()
        state={'phase':None,'frame':None,'cue':None,'started':0.}
        sampler=Sampler(report,state,lambda:engine.local.process.pid if engine.local.process else None)
        recognize=controller.ocr.recognize;http_post=requests.post;rapid_call=RapidOCR.__call__
        owned=None;producer_thread=None;producer_stop=threading.Event()

        def capture(region):
            with mutex:
                started=time.perf_counter();image=state['frame'].copy()
                row={'at':started-state['started'],'cue_id':state['cue']['id']}
                phase=state['phase'];phase['captures'].append(row);meta[id(image)]=row
                while len(meta)>64:meta.popitem(last=False)
                return image

        def rapid(self,*a,**kw):
            output=rapid_call(self,*a,**kw)
            tls.elapse_list=getattr(output,'elapse_list',None)
            return output

        def ocr(image,token,**kw):
            with mutex:
                phase=state['phase'];record=dict(meta.pop(id(image)))
            started=time.perf_counter();tls.elapse_list=None
            lines=recognize(image,token,**kw);ended=time.perf_counter()
            with mutex:
                phase['ocr'].append({**record,'text':normalized(' '.join(l.text for l in lines)),
                    'confidence':min((l.confidence for l in lines),default=0),'ms':(ended-started)*1000,
                    'started_at':started-state['started'],'completed_at':ended-state['started'],
                    'backend_det_cls_rec_seconds':tls.elapse_list})
            return lines

        def post(*a,**kw):
            started=time.perf_counter();response=http_post(*a,**kw);ended=time.perf_counter()
            payload=kw.get('json',{})
            if payload.get('messages'):
                packet=response.json()
                record={'at':started-state['started'],'request_ms':(ended-started)*1000,
                        'usage':packet.get('usage'),'backend_timings':packet.get('timings'),
                        'finish_reason':[c.get('finish_reason') for c in packet.get('choices',[])],
                        'prompt_sha256':hashlib.sha256(json.dumps(payload['messages'],ensure_ascii=False).encode()).hexdigest()}
                with mutex:
                    if state['phase'] is not None:state['phase']['backend'].append(record)
            return response

        def result(job):
            with mutex:
                if state['phase'] is not None:
                    state['phase']['results'].append({'at':time.perf_counter()-state['started'],
                        'event_id':job.event_id,'capture_epoch':job.capture_epoch,'generation':job.generation,
                        'observed_start':job.emitted_at-job.total_ms/1000-state['started'],
                        'stages':dict(job.stages),'translations':[asdict(t) for t in job.translations]})

        def ui(mode):
            if mode!=Mode.DIALOG.value:return
            with mutex:
                if state['phase'] is None:return
                page=window.pages[Mode.DIALOG]
                state['phase']['ui'].append({'at':time.perf_counter()-state['started'],
                    'visible_cue_id':state['cue']['id'],'visible_source':state['cue']['text'],
                    'source':normalized(page.source.toPlainText()),'target':page.target.toPlainText(),
                    'warning':page.ocr_note.text() if not page.ocr_note.isHidden() else ''})

        def failed(mode,message,generation):
            with mutex:
                if state['phase'] is not None:state['phase']['errors'].append({'message':message,'generation':generation})

        controller.ocr.recognize=ocr
        controller.result.connect(result,Qt.ConnectionType.DirectConnection)
        controller.delivery.connect(ui);controller.failed.connect(failed)

        def pump_until(predicate,timeout):
            deadline=time.perf_counter()+timeout
            while not predicate() and time.perf_counter()<deadline:APP.processEvents();time.sleep(.002)
            APP.processEvents()
            if not predicate():raise RuntimeError('Replay phase failed to stop within deadline')

        def warm(threads):
            settings.ocr_threads=threads
            warm_rows=rows or [row for row in tests if row['text']]
            for row in (warm_rows[0],warm_rows[len(warm_rows)//2],warm_rows[-1]):
                recognize(render(row['parts'],0),Cancellation())
            # Same final slot prefix/source before every measured arm.
            for text in ('Prepare the quiet laboratory.', 'The observer carries 3 notebooks.',
                         'Place the observation instruments beside the eastern window.'):
                store.clear_cache();engine.request(text,Mode.DIALOG,Cancellation())

        def phase_run(cues,threads,label):
            nonlocal producer_thread
            warm(threads);window.clear_workspace(Mode.DIALOG);APP.processEvents()
            store.clear_cache();controller.metrics=Telemetry();meta.clear()
            phase={'label':label,'threads':threads,'presentations':[],'captures':[],'ocr':[],
                   'ui':[],'results':[],'backend':[],'producer':[],'errors':[],'summary':{},
                   'process_cpu_start':time.process_time(),'resources_before':process(),
                   'model_resources_before':process(engine.local.process.pid)}
            report['phases'].append(phase)
            first,old=bank.load(cues[0]['id'])
            with mutex:
                state.update(phase=phase,frame=first,cue=cues[0],started=time.perf_counter())
                phase['presentations'].append({**{k:v for k,v in cues[0].items() if k!='parts'},'at':0.})
            if old is not None:old._mmap.close()
            producer_stop.clear()

            def produce():
                try:
                    for index,cue in enumerate(cues):
                        if index:
                            loading=time.perf_counter();first,old=bank.load(cue['id']);loaded=time.perf_counter()
                            with mutex:
                                actual=time.perf_counter();phase['presentations'][-1]['ended_at']=actual-state['started']
                                state.update(frame=first,cue=cue)
                                phase['presentations'].append({**{k:v for k,v in cue.items() if k!='parts'},'at':actual-state['started']})
                            if old is not None:old._mmap.close()
                            phase['producer'].append({'cue_id':cue['id'],'initial_io_wait_ms':(loaded-loading)*1000})
                        onset=time.perf_counter();deadline=onset+cue['duration'];frame_index=1
                        while not producer_stop.is_set():
                            desired=onset+frame_index/FPS
                            if desired>=deadline:break
                            if producer_stop.wait(max(0,desired-time.perf_counter())):break
                            reading=time.perf_counter();frame=bank.mapping[frame_index%BANK_FRAMES]
                            # Fault/read before taking the capture publication lock.
                            frame=frame.copy();ready=time.perf_counter()
                            with mutex:state['frame']=frame
                            phase['producer'].append({'cue_id':cue['id'],'frame_index':frame_index,
                                'deadline_miss_ms':max(0,(ready-desired)*1000),'frame_read_ms':(ready-reading)*1000})
                            frame_index+=1
                        if producer_stop.wait(max(0,deadline-time.perf_counter())):return
                    with mutex:phase['presentations'][-1]['ended_at']=time.perf_counter()-state['started']
                except Exception as error:
                    phase['errors'].append({'producer':type(error).__name__,'message':str(error)})
                finally:producer_stop.set()

            producer_thread=threading.Thread(target=produce,name='replay-disk-producer',daemon=True)
            with patch('babelander.controller.capture',side_effect=capture):
                window.regions[Mode.DIALOG]=Region(0,0,W,H);window.toggle_monitor(Mode.DIALOG)
                producer_thread.start();next_log=time.perf_counter()+10
                while not producer_stop.is_set():
                    APP.processEvents();time.sleep(.002)
                    if phase['errors']:producer_stop.set();break
                    if time.perf_counter()>=next_log:
                        log({'phase':label,'threads':threads,'cues':len(phase['presentations']),
                             'ocr':len(phase['ocr']),'elapsed_s':round(time.perf_counter()-state['started'],1)})
                        save(result_path,report);next_log=time.perf_counter()+10
                producer_thread.join(5)
                phase['capture_streams']=[s.snapshot() for s in controller.capture_streams.values()]
                window.stop(Mode.DIALOG)
                pump_until(lambda:not controller.live and not controller.capture_streams,10)
            phase['process_cpu_seconds']=time.process_time()-phase.pop('process_cpu_start')
            phase['resources_after']=process()
            phase['model_resources_after']=process(engine.local.process.pid)
            phase['monitor_drained']=not controller.live and not producer_thread.is_alive()
            phase['metrics']=controller.metrics.snapshot()
            if phase['errors'] or len(phase['presentations'])!=len(cues) or any('ended_at' not in c for c in phase['presentations']):
                raise RuntimeError('Incomplete replay phase: '+label)
            summarize(phase)
            phase['summary']['producer_deadline_miss']=stats([r['deadline_miss_ms'] for r in phase['producer'] if 'deadline_miss_ms' in r])
            with mutex:state['phase']=None;state['frame']=None
            bank.close();save(result_path,report)
            log({'phase_completed':label,'threads':threads,'summary':phase['summary']})

        try:
            sampler.start()
            with patch.object(RapidOCR,'__call__',rapid),patch('babelander.backends.requests.post',side_effect=post):
                for block,start in enumerate(range(0,len(rows),args.block_size)):
                    order=(args.threads,) if args.threads else ((2,4) if block%2==0 else (4,2))
                    for threads in order:phase_run(rows[start:start+args.block_size],threads,f'block-{block+1}-t{threads}')
                if tests:
                    for threads in ((args.threads,) if args.threads else (4,2)):phase_run(tests,threads,f'holdout-t{threads}')
            selected=(args.threads,) if args.threads else (2,4)
            report['summary']={str(t):aggregate([p for p in report['phases'] if p['threads']==t and p['label'].startswith('block-')]) for t in selected}
            report['holdout_summary']={str(t):aggregate([p for p in report['phases'] if p['threads']==t and p['label'].startswith('holdout-')]) for t in selected}
            report['completed']=True
        except Exception as error:
            report['fatal_error']={'type':type(error).__name__,'message':str(error)}
        finally:
            sampler.close()
            report['resource_sampler_stopped']=not sampler.thread.is_alive()
            producer_stop.set()
            if producer_thread is not None:producer_thread.join(5)
            owned=engine.local.process;engine.release_client('bounded-replay-benchmark')
            window.close();controller.join();store.close();APP.processEvents();bank.close()
            report['owned_model_stopped']=owned is not None and owned.poll() is not None
            report['workers_stopped']=not engine.release_worker.is_alive() and all(not t.is_alive() for q in engine.queues.values() for t in q.threads)
            report['source_unchanged']=unchanged()
            save(result_path,report)
        assert Path(bank_dir).resolve().is_relative_to(out.resolve())
        assert Path(app_dir).resolve().is_relative_to(out.resolve())
    report['temporary_frames_removed']=not Path(bank_dir).exists()
    save(result_path,report);log({k:report.get(k) for k in ('completed','summary','holdout_summary','fatal_error','owned_model_stopped','workers_stopped')})
    return not all(report.get(k) for k in ('completed','owned_model_stopped','workers_stopped','source_unchanged','temporary_frames_removed'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='replay-threads-a8')
    parser.add_argument('--limit',type=int,default=0)
    parser.add_argument('--block-size',type=int,default=20)
    parser.add_argument('--no-holdouts',action='store_true')
    parser.add_argument('--manifest',default='frozen-source-a8.json')
    parser.add_argument('--threads',type=int,choices=(2,4))
    parser.add_argument('--holdouts-only',action='store_true')
    parser.add_argument('--mixed-trigger',action='store_true')
    args=parser.parse_args()
    assert 0<=args.limit<=100 and 1<=args.block_size<=100
    assert not (args.holdouts_only and args.no_holdouts)
    raise SystemExit(run(args))
