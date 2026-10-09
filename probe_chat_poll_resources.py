"""Actual monitor CPU cost of quiet/animated chat at 800/100 ms. No LLM.

Pre-rendered synthetic frames, real CPU OCR and production scheduling. The
capture stub rotates images by wall clock; rendering is outside timed samples.
"""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import argparse,json,tempfile,time,hashlib
from pathlib import Path
from unittest.mock import patch
from dataclasses import asdict
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
import numpy as np
from babelander.types import Cancellation,Mode,Region,Translation
from babelander.settings import Settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.controller import Controller
from babelander.ocr import OCR
from babelander.window import MainWindow
from chat_fixtures import chat_frame
from replay_resources import process
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=12);args=parser.parse_args()
app=QApplication(['Offscreen poll resource test'])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/msjh.ttc')
base=chat_frame([15,16,17,18])[1]
rng=np.random.default_rng(20261009)
# Shorthand fixture; translation is stubbed to isolate capture/OCR resources.
noise=[np.clip(base.astype(np.int16)+rng.integers(-14,15,base.shape,dtype=np.int16),0,255).astype(np.uint8) for _ in range(12)]
source={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}
rows=[]
shared_ocr=OCR();real_ocr=shared_ocr.recognize
real_ocr(base,Cancellation())
for scan,style in ((800,'quiet'),(100,'quiet'),(100,'noise'),(800,'noise'),(800,'noise'),(100,'noise'),(100,'quiet'),(800,'quiet')):
    with tempfile.TemporaryDirectory(prefix='Babelander-resource-') as directory:
        root=Path(directory);settings=Settings(hotkeys={},chat_scan_ms=scan)
        store=Store(root);engine=Engine(settings,store,KeyVault(root),root);controller=Controller(engine,store,settings)
        controller.ocr=shared_ocr
        # Guard against fixture OCR drift accidentally calling a real model.
        requests=[]
        def translate(mode,token,blocks):
            requests.extend(b.text for b in blocks)
            # Resource isolation: no LLM inference, even if noise misreads GG.
            return [Translation(b.text,'GG','local','resource-fixture') for b in blocks]
        controller._translate_blocks=translate
        real_ocr(base,Cancellation())
        traces=[];captures=[0];errors=[]
        def capture(region):
            captures[0]+=1
            return (base if style=='quiet' else noise[int((time.perf_counter()-started)*10)%len(noise)]).copy()
        def recognize(image,token,**kw):
            result=real_ocr(image,token,**kw)
            traces.append({'lines':[asdict(l) for l in result],'reuse':dict(kw['chat_cache'].last)})
            return result
        controller.ocr.recognize=recognize
        controller.failed.connect(lambda *error:errors.append(list(error)))
        model_calls=[]
        engine.local.translate=lambda *a:(model_calls.append(True),'GG')[1]
        started=time.perf_counter();cpu=time.process_time();mem=[]
        try:
            with patch('babelander.controller.capture',side_effect=capture):
                controller.monitor(Mode.CHAT,Region(0,0,base.shape[1],base.shape[0]))
                deadline=started+args.seconds
                while time.perf_counter()<deadline:app.processEvents();mem.append(process());time.sleep(.02)
                controller.cancel(Mode.CHAT)
                while controller.live:app.processEvents();time.sleep(.005)
            rows.append({'chat_scan_ms':scan,'style':style,'duration_seconds':time.perf_counter()-started,
                         'cpu_core_seconds':time.process_time()-cpu,'captures':captures[0],'ocr_calls':len(traces),
                         'private_max_mib':max(m['private_mib'] for m in mem),
                         'working_max_mib':max(m['working_mib'] for m in mem),'traces':traces,
                         'model_calls':len(model_calls),'errors':errors,
                         'no_model_loaded':engine.local.process is None,
                         'shared_context_cleared':controller.ocr.engine.chat_context is None})
        finally:controller.close();controller.join();store.close();app.processEvents()
    print(json.dumps({k:v for k,v in rows[-1].items() if k!='traces'}),flush=True)
report={'runs':rows,'source_sha256':source,
        'source_unchanged':source=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')},
        'real_desktop_capture':False,'foreground_control_calls':0,
        'translation_stub':True,
        'scope':'12 seconds per phase, quiet/noisy pre-rendered synthetic chat, ONE shared warmed OCR engine across all phases, balanced phase order. CPU core seconds of test app, no actual game FPS/VRAM or model measurement.'}
report['passed']=report['source_unchanged'] and all(not r['errors'] and r['no_model_loaded'] and r['shared_context_cleared'] and not r['model_calls'] for r in rows)
out=ROOT/'test-results/chat-poll-resources-a22.json';out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'passed':report['passed']}));raise SystemExit(not report['passed'])
