"""Real CPU OCR numeric variations, plus explicitly labelled omission injection.

The app sees pixels and first-pass OCR only; expected values score outputs.
No desktop capture, windows, hotkeys, API or translation model.
"""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import hashlib,json,time,cv2
from pathlib import Path
from dataclasses import asdict
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from babelander.ocr import OCR
from babelander.types import Cancellation,OCRLine
from babelander.equipment_layout import equipment_blocks,capture_layout
from babelander.types import Region
from equipment_game_fixtures import battle_card

ROOT=Path(__file__).parent
app=QApplication(['Background numeric variations'])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/georgia.ttf')
ocr=OCR();token=Cancellation();runs=[]
frozen={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*.py')}
for value in (0,1,2,3,4,5,6,7,8,9,10,18,42,99):
    fixture=battle_card(0,health=value)
    primary=ocr.recognize(fixture.frame,token)
    expected_box=next(r['bounds'] for r in fixture.rows if r['panel']=='health' and r['group']=='literal')
    def is_health(line):
        cx=sum(p[0] for p in line.box)/4;cy=sum(p[1] for p in line.box)/4
        return expected_box[0]-5<=cx<=expected_box[2]+5 and expected_box[1]-5<=cy<=expected_box[3]+5
    for injection in (False,True):
        # Fault injection removes numeric OCR lines, never supplies a value/crop.
        before=[line for line in primary if not is_health(line)] if injection else primary
        events=[];reserved=[];at=time.perf_counter()
        after=ocr.recover_equipment(fixture.frame,before,token,lambda *a:events.append(a),reserved.extend)
        ms=(time.perf_counter()-at)*1000
        observed=[line.text for line in after if is_health(line)]
        layout=capture_layout(Region(0,0,425,680),fixture.frame,equipment_blocks(fixture.frame,after),reserved)
        x0,y0,x1,y1=expected_box
        pixels=np.frombuffer(layout.pixels,np.uint8).reshape(fixture.frame.shape)
        preserved=np.array_equal(pixels[y0:y1,x0:x1],fixture.frame[y0:y1,x0:x1])
        runs.append({'expected':str(value),'fault_injected':injection,'primary_health':[line.text for line in before if is_health(line)],
                     'observed_health':observed,'correct':observed==[str(value)],'retry_ms':round(ms,3),'retry_events':events,
                     'source_number_pixels_preserved':bool(preserved),'reserved_boxes':reserved})
negative=[]
for kind in ('ring','diamond','filled','cross','letter'):
    image=np.full((100,300,3),30,np.uint8)
    cv2.putText(image,'Health',(12,45),cv2.FONT_HERSHEY_SIMPLEX,.7,(235,235,235),1,cv2.LINE_AA)
    polygon=np.array([[160,26],[170,39],[160,51],[150,39]])
    if kind=='ring':cv2.circle(image,(160,39),10,(235,235,235),2)
    elif kind=='diamond':cv2.polylines(image,[polygon],True,(235,235,235),2)
    elif kind=='filled':cv2.fillConvexPoly(image,polygon,(235,235,235))
    elif kind=='cross':
        cv2.line(image,(151,39),(169,39),(235,235,235),2);cv2.line(image,(160,29),(160,49),(235,235,235),2)
    else:cv2.putText(image,'A',(150,48),cv2.FONT_HERSHEY_SIMPLEX,.9,(235,235,235),2,cv2.LINE_AA)
    # Controlled first-pass omission of artwork; manually supplied label geometry.
    label=OCRLine('Health',((12,24),(100,24),(100,51),(12,51)),.99)
    after=ocr.recover_equipment(image,[label],token)
    negative.append({'shape':kind,'fault_injected_label_geometry':True,'added_lines':[asdict(l) for l in after if l!=label],
                     'passed':after==[label]})
safe=lambda r:r['correct'] or (not r['observed_health'] and bool(r['reserved_boxes']) and r['source_number_pixels_preserved'])
report={'real_cpu_ocr':True,'new_model':False,'real_desktop_capture':False,'cases':len(runs),'runs':runs,'negative_cases':negative,
        'exact_recovery_cases':sum(r['correct'] for r in runs),'safe_fallback_cases':sum(not r['correct'] and safe(r) for r in runs),
        'wrong_value_cases':sum(bool(r['observed_health']) and not r['correct'] for r in runs),
        'source_sha256':frozen,'source_unchanged':all(hashlib.sha256((ROOT/'babelander'/n).read_bytes()).hexdigest()==sha for n,sha in frozen.items()),
        'passed':all(safe(r) and r['source_number_pixels_preserved'] for r in runs) and all(r['passed'] for r in negative)}
(ROOT/'test-results/equipment-numeric-a14.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k not in ('runs','source_sha256')},indent=2));raise SystemExit(not report['passed'])
