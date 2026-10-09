"""Static noise vs real text changes; no production edits or model inference."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import json,time
import argparse
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
import numpy as np
from chat_fixtures import chat_frame
from chat_gate_experiment import ChatNoiseGate
from babelander.ocr import OCR,signature
from babelander.types import Cancellation
app=QApplication([]);QFontDatabase.addApplicationFont('C:/Windows/Fonts/msjh.ttc')
parser=argparse.ArgumentParser();parser.add_argument('--noise-only',action='store_true');args=parser.parse_args()
ocr=OCR();base=chat_frame([0,1,2,3])[1];lines=ocr.recognize(base,Cancellation())
rng=np.random.default_rng(996);gate=ChatNoiseGate();gate.due(base,signature(base),0);gate.observed(base,signature(base),lines,0)
rows=[]
for amplitude in (8,14,24):
    count=0;reasons={};times=[]
    for _ in range(30):
        image=np.clip(base.astype(np.int16)+rng.integers(-amplitude,amplitude+1,base.shape,dtype=np.int16),0,255).astype(np.uint8)
        at=time.perf_counter();due=gate.due(image,signature(image),.1);times.append((time.perf_counter()-at)*1000)
        count+=due;reasons[gate.reason]=reasons.get(gate.reason,0)+1
    rows.append({'amplitude':amplitude,'ocr_triggered':count,'n':30,'mean_filter_ms':np.mean(times),'reasons':reasons})
transitions=[]
for index in ([] if args.noise_only else range(1,100)):
    old=chat_frame(list(range(max(index//20*20,index-4),index)))[1] if index%20 else None
    if old is None:continue
    new=chat_frame(list(range(max(index//20*20,index-3),index+1)))[1]
    gate=ChatNoiseGate();old_lines=ocr.recognize(old,Cancellation())
    gate.due(old,signature(old),0);gate.observed(old,signature(old),old_lines,0)
    transitions.append({'index':index,'immediate':gate.due(new,signature(new),.1),'reason':gate.reason})
result={'noise':rows,'transitions':transitions,'immediate':sum(v['immediate'] for v in transitions),'n':len(transitions)}
Path('test-results/chat-gate-discovery.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps({'noise':rows,'immediate':result['immediate'],'n':len(transitions)}))
