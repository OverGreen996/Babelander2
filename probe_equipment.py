"""Real OCR + CUDA model + Qt equipment replay; no desktop/hotkeys/cloud."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
from pathlib import Path
from dataclasses import asdict
from unittest.mock import patch
import hashlib
import json
import re
import tempfile
import threading
import time
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont,QFontDatabase,QFontMetrics,QImage,QPainter,QColor
from PySide6.QtWidgets import QApplication
from babelander import __version__
from babelander.controller import Controller
from babelander.engine import Engine
from babelander.settings import Settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.types import Mode,Region,Cancellation
from babelander.window import MainWindow

ROOT=Path(__file__).resolve().parent
APP=QApplication(['Equipment real-engine offscreen replay'])
APP.setStyle('Fusion');APP.setStyleSheet((ROOT/'babelander/theme.qss').read_text(encoding='utf-8'))
for name in ('arial.ttf','segoeui.ttf','msjh.ttc'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
FONT=QFont('Arial',23);FM=QFontMetrics(FONT)
ROWS=[
 ('base',[('Copper Longbow','#ffffff'),('Gain +12% movement speed for 5 seconds.','#9b9b9b')]),
 ('dim_digit_change',[('Copper Longbow','#ffffff'),('Gain +18% movement speed for 5 seconds.','#9b9b9b')]),
 ('conditional',[('Lunar Shield','#f0d29b'),('If health is below 30%,','#ffffff'),
                 ('gain +12% movement speed for 5 seconds.','#ffffff'),('Otherwise, gain +3% fire resistance.','#ffffff')]),
 ('prohibition',[('Storm Boots','#f0d29b'),('Gain +15% movement speed for 8 seconds.','#88d2ee'),
                 ('Do not equip this item before level 20.','#ffffff')]),
 ('stats',[('Glass Dagger','#f0d29b'),('Damage: 125','#ffffff'),('Critical Chance: 18%','#88d2ee'),
           ('Durability: 130 / 130','#9b9b9b')]),
 ('unless',[('Sealed Ring','#f0d29b'),('Do not activate the shield unless the outer circle turns violet.','#ffffff')]),
 ('long_effect',[('Guardian Pendant','#f0d29b'),('When you block an attack while health is below 25%,','#ffffff'),
                 ('restore 10% health and gain +15% armor for 8 seconds.','#ffffff'),
                 ('Otherwise, gain +5% movement speed for 3 seconds.','#ffffff'),
                 ('This effect cannot trigger more than once every 30 seconds.','#9b9b9b')]),
 ('description',[('Old Lantern','#f0d29b'),('A dented lantern carried by the missing guard.','#ffffff')]),
]
W,H=740,560
FONT=QFont('Arial');FONT.setPixelSize(23)

def render(parts):
    frame=np.full((H,W,3),28,dtype=np.uint8)
    picture=QImage(frame.data,W,H,W*3,QImage.Format.Format_BGR888)
    painter=QPainter(picture)
    painter.setPen(QColor('#735a37'));painter.drawRect(3,3,W-7,H-7)
    y=42
    for index,(text,color) in enumerate(parts):
        font=QFont(FONT);font.setPixelSize(28 if index==0 else 23)
        painter.setFont(font);painter.setPen(QColor(color));metrics=QFontMetrics(font)
        words=text.split();row=''
        for word in words:
            candidate=(row+' '+word).strip()
            if row and metrics.horizontalAdvance(candidate)>W-48:
                painter.drawText(24,y,row);y+=32;row=word
            else:row=candidate
        painter.drawText(24,y,row);y+=45
    painter.end();return frame

def normalized(text):return ' '.join(text.split())
frames=[render(parts) for _,parts in ROWS]
report={'version':__version__,'qt_platform':APP.platformName(),'real_ocr':True,'real_model':True,
    'real_desktop_capture':False,'semantic_accuracy_scored':False,'single_shot':True,'ocr_threads':2,'cards':[],
    'application_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*.py')}}
with tempfile.TemporaryDirectory(prefix='Babelander2-real-equipment-once-') as temp:
    root=Path(temp);assets=ROOT.parent/'recovery/test-assets'
    settings=Settings(hotkeys={},model_path=str(next((assets/'models').glob('*.gguf'))),server_path=str(assets/'runtime/llama-server.exe'))
    store=Store(root);engine=Engine(settings,store,KeyVault(root),root)
    controller=Controller(engine,store,settings);window=MainWindow(controller,store,settings,KeyVault(root),root)
    current={'frame':frames[0],'row':None,'at':0};backend_process=None
    def capture(region):
        current['row']['capture_calls']+=1
        return current['frame'].copy()
    real_ocr=controller.ocr.recognize
    def ocr(image,token):
        current['row']['ocr_calls']+=1
        return real_ocr(image,token)
    def receive(mode):
        result=controller.take_result(mode)
        if result is None:return
        permitted=controller.displayable(result);window.receive(result)
        row=current['row']
        if row is None or not result.translations:return
        source=normalized(' '.join(t.source for t in result.translations))
        widget=window.overlay(mode)
        item={'source':source,'matches_current_card':source==row['expected_ocr'],'displayable':permitted,
              'translations':[asdict(t) for t in result.translations],'overlay':widget.text.toPlainText(),
              'matches_content':re.sub(r'\s*/\s*','/',source)==re.sub(r'\s*/\s*','/',row['expected_ocr']),
              'renderable':widget.renderable,'render_warning':widget.render_warning,
              'geometry':[widget.x(),widget.y(),widget.width(),widget.height()],
              'full_qt_latency_ms':round((time.perf_counter()-current['at'])*1000,2)}
        row['results'].append(item)
        if item['matches_content'] and permitted and item['renderable'] and all(t.target and not t.warning for t in result.translations):
            row.setdefault('complete_translation_ms',item['full_qt_latency_ms'])
            if row['id'] in ('conditional','stats'):
                widget.grab().save(str(ROOT/('assets/equipment-'+row['id']+'-translated-a10.png')))
                source_image=QImage(current['frame'].data,W,H,W*3,QImage.Format.Format_BGR888)
                source_image.save(str(ROOT/('assets/equipment-'+row['id']+'-original-a10.png')))
                comparison=QImage(W*2,H,QImage.Format.Format_RGB32)
                painter=QPainter(comparison);painter.drawImage(0,0,source_image);painter.drawImage(W,0,widget.grab().toImage());painter.end()
                comparison.save(str(ROOT/('assets/equipment-'+row['id']+'-comparison-a10.png')))
    controller.delivery.disconnect(window.receive);controller.delivery.connect(receive)
    controller.ocr.recognize=ocr
    try:
        real_ocr(frames[0],Cancellation())
        report['warmup_warning']=engine.request('The merchant is waiting by the east gate.',Mode.DIALOG,Cancellation()).warning
        backend_process=engine.local.process;store.clear_cache()
        with patch('babelander.controller.capture',side_effect=capture):
            for index,(identifier,parts) in enumerate(ROWS):
                row={'id':identifier,'expected_ocr':normalized(' '.join(text for text,_ in parts)),
                     'capture_calls':0,'ocr_calls':0,'results':[]}
                report['cards'].append(row);current.update(frame=frames[index],row=row,at=time.perf_counter())
                window.region_selected(Mode.EQUIPMENT,Region(20,80,W,H))
                deadline=current['at']+12
                while not row['results'] and time.perf_counter()<deadline:APP.processEvents();time.sleep(.005)
                current['frame']=frames[(index+1)%len(frames)]
                deadline=time.perf_counter()+.15
                while time.perf_counter()<deadline:APP.processEvents();time.sleep(.005)
                row['ocr_exact_observed']=any(item['matches_current_card'] for item in row['results'])
                row['geometry_exact']=all(item['geometry']==[20,80,W,H] for item in row['results'])
                row['single_capture_ocr']=row['capture_calls']==1 and row['ocr_calls']==1
                print(json.dumps({'id':identifier,'complete_translation_ms':row.get('complete_translation_ms'),
                    'ocr_exact_observed':row['ocr_exact_observed'],'single_capture_ocr':row['single_capture_ocr'],
                    'render_warnings':[item['render_warning'] for item in row['results']]},ensure_ascii=True),flush=True)
            report['no_equipment_monitors']=not controller.capture_streams and not controller.live and Mode.EQUIPMENT not in window.monitoring
            report['metrics']=controller.metrics.snapshot();window.stop(Mode.EQUIPMENT);APP.processEvents()
            report['stop_hid_overlay']=not window.overlay(Mode.EQUIPMENT).isVisible()
            report['stop_released_backdrop']=window.overlay(Mode.EQUIPMENT).layout_data is None
        report['completed']=True
        report['guards_hide_incomplete_cards']=all(item['renderable'] or (item['render_warning'] and not item['overlay']) for row in report['cards'] for item in row['results'])
    except Exception as error:report['error']={'type':type(error).__name__,'message':str(error)}
    finally:
        window.close();controller.close();controller.join();store.close();APP.processEvents()
        report['own_model_stopped']=backend_process is None or backend_process.poll() is not None
        report['workers_stopped']=all(not thread.is_alive() for queue in engine.queues.values() for thread in queue.threads)
values=[row['complete_translation_ms'] for row in report['cards'] if 'complete_translation_ms' in row]
report['summary']={'cards':len(ROWS),'ocr_exact_observed':sum(row.get('ocr_exact_observed',False) for row in report['cards']),
    'content_match_observed':sum(any(item['matches_content'] for item in row['results']) for row in report['cards']),
    'complete_usable_cards':len(values),'single_capture_ocr':sum(row.get('single_capture_ocr',False) for row in report['cards']),
    'geometry_exact':sum(row.get('geometry_exact',False) for row in report['cards']),
    'mean_complete_ms':round(sum(values)/len(values),2) if values else None,'maximum_complete_ms':max(values) if values else None,
    'within_700ms':sum(value<=700 for value in values)}
report['application_source_unchanged']=all(hashlib.sha256((ROOT/'babelander'/name).read_bytes()).hexdigest()==value for name,value in report['application_sha256'].items())
destination=ROOT/'test-results/equipment-real-a10.json';destination.parent.mkdir(exist_ok=True)
destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({key:value for key,value in report.items() if key not in ('cards','application_sha256','metrics')},ensure_ascii=True),flush=True)
raise SystemExit(not report.get('completed',False) or not report.get('guards_hide_incomplete_cards') or not all(row['results'] and row['single_capture_ocr'] and row['geometry_exact'] for row in report['cards']) or not report['own_model_stopped'] or not report['workers_stopped'])
