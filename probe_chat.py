"""Real local engine and scrolling chat OCR replay; never user desktop data."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import argparse,json,hashlib,time,tempfile,re,subprocess,shutil
from pathlib import Path
from dataclasses import asdict
from unittest.mock import patch
from collections import Counter
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from babelander import __version__
from babelander.types import Mode,Region,Cancellation
from babelander.settings import Settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.controller import Controller
from babelander.window import MainWindow
from babelander.chat import split_message
from chat_fixtures import TEXTS,STYLES,prefix,chat_frame
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--name',default='chat-a19-discovery');parser.add_argument('--text-only',action='store_true');parser.add_argument('--limit',type=int,default=100)
parser.add_argument('--full-chat-ocr',action='store_true',help='A/B control: bypass session recognition reuse only')
parser.add_argument('--scan-ms',type=int,default=None,choices=(100,300,500,800),help='Temporary chat setting only; never writes saved settings')
args=parser.parse_args();dest=ROOT/'test-results'/args.name;dest.mkdir(parents=True,exist_ok=True)
APP=QApplication(['Chat replay background'])
APP.setStyle('Fusion');APP.setStyleSheet((ROOT/'babelander/theme.qss').read_text(encoding='utf8'))
for name in ('arial.ttf','msjh.ttc'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
report={'version':__version__,'real_cpu_ocr':True,'real_desktop_capture':False,'qt_platform':APP.platformName(),'paid_api':False,'foreground_control_calls':0,
        'scan_ms':800,'recognition_reuse':not args.full_chat_ocr,'styles':STYLES,'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')},
        'text_rows':[],'live_results':[],'ocr_traces':[],'changes':[],'errors':[],'semantic_accuracy_scored':False}
def save():(dest/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
def until(predicate,seconds=5):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:APP.processEvents();time.sleep(.005)
    APP.processEvents();return bool(predicate())
def normal(text):return re.sub(r'\s+','',text).casefold().replace('，',',').replace('。','.').replace('：',':').replace('？','?')
def stats(values):
    return {'n':len(values),'mean_ms':round(float(np.mean(values)),2),'p95_ms':round(float(np.percentile(values,95)),2),'max_ms':round(max(values),2)} if values else None
current={};shown={};session_caches=[];cache_patch_bytes=[]
with tempfile.TemporaryDirectory(prefix='Babelander-chat-test-') as d:
    root=Path(d);assets=ROOT.parent/'recovery/test-assets'
    settings=Settings(hotkeys={},model_path=str(next((assets/'models').glob('*.gguf'))),server_path=str(assets/'runtime/llama-server.exe'))
    if args.scan_ms is not None:settings.chat_scan_ms=args.scan_ms
    report['scan_ms']=settings.chat_scan_ms
    store=Store(root);vault=KeyVault(root);engine=Engine(settings,store,vault,root);controller=Controller(engine,store,settings);window=MainWindow(controller,store,settings,vault,root)
    backend=None;real_ocr=controller.ocr.recognize
    def capture(region):
        current['captures']=current.get('captures',0)+1;current['captured_index']=current['index']
        return current['frame'].copy()
    def recognize(frame,token,*a,**kw):
        cache=kw.get('chat_cache')
        if cache is not None and not any(cache is old for old in session_caches):session_caches.append(cache)
        if args.full_chat_ocr:kw.pop('chat_cache',None)
        index=current['captured_index'];at=time.perf_counter();lines=real_ocr(frame,token,*a,**kw)
        report['ocr_traces'].append({'index':index,'ocr_ms':round((time.perf_counter()-at)*1000,2),'reuse':dict(cache.last) if cache is not None else {},'lines':[asdict(l) for l in lines]})
        if cache is not None:cache_patch_bytes.append(sum(row[1].nbytes for row in cache.regions))
        current['ocr_done']=index;return lines
    def receive(mode):
        result=controller.take_result(mode)
        if result is None:return
        window.receive(result);now=time.perf_counter()
        for t in result.translations:
            match=re.search(r'P([0O1]\d{2})',t.source);index=int(match[1].replace('O','0'))-1 if match else None
            # Evaluation only: report a misread speaker separately. Never send
            # this correction, expected text or fixture IDs into the app.
            report['live_results'].append({**asdict(t),'event_id':result.event_id,'index':index,'observed_ms':round(result.total_ms,2),
                'fixture_shown_to_qt_ms':round((now-shown[index])*1000,2) if index in shown else None,
                'stages':dict(result.stages),'overlay_contains_target':bool(t.target and t.target in window.overlay(Mode.CHAT).toPlainText()) if hasattr(window.overlay(Mode.CHAT),'toPlainText') else bool(t.target and t.target in window.overlay(Mode.CHAT).text.toPlainText())})
    controller.delivery.disconnect(window.receive);controller.delivery.connect(receive)
    controller.failed.connect(lambda *row:report['errors'].append(list(row)))
    try:
        engine.prepare_local(Cancellation()).result(timeout=65);backend=engine.local.process
        gpu=subprocess.run([shutil.which('nvidia-smi') or 'C:/Windows/System32/nvidia-smi.exe','--query-compute-apps=pid','--format=csv,noheader'],capture_output=True,text=True,timeout=10)
        report['cuda_offload_confirmed']=gpu.returncode==0 and str(backend.pid) in {row.strip() for row in gpu.stdout.splitlines()}
        for index,text in enumerate(TEXTS[:args.limit]):
            at=time.perf_counter();t=engine.request(text,Mode.CHAT,Cancellation())
            report['text_rows'].append({'index':index,**asdict(t),'request_ms':round((time.perf_counter()-at)*1000,2)})
        save();print(json.dumps({'phase':'text','messages':len(report['text_rows']),'no_warning':sum(not r['warning'] for r in report['text_rows'])}),flush=True)
        if not args.text_only:
            warm=chat_frame([0]);real_ocr(warm[1],Cancellation());engine.volatile.clear()
            controller.ocr.recognize=recognize
            with patch('babelander.controller.capture',side_effect=capture):
                for index in range(args.limit):
                    start=index//20*20;indices=list(range(max(start,index-3),index+1));image,frame,rows=chat_frame(indices)
                    if index%20==0:
                        window.stop(Mode.CHAT)
                        assert until(lambda:not controller.live), 'old monitor did not stop'
                    shown[index]=time.perf_counter();current.update(index=index,frame=frame,ocr_done=None)
                    report['changes'].append({'index':index,'visible_messages':indices,'rows':rows,'frame_sha256':hashlib.sha256(frame.tobytes()).hexdigest()})
                    if index%20==0:
                        window.regions[Mode.CHAT]=Region(0,0,image.width(),image.height());window.toggle_monitor(Mode.CHAT)
                    assert until(lambda:current.get('ocr_done')==index),f'OCR timeout at {index}'
                    # Advance after production had a chance to dispatch. This
                    # is a paced replay; it is not a fixed-rate saturation test.
                    assert until(lambda:any(r['index']==index for r in report['live_results']),20),f'delivery timeout at {index}'
                    assert until(lambda:not controller.live or all(not d.snapshot()['pending'] and not d.snapshot()['in_flight'] for d in controller.live.values()),20),f'drain timeout at {index}'
                    if index%20==19 or index in (60,96,97):
                        image.save(str(dest/f'chat-{index+1:03d}-original.png'))
                        window.overlay(Mode.CHAT).grab().save(str(dest/f'chat-{index+1:03d}-translated.png'))
                    if index%10==9:
                        save();print(json.dumps({'phase':'live','index':index,'results':len(report['live_results']),'errors':len(report['errors'])}),flush=True)
                window.stop(Mode.CHAT);assert until(lambda:not controller.live)
                report['captures']=current.get('captures',0);report['metrics']=controller.metrics.snapshot()
        report['sqlite_rows']={table:store.db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('cache','history','usage')}
        report['volatile_entries']=len(engine.volatile)
        report['completed']=True
    except Exception as e:
        report['fatal_error']={'type':type(e).__name__,'message':str(e)}
        report['dispatcher_at_failure']=[d.snapshot() for d in controller.live.values()]
        report['engine_at_failure']={'pending':len(engine.pending),'active_calls':engine.active_local_calls}
        import sys,traceback
        report['thread_stacks']={str(key):[{'file':frame.filename,'line':frame.lineno,'function':frame.name} for frame in traceback.extract_stack(value)] for key,value in sys._current_frames().items()}
    finally:
        window.close();controller.close();controller.join();store.close();APP.processEvents()
        report['owned_model_stopped']=backend is None or backend.poll() is not None
        report['workers_stopped']=all(not t.is_alive() for queue in engine.queues.values() for t in queue.threads)
        report['recognition_sessions_cleared']=all(not c.entries and not c.regions and c.current_regions is None and c.scope is None for c in session_caches)
        report['recognition_patch_peak_mib']=round(max(cache_patch_bytes,default=0)/1048576,4)
        report['shared_ocr_context_cleared']=controller.ocr.engine is None or controller.ocr.engine.chat_context is None
report['text_summary']={'messages':len(report['text_rows']),'no_warning':sum(not r['warning'] for r in report['text_rows']),
    'warnings':sum(bool(r['warning']) for r in report['text_rows']),'request_latency':stats([r['request_ms'] for r in report['text_rows']]),'cache_hits':sum(r['cache_hit'] for r in report['text_rows'])}
matched=Counter(r['index'] for r in report['live_results'] if r['index'] is not None)
report['live_summary']={'results':len(report['live_results']),'missing_message_indices':[i for i in range(args.limit) if not matched[i]],
    'duplicated_message_indices':{i:count for i,count in matched.items() if count>1},'unattributed_results':sum(r['index'] is None for r in report['live_results']),
    'source_exact':sum(r['index'] is not None and normal(r['source'])==normal(prefix(r['index'])+' '+TEXTS[r['index']]) for r in report['live_results']),
    'no_warning':sum(not r['warning'] for r in report['live_results']),
    'fixture_shown_to_qt':stats([r['fixture_shown_to_qt_ms'] for r in report['live_results'] if r['fixture_shown_to_qt_ms'] is not None]),
    'observed_worker':stats([r['observed_ms'] for r in report['live_results']])}
report['source_unchanged']=all(hashlib.sha256((ROOT/'babelander'/name).read_bytes()).hexdigest()==sha for name,sha in report['source_sha256'].items())
save();print(json.dumps({k:report.get(k) for k in ('version','text_summary','live_summary','fatal_error','sqlite_rows','owned_model_stopped','workers_stopped','source_unchanged')},ensure_ascii=True),flush=True)
raise SystemExit(not report.get('completed') or not report['owned_model_stopped'] or not report['workers_stopped'])
