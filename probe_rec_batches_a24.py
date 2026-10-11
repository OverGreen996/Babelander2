"""Alternating same-frame recognition batch sizes, CPU OCR only, offscreen."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import json,time
from pathlib import Path
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from babelander.ocr import OCR
from babelander.types import Cancellation
from chat_fixtures import chat_frame
from chat_gate_fixtures import variants
app=QApplication([])
for f in ('arial.ttf','msjh.ttc'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+f)
ocr=OCR();token=Cancellation()
frames=[variants(chat_frame(list(range(max(i//20*20,i-3),i+1)))[1],i)[0] for i in range(3,100,4)]
ocr.recognize(frames[0],token)
rows=[]
for i,frame in enumerate(frames):
    runs={}
    for batch in ((6,3,2,1) if i%2==0 else (1,2,3,6)):
        ocr.engine.text_rec.rec_batch_num=batch
        at=time.perf_counter();cpu=time.process_time();lines=ocr.recognize(frame,token)
        runs[str(batch)]={'ms':(time.perf_counter()-at)*1000,'cpu':time.process_time()-cpu,'texts':[l.text for l in lines],
                         'scores':[l.confidence for l in lines]}
    rows.append(runs)
summary={str(b):{'mean_ms':float(np.mean([r[str(b)]['ms'] for r in rows])),
    'p95_ms':float(np.percentile([r[str(b)]['ms'] for r in rows],95)),
    'cpu_seconds':sum(r[str(b)]['cpu'] for r in rows),
    'changed_frames':[i for i,r in enumerate(rows) if r[str(b)]['texts']!=r['6']['texts']]} for b in (6,3,2,1)}
out=Path('test-results/ocr-batches-a24.json');out.write_text(json.dumps({'summary':summary,'rows':rows},ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(summary),flush=True)
