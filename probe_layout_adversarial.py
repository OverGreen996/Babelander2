"""Real OCR comparisons for bright/dim/mixed text; offscreen, no model/API."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
from pathlib import Path
import hashlib
import json
import time
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont,QFontDatabase,QFontMetrics,QImage,QPainter,QPainterPath,QColor,QPen
from PySide6.QtCore import Qt
from babelander.ocr import OCR,signature
from babelander.subtitle_layout import SubtitleLayout
from babelander.monitor import bright_signature,dialogue_text_key
from babelander.types import Cancellation
from babelander.settings import Settings
from babelander import __version__

ROOT=Path(__file__).resolve().parent
APP=QApplication([])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/arial.ttf')
FONT=QFont('Arial',30);FM=QFontMetrics(FONT)

def render(parts):
    image=np.full((250,1450,3),55,dtype=np.uint8)
    picture=QImage(image.data,1450,250,4350,QImage.Format.Format_BGR888)
    painter=QPainter(picture);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    for text,x,y,color in parts:
        path=QPainterPath();path.addText(x,y,FONT,text)
        painter.setPen(QPen(QColor('black'),4));painter.setBrush(QColor('black'));painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(color));painter.drawPath(path)
    painter.end();return image

def ink_key(image):
    ink=bright_signature(image)
    return ('ink',ink) if ink is not None else ('raw',signature(image))

seed=render([('Open the door.',24,55,'white')])
ocr=OCR(lambda:Settings(ocr_threads=4));token=Cancellation()
seed_lines=ocr.recognize(seed,token)
fixtures=[('white_only',[('Open the gate.',24,55,'white')]),
          ('wider_white',[('Open the gate before the guards return.',24,55,'white')]),
          ('two_white_lines',[('Open the gate.',24,55,'white'),('Wait for me.',24,105,'white')]),
          ('moved',[('Open the gate.',24,155,'white')]),
          ('yellow',[('Open the gate.',24,55,'yellow')]),
          ('dim_only',[('Open the gate.',24,55,'#9b9b9b')]),
          ('mixed_new_dim_line',[('Open the gate.',24,55,'white'),('before midnight.',24,105,'#9b9b9b')]),
          ('mixed_inline',[('Open the gate',24,55,'white'),(' before midnight.',24+FM.horizontalAdvance('Open the gate'),55,'#9b9b9b')])]
rows=[]
for name,parts in fixtures:
    image=render(parts);layout=SubtitleLayout();layout.learn(seed,seed_lines,key=ink_key(seed))
    full=ocr.recognize(image,token)
    started=time.perf_counter();fast=ocr.recognize(image,token,layout=layout,layout_key=ink_key(image));elapsed=(time.perf_counter()-started)*1000
    full_text=' '.join(l.text for l in full);fast_text=' '.join(l.text for l in fast)
    rows.append({'fixture':name,'expected':' '.join(p[0].strip() for p in parts),'full_text':full_text,
                 'fast_text':fast_text,'path':layout.last_path,'reason':layout.last_reason,'fast_ms':elapsed,
                 'matches_full_period_tolerant':dialogue_text_key(full_text)==dialogue_text_key(fast_text),
                 'confidence':min((l.confidence for l in fast),default=0)})
    QImage(image.data,1450,250,4350,QImage.Format.Format_BGR888).save(str(ROOT/'test-results'/f'layout-{name}-a8.png'))
manifest=json.loads((ROOT/'test-results/frozen-source-a8.json').read_text(encoding='utf-8'))
unchanged=all(hashlib.sha256((ROOT/'babelander'/name).read_bytes()).hexdigest()==sha for name,sha in manifest.items())
report={'version':__version__,'application_source_sha256':manifest,'source_matches_frozen':unchanged,
        'qt_platform':APP.platformName(),'real_ocr':True,'real_model':False,
        'scope':'Discovery comparison, including unsupported mixed dim scenes. A mismatch is preserved; not declared all-pass recall.',
        'rows':rows,'all_fast_match_full':all(r['matches_full_period_tolerant'] for r in rows)}
(ROOT/'test-results/layout-adversarial-a8.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'rows':rows,'all_fast_match_full':report['all_fast_match_full']},ensure_ascii=False))
raise SystemExit(not unchanged)
