"""Pinned detector preprocessing experiment; production engine remains unchanged."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import argparse,json,time,hashlib
from pathlib import Path
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase,QImage,QPainter,QFont,QColor
from babelander.ocr import OCR
from babelander.types import Cancellation
from babelander.chat import filter_decorations,messages,message_key
from chat_fixtures import chat_frame
from chat_gate_fixtures import variants
from rapidocr.ch_ppocr_det.utils import DetPreProcess
parser=argparse.ArgumentParser();parser.add_argument('--caps',default='0,960,736,0');args=parser.parse_args()
root=Path(__file__).resolve().parent
app=QApplication([])
for f in ('arial.ttf','msjh.ttc'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+f)
frames=[]
for i in range(100):
    frame=chat_frame(list(range(max(i//20*20,i-3),i+1)))[1]
    frames.append((f'chat-{i}',variants(frame,i)[i%2]))
# Unseen small, low-contrast and signed-number cases on a wide ROI.
for size in (11,14,18,26):
    for color in ((230,235,240),(45,49,55)):
        image=QImage(1440,320,QImage.Format.Format_BGR888);image.fill(QColor(16,20,26))
        p=QPainter(image);font=QFont('Microsoft JhengHei UI');font.setPixelSize(size);p.setFont(font);p.setPen(QColor(*color))
        for j,t in enumerate(('Rin: Need keys x5.','Jo: Do not trade item X6.','Kai: HP -12.5%, wait 3 sec.')):p.drawText(20,45+j*45,t)
        p.end();pixels=np.frombuffer(image.bits(),np.uint8).reshape(320,image.bytesPerLine())[:,:4320].reshape(320,1440,3).copy()
        frames.append((f'edge-{size}-{color[0]}',pixels))
ocr=OCR();token=Cancellation();ocr.recognize(frames[0][1],token)
det=ocr.engine.text_det;original=det.get_preprocess;runs=[]
for cap in map(int,args.caps.split(',')):
    det.get_preprocess=(lambda max_wh,c=cap:DetPreProcess(c,'max',det.mean,det.std)) if cap else original
    ocr.recognize(frames[0][1],token);cpu=time.process_time();rows=[]
    for name,frame in frames:
        start=time.perf_counter();result=ocr.recognize(frame,token)
        kept,removed=filter_decorations(result)
        rows.append({'name':name,'ms':(time.perf_counter()-start)*1000,'raw':[l.text for l in result],
                     'messages':[l.text for l in messages(kept)],'decorations':removed,
                     'confidence':[l.confidence for l in kept]})
    run={'cap':cap,'cpu_core_seconds':time.process_time()-cpu,'rows':rows,
         'mean_ms':float(np.mean([r['ms'] for r in rows])),'p95_ms':float(np.percentile([r['ms'] for r in rows],95))}
    runs.append(run);print(json.dumps({k:v for k,v in run.items() if k!='rows'}),flush=True)
det.get_preprocess=original
baseline=runs[0]['rows']
for run in runs[1:]:
    run['different']=[{'name':a['name'],'baseline':a['messages'],'candidate':b['messages']} for a,b in zip(baseline,run['rows'])
                      if [message_key(t) for t in a['messages']]!=[message_key(t) for t in b['messages']]]
report={'runs':runs,'installed_rapidocr':'3.9.2','real_cpu_ocr':True,'production_changed':False,
        'foreground_control_calls':0,'real_desktop_capture':False}
(root/'test-results/chat-detector-scale-a23.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'different':{str(i)+':'+str(r['cap']):len(r.get('different',[])) for i,r in enumerate(runs)}}))
