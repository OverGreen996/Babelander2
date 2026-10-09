"""Real warm CPU OCR/Qwen/Qt counterexample: dim 200ms transient new row."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import tempfile,time,json,hashlib,argparse
from pathlib import Path
from contextlib import nullcontext
from unittest.mock import patch
from dataclasses import asdict
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QFont,QColor,QFontDatabase
import numpy as np
from babelander.types import Mode,Region,Cancellation
from babelander.settings import Settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.controller import Controller
from babelander.window import MainWindow
from babelander.ocr import signature
from chat_gate_experiment import SignatureAdapter
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--reverse',action='store_true');parser.add_argument('--production-only',action='store_true');parser.add_argument('--out');args=parser.parse_args()
app=QApplication([]);QFontDatabase.addApplicationFont('C:/Windows/Fonts/msjh.ttc')
def frame(dim=False):
    image=QImage(780,240,QImage.Format.Format_BGR888);image.fill(QColor(16,20,26))
    p=QPainter(image);f=QFont('Microsoft JhengHei UI');f.setPixelSize(26);p.setFont(f)
    p.setPen(QColor(230,235,240));p.drawText(20,45,'Jo: GG')
    if dim:p.setPen(QColor(30,34,40));p.drawText(20,87,'Rin: Need keys x5.')
    p.end();return np.frombuffer(image.bits(),np.uint8).reshape(240,image.bytesPerLine())[:,:2340].reshape(240,780,3).copy()
before,after=frame(),frame(True);state={};rows=[]
def until(predicate,seconds=4):
    deadline=time.perf_counter()+seconds
    while not predicate() and time.perf_counter()<deadline:app.processEvents();time.sleep(.002)
    app.processEvents();return bool(predicate())
with tempfile.TemporaryDirectory(prefix='Babelander-flash-') as folder:
    root=Path(folder);assets=ROOT.parent/'recovery/test-assets'
    settings=Settings(hotkeys={},chat_scan_ms=100,model_path=str(next((assets/'models').glob('*.gguf'))),server_path=str(assets/'runtime/llama-server.exe'))
    store=Store(root);engine=Engine(settings,store,KeyVault(root),root);controller=Controller(engine,store,settings)
    window=MainWindow(controller,store,settings,KeyVault(root),root);real=controller.ocr.recognize;backend=None
    window.regions[Mode.CHAT]=Region(0,0,780,240);window.controller.delivery.disconnect(window.receive)
    def receive(mode):
        result=controller.take_result(mode)
        if result is not None:
            window.receive(result)
            state['results'].extend({**asdict(t),'at':time.perf_counter()} for t in result.translations)
    controller.delivery.connect(receive)
    try:
        engine.prepare_local(Cancellation()).result(timeout=65);backend=engine.local.process
        engine.request('We should leave before sunset.',Mode.CHAT,Cancellation());engine.volatile.clear()
        real(before,Cancellation())
        for enabled in ((False,False) if args.production_only else ((True,False) if args.reverse else (False,True))):
            adapter=SignatureAdapter(signature);state.update(image=before,results=[]);engine.volatile.clear();ocr_rows=[]
            def recognize(image,token,**kw):
                result=real(image,token,**kw)
                ocr_rows.append({'lines':[asdict(l) for l in result],'at':time.perf_counter()})
                if enabled:adapter.observed(image,result)
                return result
            controller.ocr.recognize=recognize
            with patch('babelander.controller.capture',side_effect=lambda region:state['image'].copy()),(patch('babelander.controller.signature',side_effect=adapter) if enabled else nullcontext()):
                window.toggle_monitor(Mode.CHAT);assert until(lambda:state['results']),'old GG not ready'
                shown=time.perf_counter();state['image']=after
                until(lambda:time.perf_counter()-shown>=.2,1);ended=time.perf_counter();state['image']=before
                until(lambda:time.perf_counter()-ended>=1.2,2)
                window.stop(Mode.CHAT,release_model=False);assert until(lambda:not controller.live)
            events=[r for r in state['results'] if 'keys' in r['source'].lower()]
            for event in events:event['shown_to_qt_ms']=(event['at']-shown)*1000
            rows.append({'enabled':enabled,'exposure_ms':(ended-shown)*1000,'events':events,'ocr':ocr_rows,
                         'gate_counts':adapter.counts,'recognized_transient':bool(events),
                         'within700':any(r['at']-shown<=.7 and r['target'] and not r['warning'] for r in events)})
            adapter.gate.clear()
    finally:
        window.close();controller.close();controller.join();store.close();app.processEvents()
report={'runs':rows,'candidate_sha256':hashlib.sha256((ROOT/'chat_gate_experiment.py').read_bytes()).hexdigest(),
        'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')},
        'real_cpu_ocr':True,'real_local_model':True,'real_desktop_capture':False,'foreground_control_calls':0,
        'owned_model_stopped':backend is None or backend.poll() is not None}
by_mode={r['enabled']:r for r in rows}
report['recall_not_worse']=(all(r['recognized_transient'] and r['within700'] for r in rows) if args.production_only else by_mode[True]['recognized_transient']>=by_mode[False]['recognized_transient'])
report['production_only']=args.production_only
Path(args.out or ('test-results/chat-gate-flash'+('-production' if args.production_only else '-reversed' if args.reverse else '')+'.json')).write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({'recall_not_worse':report['recall_not_worse'],'runs':[{k:v for k,v in r.items() if k not in ('events','ocr')} for r in rows]}))
raise SystemExit(not report['recall_not_worse'])
