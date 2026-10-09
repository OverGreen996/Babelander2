"""Alternate OpenCV CPU budgets on identical full-OCR frames; no model/desktop."""
import cv2,time,json
from probe_replay_threads import render,text_parts,holdouts,ROOT
from background_corpus_100 import CORPUS
from babelander.ocr import OCR
from babelander.settings import Settings
from babelander.types import Cancellation
from replay_analysis import stats,text_key
original=cv2.getNumThreads();ocr=OCR(lambda:Settings(ocr_threads=2));token=Cancellation()
fixtures=[{'id':str(row['id']),'expected':row['text'],'parts':text_parts(row['text'])} for row in CORPUS[::5]]
fixtures.extend({'id':row['id'],'expected':row['text'],'parts':row['parts']} for row in holdouts()[:6] if row['text'])
ocr.recognize(render(fixtures[0]['parts'],0),token)
rows=[]
try:
    for index,row in enumerate(fixtures):
        image=render(row['parts'],index%16);runs={}
        for threads in ((16,1) if index%2==0 else (1,16)):
            cv2.setNumThreads(threads);started=time.perf_counter();cpu=time.process_time()
            lines=ocr.recognize(image,token)
            runs[str(threads)]={'elapsed_ms':(time.perf_counter()-started)*1000,'cpu_seconds':time.process_time()-cpu,
                'text':' '.join(line.text for line in lines)}
        rows.append({'id':row['id'],'expected':row['expected'],'runs':runs,'texts_match':runs['1']['text']==runs['16']['text']})
finally:cv2.setNumThreads(original)
report={'scope':'Real full CPU OCR on identical pre-rendered frames, alternating order, ONNX threads fixed at 2; OpenCV 16 versus 1. No translation or game FPS claim.',
    'original_opencv_threads':original,'rows':rows,'all_recognized_texts_match':all(row['texts_match'] for row in rows),
    'summary':{str(t):{'latency':stats([row['runs'][str(t)]['elapsed_ms'] for row in rows]),
                     'cpu_core_seconds':round(sum(row['runs'][str(t)]['cpu_seconds'] for row in rows),3),
                     'expected_texts_seen':sum(text_key(row['runs'][str(t)]['text'])==text_key(row['expected']) for row in rows)} for t in (1,16)}}
(ROOT/'test-results/ocr-opencv-budget-a13.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
