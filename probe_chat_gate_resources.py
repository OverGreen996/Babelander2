"""Candidate/control ABBA, shared CPU OCR, independent animated capture."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import argparse,json,tempfile,time,hashlib
from pathlib import Path
from unittest.mock import patch
from contextlib import nullcontext
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
import numpy as np
from babelander.types import Cancellation,Mode,Region,Translation
from babelander.settings import Settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.controller import Controller
from babelander.ocr import OCR,signature
from chat_fixtures import chat_frame,STYLES
from chat_gate_experiment import SignatureAdapter
from replay_resources import process
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=12)
parser.add_argument('--scenes',nargs='+',default=['jitter14','waves','translucent','particles'])
parser.add_argument('--quick',action='store_true');args=parser.parse_args()
app=QApplication([]);QFontDatabase.addApplicationFont('C:/Windows/Fonts/msjh.ttc')
base=chat_frame([15,16,17,18])[1];bg=np.array(STYLES[0][4][::-1],dtype=np.int16)
ink=np.any(base!=bg,axis=2);rng=np.random.default_rng(771966)
yy,xx=np.indices(base.shape[:2]);frames={}
for scene in args.scenes:
    frames[scene]=[]
    for step in range(12):
        if scene.startswith('jitter'):
            a=int(scene[6:]);im=np.clip(base.astype(np.int16)+rng.integers(-a,a+1,base.shape,dtype=np.int16),0,255).astype(np.uint8)
        else:
            wave=(30+25*np.sin(xx/80+step*.5)+20*np.sin(yy/100-step*.3)).astype(np.int16)
            background=np.clip(bg+wave[:,:,None],0,255).astype(np.uint8)
            im=background.copy();im[ink]=base[ink]
            if scene=='translucent':im=np.clip(base.astype(np.int16)+wave[:,:,None],0,255).astype(np.uint8)
            if scene=='particles':
                for j in range(40):
                    x=(j*97+step*19)%(base.shape[1]-8);y=(j*71+step*11)%(base.shape[0]-8)
                    im[y:y+5,x:x+5]=(150,160,180)
                im[ink]=base[ink]
        frames[scene].append(im)
ocr=OCR();real=ocr.recognize;real(base,Cancellation());rows=[]
source={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}
candidate=hashlib.sha256((ROOT/'chat_gate_experiment.py').read_bytes()).hexdigest()
for scene in args.scenes:
    for enabled in ([False,True] if args.quick else [False,True,True,False]):
        with tempfile.TemporaryDirectory(prefix='Babelander-gate-resources-') as directory:
            root=Path(directory);settings=Settings(hotkeys={},chat_scan_ms=100)
            store=Store(root);engine=Engine(settings,store,KeyVault(root),root);controller=Controller(engine,store,settings)
            controller.ocr=ocr;adapter=SignatureAdapter(signature);calls=[];errors=[];captures=[0];mem=[]
            controller._translate_blocks=lambda mode,token,blocks:[Translation(b.text,'GG','local','resource-stub') for b in blocks]
            def recognize(image,token,**kw):
                at=time.perf_counter();result=real(image,token,**kw);calls.append({'ms':(time.perf_counter()-at)*1000,'lines':[l.text for l in result]})
                if enabled:adapter.observed(image,result)
                return result
            ocr.recognize=recognize
            def capture(region):
                captures[0]+=1;return frames[scene][int((time.perf_counter()-started)*10)%12].copy()
            controller.failed.connect(lambda *error:errors.append(list(error)))
            started=time.perf_counter();cpu=time.process_time()
            try:
                with patch('babelander.controller.capture',side_effect=capture), (patch('babelander.controller.signature',side_effect=adapter) if enabled else nullcontext()):
                    controller.monitor(Mode.CHAT,Region(0,0,base.shape[1],base.shape[0]))
                    while time.perf_counter()-started<args.seconds:app.processEvents();mem.append(process());time.sleep(.01)
                    controller.cancel(Mode.CHAT)
                    while controller.live:app.processEvents();time.sleep(.005)
                rows.append({'scene':scene,'enabled':enabled,'cpu_core_seconds':time.process_time()-cpu,
                    'duration_seconds':time.perf_counter()-started,'ocr_calls':len(calls),'captures':captures[0],
                    'gate_counts':adapter.counts,'errors':errors,'ocr':calls,
                    'retained_gate_bytes':sum(a.nbytes for a in (adapter.gate.reference,adapter.gate.focus) if a is not None),
                    'private_max_mib':max(v['private_mib'] for v in mem),'no_model_loaded':engine.local.process is None,
                    'shared_context_cleared':ocr.engine.chat_context is None})
            finally:
                controller.close();controller.join();store.close();adapter.gate.clear();app.processEvents()
        print(json.dumps({k:v for k,v in rows[-1].items() if k!='ocr'}),flush=True)
report={'runs':rows,'source_sha256':source,'candidate_sha256':candidate,'real_cpu_ocr':True,
    'real_desktop_capture':False,'foreground_control_calls':0,'translation_stub':True,
    'source_unchanged':source=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')},
    'candidate_unchanged':candidate==hashlib.sha256((ROOT/'chat_gate_experiment.py').read_bytes()).hexdigest()}
report['passed']=report['source_unchanged'] and report['candidate_unchanged'] and all(not r['errors'] and r['no_model_loaded'] and r['shared_context_cleared'] for r in rows)
Path('test-results/chat-gate-resources'+('-quick' if args.quick else '')+'.json').write_text(json.dumps(report,indent=2),encoding='utf8')
raise SystemExit(not report['passed'])
