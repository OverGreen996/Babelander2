"""Real CPU OCR edge cases: quantities, negation, repeats, wraps and noise.

No model, native window, hotkey, desktop capture or saved user data.
"""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import json, hashlib, argparse
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QFont,QColor,QFontDatabase
import numpy as np
from dataclasses import asdict
from babelander.ocr import OCR
from babelander.chat_ocr import ChatRecognitionCache
from babelander.types import Cancellation,Cancelled
from babelander.chat import messages
from babelander.controller import new_chat_lines
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--out');args=parser.parse_args()
app=QApplication(['Offscreen recognition edge cases'])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/arial.ttf')
source={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*.py')}

def frame(texts,noise=0,dim=False):
    image=QImage(1000,300,QImage.Format.Format_BGR888);image.fill(QColor(20,25,32))
    painter=QPainter(image);font=QFont('Arial');font.setPixelSize(26)
    painter.setFont(font);painter.setPen(QColor(135,145,155) if dim else QColor(230,240,250))
    for i,text in enumerate(texts):painter.drawText(22,48+i*43,text)
    painter.end()
    pixels=np.frombuffer(image.bits(),np.uint8).reshape(300,image.bytesPerLine())[:,:3000].reshape(300,1000,3).copy()
    if noise:
        rng=np.random.default_rng(noise)
        pixels=np.clip(pixels.astype(np.int16)+rng.integers(-5,6,pixels.shape,dtype=np.int16),0,255).astype(np.uint8)
    return pixels

scenarios=[
    ('numbers',[(['Alice: I need item X5.'],0,False),(['Alice: I need item X6.'],0,False)]),
    ('negation',[(['Alice: Do not enter the gate yet.'],0,False),(['Alice: Enter the gate now.'],0,False)]),
    ('repeated-speaker',[(['Alice: GG','Bob: ty'],0,False),(['Bob: ty','Alice: GG'],0,False)]),
    ('wrapped',[(['Alice: Keep the four potions for the healer', 'until the next fight starts.'],0,False),
                (['Alice: Keep the six potions for the healer', 'until the next fight starts.','Bob: GG'],0,False)]),
    ('dim-new-line',[(['Alice: Need a shield.'],0,False),(['Alice: Need a shield.','Bob: Need 3 gems.'],0,True)]),
    ('animated-noise',[( ['Alice: I need item X5.','Bob: Do not pull the boss.'],n,False) for n in range(1,5)]),
]
ocr=OCR();rows=[];checks={}
for name,inputs in scenarios:
    cache=ChatRecognitionCache();token=Cancellation();old_full=[];old_reuse=[]
    for index,(texts,noise,dim) in enumerate(inputs):
        pixels=frame(texts,noise,dim)
        full=ocr.recognize(pixels,token)
        reused=ocr.recognize(pixels,token,chat_cache=cache)
        a=[line.text for line in messages(full)];b=[line.text for line in messages(reused)]
        ea,eb=new_chat_lines(old_full,a),new_chat_lines(old_reuse,b)
        checks[f'{name}-{index}-new-events-equal']=ea==eb and bool(full)
        if noise:checks[f'{name}-{index}-noise-not-reused']=cache.last.get('region_reused',0)==0
        if name=='numbers':checks[f'{name}-{index}-quantity']=f'X{5+index}' in ' '.join(eb)
        if name=='negation':checks[f'{name}-{index}-negation']=('not' in ' '.join(eb).lower())==(index==0)
        old_full,old_reuse=a,b
        rows.append({'case':name,'index':index,'authored_source':texts,'full':[asdict(l) for l in full],
                     'reuse':[asdict(l) for l in reused],'new_events':eb,'reuse_stats':dict(cache.last)})
    cache.clear()
    checks[name+'-session-cleared']=not cache.entries and not cache.regions and cache.scope is None
# Cancellation through the real engine's recognize_txt override must release
# the frame and engine context, even when cancellation occurs during inference.
cache=ChatRecognitionCache();token=Cancellation();normal=cache.recognize
def cancel(*a,**kw):
    result=normal(*a,**kw);token.cancel();token.check();return result
cache.recognize=cancel
try:
    ocr.recognize(frame(['Alice: Need six keys.']),token,chat_cache=cache)
    checks['cancel-propagated']=False
except Cancelled:checks['cancel-propagated']=True
checks['cancel-frame-released']=cache.current_regions is None
checks['engine-context-released']=ocr.engine.chat_context is None
cache.clear()
checks['full-ocr-after-cancel']=bool(ocr.recognize(frame(['Bob: GG']),Cancellation()))
result={'checks':checks,'passed':all(checks.values()),'rows':rows,'source_sha256':source,
        'source_unchanged':source=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*.py')},
        'real_cpu_ocr':True,'real_desktop_capture':False,'foreground_control_calls':0}
from babelander import __version__
out=ROOT/(args.out or ('test-results/chat-ocr-edges-a'+__version__.split('a')[-1]+'.json'))
out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'passed':result['passed'],'checks':len(checks),'failed':[k for k,v in checks.items() if not v]}))
raise SystemExit(not result['passed'] or not result['source_unchanged'])
