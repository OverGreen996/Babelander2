"""Compare identical animated inputs, independent of live sampling timing."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import json,sys,types,subprocess,time,hashlib,gc
from pathlib import Path
import numpy as np
from dataclasses import asdict
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase,QImage,QPainter,QFont,QColor
from babelander.ocr import OCR
from babelander.chat_ocr import ChatRecognitionCache
from babelander.types import Cancellation
from chat_fixtures import chat_frame
from chat_gate_fixtures import variants

ROOT=Path(__file__).resolve().parent
BASELINE='53e9292e104ea05bfe6f66cb10757e6503dd6c2b'
classes=[]
for name,symbol in (('ocr','OCR'),('chat_ocr','ChatRecognitionCache')):
    code=subprocess.check_output(['git','show',BASELINE+':babelander/'+name+'.py'],cwd=ROOT).decode('utf8')
    module=types.ModuleType('babelander._baseline_'+name);module.__package__='babelander'
    exec(compile(code,'<baseline '+name+'>','exec'),module.__dict__)
    classes.append(getattr(module,symbol))
app=QApplication([])
for font in ('arial.ttf','msjh.ttc'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
frames=[]
for i in range(100):
    image=chat_frame(list(range(max(i//20*20,i-3),i+1)))[1]
    for phase,frame in enumerate(variants(image,i)):
        frames.append((f'chat-{i}-{phase}',frame,i//20))
for size in (11,14,18,26):
    for level in (230,45):
        image=QImage(1440,320,QImage.Format.Format_BGR888);image.fill(QColor(16,20,26))
        painter=QPainter(image);font=QFont('Microsoft JhengHei UI');font.setPixelSize(size)
        painter.setFont(font);painter.setPen(QColor(level,level+4,level+10))
        for j,text in enumerate(('Rin: Need keys x5.','Jo: Do not trade item X6.','Kai: HP -12.5%, wait 3 sec.')):
            painter.drawText(20,45+j*45,text)
        painter.end()
        pixels=np.frombuffer(image.bits(),np.uint8).reshape(320,image.bytesPerLine())[:,:4320].reshape(320,1440,3).copy()
        frames.append((f'edge-{size}-{level}',pixels,5))

results={}
for label,ocr_class,cache_class in (('baseline',*classes),('candidate',OCR,ChatRecognitionCache)):
    ocr=ocr_class();cache=cache_class();token=Cancellation();rows=[];group=None
    ocr.recognize(frames[0][1],token)
    for name,frame,current_group in frames:
        if group!=current_group:cache.clear();group=current_group
        at=time.perf_counter();lines=ocr.recognize(frame,token,chat_cache=cache if current_group<5 else None)
        rows.append({'name':name,'ms':(time.perf_counter()-at)*1000,'lines':[asdict(line) for line in lines],
                     'reuse':dict(cache.last),'frame_sha256':hashlib.sha256(frame.tobytes()).hexdigest()})
    results[label]=rows;cache.clear();del ocr;gc.collect()
    print(label+' fixed frames complete',flush=True)
differences=[]
for a,b in zip(results['baseline'],results['candidate']):
    if [line['text'] for line in a['lines']]!=[line['text'] for line in b['lines']]:
        differences.append({'name':a['name'],'baseline':[line['text'] for line in a['lines']],
                            'candidate':[line['text'] for line in b['lines']]})
report={'baseline_commit':BASELINE,'frames':len(frames),'rows':results,'differences':differences,
    'all_texts_equal':not differences,
    'same_frames':all(a['frame_sha256']==b['frame_sha256'] for a,b in zip(*results.values())),
    'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*.py')},
    'real_cpu_ocr':True,'real_desktop_capture':False,'foreground_control_calls':0}
report['passed']=report['all_texts_equal'] and report['same_frames']
(ROOT/'test-results/ocr-fixed-a24.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k not in ('rows','source_sha256','differences')}),flush=True)
raise SystemExit(not report['passed'])
