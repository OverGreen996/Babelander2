"""Hard signal-recall cases checked against actual complete OCR outputs."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import json,time,hashlib
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QFont,QColor,QFontDatabase
import numpy as np
from babelander.ocr import OCR,signature
from babelander.types import Cancellation
from chat_gate_experiment import ChatNoiseGate
app=QApplication([]);QFontDatabase.addApplicationFont('C:/Windows/Fonts/msjh.ttc')
def frame(rows,bg=(16,20,26),size=26):
    im=QImage(780,240,QImage.Format.Format_BGR888);im.fill(QColor(*bg))
    p=QPainter(im);font=QFont('Microsoft JhengHei UI');font.setPixelSize(size);p.setFont(font)
    for i,(text,color) in enumerate(rows):p.setPen(QColor(*color));p.drawText(20,45+i*42,text)
    p.end();return np.frombuffer(im.bits(),np.uint8).reshape(240,im.bytesPerLine())[:,:2340].reshape(240,780,3).copy()
white=(230,235,240);cases=[]
for level in (230,100,60,40,34,30):
    color=(level,level+4,level+10)
    for name,a,b in [('quantity','Rin: Need potions x4.','Rin: Need potions x6.'),
                     ('negation','Rin: Do enter the gate.','Rin: Do not enter the gate.'),
                     ('one-digit','Rin: HP 10','Rin: HP 18')]:
        cases.append((f'{name}-{level}',[(a,color)],[(b,color)]))
    cases.append((f'new-dim-row-{level}',[('Jo: GG',white)],[('Jo: GG',white),('Rin: Need keys x5.',color)]))
cases.extend([
    ('clear',[('Jo: GG',white)],[]),
    ('repeated-GG',[('Jo: GG',white)],[('Jo: GG',white),('Jo: GG',white)]),
    ('scroll',[('Rin: TY',white),('Jo: GG',white)],[('Jo: GG',white),('Kai: BRB',white)]),
    ('color-shift',[('Jo: GG',(220,60,80))],[('Jo: GG',(60,130,80))]),
    ('new-color-row',[('Jo: GG',white)],[('Jo: GG',white),('Kai: Need x6',(70,80,180))]),
    ('light-quantity',[('Rin: Need potions x4.',(35,35,35))],[('Rin: Need potions x6.',(35,35,35))]),
    ('tiny-quantity',[('Rin: Need potions x4.',white)],[('Rin: Need potions x6.',white)]),
])
ocr=OCR();rows=[]
for name,a,b in cases:
    options={'bg':(235,235,235)} if name.startswith('light-') else {'size':14} if name.startswith('tiny-') else {}
    before,after=frame(a,**options),frame(b,**options);old=ocr.recognize(before,Cancellation());new=ocr.recognize(after,Cancellation())
    gate=ChatNoiseGate();gate.due(before,signature(before),0);gate.observed(before,signature(before),old,0)
    due=gate.due(after,signature(after),.1)
    row={'case':name,'old':[l.text for l in old],'new':[l.text for l in new],
         'immediate':due,'reason':gate.reason,'stats':gate.last,
         'old_confidence':[l.confidence for l in old],'new_confidence':[l.confidence for l in new]}
    row['recognizable_change']=row['old']!=row['new']
    # A cue exposed at 100 and 200ms, gone at 300ms, was capturable by
    # the original 100ms loop. A periodic recheck at 400ms cannot rescue it.
    row['flash_seen']=due or gate.due(after,signature(after),.2)
    rows.append(row)
result={'rows':rows,'recognizable_changes':sum(v['recognizable_change'] for v in rows),
        'missed_immediate':[v['case'] for v in rows if v['recognizable_change'] and not v['immediate']],
        'missed_200ms_flash':[v['case'] for v in rows if v['recognizable_change'] and not v['flash_seen']],
        'candidate_sha256':hashlib.sha256(Path('chat_gate_experiment.py').read_bytes()).hexdigest(),
        'real_cpu_ocr':True,'real_desktop_capture':False,'foreground_control_calls':0}
Path('test-results/chat-gate-edges.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
