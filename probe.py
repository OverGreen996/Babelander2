"""Real OCR and local-model smoke test; no legacy application imports."""
from pathlib import Path
import json
import sys
import time

from bootstrap import prepare
prepare()
from babelander.windows import dpi_aware
dpi_aware()
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QFont,QColor
import cv2
from babelander.settings import load_settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.ocr import OCR
from babelander.types import Mode,Cancellation

ROOT = Path(__file__).resolve().parent
app = QApplication.instance() or QApplication(['Babelander2 smoke'])
root = ROOT/'test-results/probe-data'
store = Store(root)
settings = load_settings(root)
engine = Engine(settings,store,KeyVault(root),root)
rows = []
try:
    image = QImage(1080,110,QImage.Format.Format_RGB32)
    image.fill(QColor('white'))
    painter = QPainter(image)
    painter.setPen(QColor('black'))
    painter.setFont(QFont('Arial',30))
    painter.drawText(24,68,'Alice, we must leave before sunset.')
    painter.end()
    image.save(str(root/'ocr.png'))
    lines = OCR().recognize(cv2.imread(str(root/'ocr.png')),Cancellation())
    recognized = ' '.join(l.text for l in lines)
    print('OCR',recognized,flush=True)
    assert 'before sunset' in recognized
    cases = [
        (Mode.DIALOG,recognized),
        (Mode.EQUIPMENT,'Gain +50% Fire Resistance for 10 seconds.'),
        (Mode.QUEST,'Collect 3/10 moonstones before 01:30. Do not leave the area.'),
        (Mode.CHAT,'Do not start the raid. I will return in 5 minutes.'),
        (Mode.REPLY,'我 5 分鐘後回來，請不要開始。'),
        (Mode.SCREEN,'Please read the update notes before entering the dungeon.'),
    ]
    from dataclasses import asdict
    for mode,text in cases:
        started = time.perf_counter()
        result = engine.request(text,mode,Cancellation())
        row = {'mode':mode.value,**asdict(result),'ms':round((time.perf_counter()-started)*1000,2)}
        rows.append(row)
        print(json.dumps(row,ensure_ascii=False),flush=True)
    assert not any(name=='gamelens' or name.startswith('gamelens.') for name in sys.modules)
    report = {'passed':all(not row['warning'] for row in rows),'ocr':recognized,'results':rows,
              'legacy_application_imports':0}
finally:
    engine.close()
    engine.join()
    store.close()
(ROOT/'test-results').mkdir(exist_ok=True)
(ROOT/'test-results/real-local.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(not report['passed'])
