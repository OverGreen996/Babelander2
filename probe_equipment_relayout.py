"""Layout-only regression using recorded genuine model results, no new OCR/LLM.

This is a debugging aid; final acceptance runs the complete real pipeline.
"""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import json,cv2,numpy as np
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase,QImage
from babelander.types import OCRLine,Translation,Region
from babelander.equipment_layout import equipment_blocks,capture_layout
from babelander.equipment_overlay import EquipmentOverlay
from equipment_game_fixtures import fixtures
root=Path(__file__).parent;app=QApplication([])
for font in ('arial.ttf','georgia.ttf','times.ttf','consola.ttf','trebuc.ttf','segoeui.ttf','cour.ttf','msjh.ttc'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
record=json.loads((root/'test-results/equipment-structures-a12-preservation/report.json').read_text(encoding='utf8'))
for f,r in zip(fixtures(),record['runs']):
    lines=[OCRLine(**l) for l in r['ocr_lines']];blocks=equipment_blocks(f.frame,lines)
    layout=capture_layout(Region(20,10,f.image.width(),f.image.height()),f.frame,blocks)
    lookup={t['source']:Translation(**t) for t in r['translations']}
    if any(b.text not in lookup for b in blocks):print(f.identifier,'grouping_changed');continue
    widget=EquipmentOverlay();widget.set_translations([lookup[b.text] for b in blocks],layout)
    if not widget.renderable:print(f.identifier,widget.render_warning);continue
    im=widget.grab().toImage().convertToFormat(QImage.Format.Format_BGR888)
    out=np.frombuffer(im.bits(),np.uint8).reshape(im.height(),im.bytesPerLine())[:,:im.width()*3].reshape(f.frame.shape)
    bad=[]
    for x0,y0,x1,y1 in f.art_regions:
        diff=np.any(out[y0:y1,x0:x1]!=f.frame[y0:y1,x0:x1],axis=2)
        if diff.any():
            ys,xs=np.where(diff);bad.append({'region':[x0,y0,x1,y1],'pixels':int(diff.sum()),'bounds':[int(xs.min()+x0),int(ys.min()+y0),int(xs.max()+x0),int(ys.max()+y0)]})
    color_bad=[]
    for b,slot in zip(blocks,layout.slots):
        if slot.literal:continue
        x0,y0,x1,y1=slot.source_bounds
        for row in f.rows:
            if x0<=sum(row['bounds'][::2])/2<=x1 and y0<=sum(row['bounds'][1::2])/2<=y1:
                delta=max(abs(a-b) for a,b in zip(row['color'],slot.color))
                if delta>8:color_bad.append([b.text,slot.color,row['color'],delta])
    print(json.dumps({'id':f.identifier,'art_bad':bad,'color_bad':color_bad},ensure_ascii=True));widget.close()
