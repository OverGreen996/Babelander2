"""Compare OCR resizing on owned text fixtures; no desktop/user data."""
from pathlib import Path
import json
import re
import statistics
import time
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QFont,QColor
from rapidocr import RapidOCR

app = QApplication(['OCR comparison'])
CASES = [
    ('dialog-28',28,['Alice, we must leave before sunset.']),
    ('equipment-22',22,['Gain +50% Fire Resistance for 10 seconds.']),
    ('quest-16',16,['Collect 3/10 moonstones before 01:30.']),
    ('chat-14',14,['[Party] Player_007: Wait for me.']),
    ('card-multiline-18',18,['Gain +50% Fire Resistance for 10 seconds.','If health is below 30%, gain 12% movement speed.','Otherwise, lose -5% movement speed.']),
]
fixtures = []
for name,size,texts in CASES:
    image = QImage(1100,max(100,len(texts)*(size*2+12)+24),QImage.Format.Format_RGB32)
    image.fill(QColor('white'))
    painter = QPainter(image);painter.setPen(QColor('black'));painter.setFont(QFont('Arial',size))
    for index,text in enumerate(texts):painter.drawText(20,20+(index+1)*(size*2+12),text)
    painter.end()
    pixels=np.frombuffer(image.bits(),dtype=np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)[:,:image.width(),:3].copy()
    fixtures.append((name,texts,pixels))
rows=[]
for policy in ('min','max'):
    ocr=RapidOCR(params={'Global.log_level':'error','Global.use_cls':False,'Global.text_score':.35,
                        'EngineConfig.onnxruntime.intra_op_num_threads':2,'EngineConfig.onnxruntime.inter_op_num_threads':1,
                        'EngineConfig.onnxruntime.enable_cpu_mem_arena':False,'Det.limit_type':policy})
    for name,texts,pixels in fixtures:
        ocr(pixels) # Warm-up deliberately excluded from warm timings.
        times=[]
        for _ in range(3):
            at=time.perf_counter();output=ocr(pixels);times.append((time.perf_counter()-at)*1000)
        recognized=' '.join(output.txts or [])
        normalize=lambda s:re.sub(r'\s+','',s).casefold()
        row={'policy':policy,'case':name,'recognized':recognized,
             'exact_content':normalize(recognized)==normalize(' '.join(texts)),
             'median_ms':round(statistics.median(times),2),'samples_ms':[round(v,2) for v in times]}
        rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
report={'fixture_count':len(fixtures),'warm_repetitions':3,'results':rows,
        'note':'Self-rendered white/black Arial fixtures, 14–28pt. Not evidence for all game fonts/backgrounds.'}
Path(__file__).with_name('test-results').joinpath('ocr-benchmark.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(not all(r['exact_content'] for r in rows if r['policy']=='max'))
