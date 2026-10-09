"""All production modes together, real OCR/Qt/Qwen, owned fault injection only."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import argparse,json,time,tempfile,hashlib,re,subprocess,shutil
from pathlib import Path
from dataclasses import asdict
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QFont,QColor,QFontDatabase
from babelander import __version__
from babelander.types import Mode,Region,Cancellation
from babelander.settings import Settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.controller import Controller
from babelander.window import MainWindow
from babelander.backends import BackendError
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--out',default='test-results/supertest-a'+__version__.split('a')[-1]+'/modes')
args=parser.parse_args();DEST=ROOT/args.out;DEST.mkdir(parents=True,exist_ok=True)
APP=QApplication(['All modes background verification']);APP.setStyle('Fusion');APP.setStyleSheet((ROOT/'babelander/theme.qss').read_text(encoding='utf8'))
for name in ('arial.ttf','msjh.ttc'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
def until(predicate,seconds=12):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:APP.processEvents();time.sleep(.005)
    APP.processEvents();return bool(predicate())
def render(rows,size):
    image=QImage(*size,QImage.Format.Format_BGR888);image.fill(QColor('#17212b'))
    painter=QPainter(image);painter.setPen(QColor('#937649'));painter.drawRect(3,3,size[0]-7,size[1]-7)
    font=QFont('Microsoft JhengHei UI');font.setPixelSize(26);painter.setFont(font)
    for i,text in enumerate(rows):painter.setPen(QColor('#efce95' if i==0 else '#edf1f7'));painter.drawText(22,48+i*48,text)
    painter.end()
    return image,np.frombuffer(image.bits(),np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*3].reshape(image.height(),image.width(),3).copy()
CASES={Mode.DIALOG: (['Do not cross the river yet.'],(1000,170)),
       Mode.CHAT: (['[Party] Rin: I need potions X6.','[Party] Kai: GG','[Party] Jo: Do not start the raid yet.'],(1080,240)),
       Mode.EQUIPMENT: (['Rare Shield','Gain +18% Fire Resistance for 7 seconds.'],(760,280)),
       Mode.QUEST: (['Objectives','Collect 5 crystals.','0 / 5'],(720,250)),
       Mode.SCREEN: (['System Update','Restart in 6 minutes.','Do not close this window.'],(900,270))}
frames={};regions={}
for mode,(rows,size) in CASES.items():
    image,frame=render(rows,size);image.save(str(DEST/(mode.value+'-original.png')))
    frames[mode]=frame;regions[mode]=Region(0,0,*size)
report={'version':__version__,'application_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')},
        'foreground_control_calls':0,'real_desktop_capture':False,'qt_platform':APP.platformName(),'real_cpu_ocr':True,'real_local_model':True,
        'results':[],'checks':{},'errors':[],'quality_cases':[],'scope':'Synthetic all-mode integration and deliberate failure of the owned model only; no real game/FPS claim.'}
def save():(DEST/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
with tempfile.TemporaryDirectory(prefix='Babelander-super-modes-') as directory:
    assets=ROOT.parent/'recovery/test-assets';settings=Settings(hotkeys={},model_path=str(next((assets/'models').glob('*.gguf'))),server_path=str(assets/'runtime/llama-server.exe'))
    store=Store(directory);vault=KeyVault(directory);engine=Engine(settings,store,vault,directory);controller=Controller(engine,store,settings);window=MainWindow(controller,store,settings,vault,directory)
    owned=[];phase='sequential';received=[];capture_calls={m:0 for m in CASES}
    def capture(region):
        mode=next(m for m,r in regions.items() if r==region);capture_calls[mode]+=1;return frames[mode].copy()
    def receive(mode):
        result=controller.take_result(mode)
        if result is None:return
        window.receive(result);received.append((phase,result))
        report['results'].append({'phase':phase,'mode':result.mode.value,'generation':result.generation,'event_id':result.event_id,'worker_ms':result.total_ms,'translations':[asdict(t) for t in result.translations]})
    controller.delivery.disconnect(window.receive);controller.delivery.connect(receive)
    controller.failed.connect(lambda *values:report['errors'].append({'phase':phase,'mode':values[0],'message':values[1]}))
    try:
        engine.acquire_client('supertest');engine.prepare_local(Cancellation()).result(timeout=65);owned.append(engine.local.process)
        query=subprocess.run([shutil.which('nvidia-smi') or 'nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],capture_output=True,text=True,timeout=8,creationflags=subprocess.CREATE_NO_WINDOW)
        report['cuda_offload_confirmed']=query.returncode==0 and str(owned[0].pid) in {s.strip() for s in query.stdout.splitlines()}
        with patch('babelander.controller.capture',side_effect=capture):
            for mode in Mode:
                before=len(received)
                if mode==Mode.REPLY:controller.submit_text(mode,'我需要6瓶藥水，請等我。')
                else:
                    window.regions[mode]=regions[mode]
                    if mode in (Mode.DIALOG,Mode.CHAT):window.toggle_monitor(mode)
                    else:controller.submit_region(mode,regions[mode])
                expected=3 if mode==Mode.CHAT else 1
                assert until(lambda:sum(len(r.translations) for p,r in received[before:] if r.mode==mode)>=expected),mode.value+' delivery timeout'
                translations=[t for p,r in received[before:] if r.mode==mode for t in r.translations]
                report['checks']['sequential_'+mode.value]=bool(translations) and all(t.target and not t.warning for t in translations)
                if mode!=Mode.REPLY:window.overlay(mode).grab().save(str(DEST/(mode.value+'-translated.png')))
                if mode in (Mode.EQUIPMENT,Mode.QUEST):
                    report['checks'][mode.value+'_single_capture']=capture_calls[mode]==1
                    widget=window.overlay(mode)
                    report['checks'][mode.value+'_original_roi']=[widget.width(),widget.height()]==[regions[mode].width,regions[mode].height]
                window.stop(mode);assert until(lambda:not controller.working(mode)),mode.value+' stop timeout'
            # All six share the production CPU OCR lock and one model queue.
            phase='concurrent';before=len(received)
            for mode in (Mode.DIALOG,Mode.CHAT):window.toggle_monitor(mode)
            for mode in (Mode.EQUIPMENT,Mode.QUEST,Mode.SCREEN):controller.submit_region(mode,regions[mode])
            controller.submit_text(Mode.REPLY,'我需要6瓶藥水，請等我。')
            assert until(lambda:{r.mode for p,r in received[before:]}==set(Mode),25),'concurrent modes timeout'
            for mode in Mode:
                rows=[t for p,r in received[before:] if r.mode==mode for t in r.translations]
                report['checks']['concurrent_'+mode.value]=bool(rows) and all(t.target and not t.warning for t in rows)
            report['checks']['concurrent_reused_one_model']=engine.local.process is owned[0] and owned[0].poll() is None
            for mode in Mode:window.stop(mode)
            assert until(lambda:not controller.live and not controller.capture_streams and not any(controller.working(m) for m in Mode)),'concurrent work did not stop'
            report['checks']['stop_removed_capture_and_dispatch']=not controller.live and not controller.capture_streams
            report['checks']['stopped_overlays_hidden']=all(not widget.isVisible() for widget in window.overlays.values())
        # Kill only this test's model child while an actual HTTP request starts.
        import threading
        entered=threading.Event();original_post=__import__('requests').post
        def post(*a,**kw):entered.set();return original_post(*a,**kw)
        phase='fault_injection';store.clear_cache()
        with ThreadPoolExecutor(max_workers=1) as pool,patch('babelander.backends.requests.post',side_effect=post):
            future=pool.submit(engine.request,'The southern bridge is damaged. '+('The guards are waiting by the river. '*10),Mode.SCREEN,Cancellation())
            assert entered.wait(8),'no real HTTP request observed'
            owned[0].terminate();owned[0].wait(5)
            try:future.result(timeout=35);report['checks']['owned_inflight_failure_reported']=False
            except BackendError:report['checks']['owned_inflight_failure_reported']=True
        assert until(lambda:not engine.pending and engine.active_local_calls==0),'failed request did not retire'
        report['checks']['failure_did_not_deadlock']=not engine.pending and engine.active_local_calls==0
        recovered=engine.request('The northern wall is damaged.',Mode.SCREEN,Cancellation());owned.append(engine.local.process)
        report['checks']['request_after_crash_recovered']=bool(recovered.target) and not recovered.warning and engine.local.process is not owned[0]
        report['privacy']={'chat_reply_history_rows':store.db.execute("SELECT COUNT(*) FROM history WHERE mode IN ('chat','reply')").fetchone()[0],
                           'chat_reply_cache_rows':sum(json.loads(value)['source'] in {'I need potions X6.','GG','Do not start the raid yet.','我需要6瓶藥水，請等我。'} for (value,) in store.db.execute('SELECT value FROM cache').fetchall()),
                           'volatile_entries':len(engine.volatile)}
        report['checks']['private_history_empty']=report['privacy']['chat_reply_history_rows']==0
        report['checks']['private_cache_empty']=report['privacy']['chat_reply_cache_rows']==0
        report['checks']['volatile_cache_bounded']=len(engine.volatile)<=128
        # Quality checks are not lifecycle checks. Retain failed outputs rather
        # than certifying semantics from the presence of Chinese.
        semantic=[('Party full?',r'隊伍'),('Save one potion for me.',r'留'),('Focus the healer first.',r'先|優先'),
                  ('Do not open the gate yet.',r'不|勿|別'),('Can we pause for 2 minutes?',r'2|兩|二'),
                  ('I need potions X5.',r'5'),('I need potions X6.',r'6'),('GG',r'^GG$')]
        for source,required in semantic:
            t=engine.request(source,Mode.CHAT,Cancellation())
            report['quality_cases'].append({**asdict(t),'required_marker':required,'critical_marker_passed':bool(t.target and not t.warning and re.search(required,t.target))})
        report['quality_marker_passed']=all(row['critical_marker_passed'] for row in report['quality_cases'])
        report['metrics']=controller.metrics.snapshot();report['completed']=True
    except Exception as error:report['fatal_error']={'type':type(error).__name__,'message':str(error)}
    finally:
        window.close();controller.close();controller.join();store.close();APP.processEvents()
        report['checks']['owned_models_stopped']=all(process.poll() is not None for process in owned)
        report['checks']['workers_stopped']=all(not t.is_alive() for q in engine.queues.values() for t in q.threads)
        report['checks']['resource_release_worker_stopped']=not engine.release_worker.is_alive()
report['source_unchanged']=all(hashlib.sha256((ROOT/'babelander'/name).read_bytes()).hexdigest()==value for name,value in report['application_sha256'].items())
report['functional_passed']=bool(report.get('completed')) and all(report['checks'].values()) and not report['errors'] and report['source_unchanged']
report['overall_passed']=report['functional_passed'] and report.get('quality_marker_passed',False)
save();print(json.dumps({k:report.get(k) for k in ('functional_passed','overall_passed','checks','quality_marker_passed','fatal_error','privacy')},ensure_ascii=True),flush=True)
raise SystemExit(not report['functional_passed'])
