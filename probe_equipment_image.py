"""One supplied screenshot through real OCR/model/Qt, without desktop capture."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import argparse,json,tempfile,time
from pathlib import Path
from dataclasses import asdict
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage,QFontDatabase,QPainter
from PySide6.QtWidgets import QApplication
from babelander import __version__
from babelander.types import Region,Mode,Cancellation
from babelander.controller import Controller
from babelander.engine import Engine
from babelander.settings import Settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.window import MainWindow

parser=argparse.ArgumentParser()
parser.add_argument('image');parser.add_argument('--roi',nargs=4,type=int,required=True)
parser.add_argument('--report',default='test-results/equipment-user-card-a10.json')
args=parser.parse_args();ROOT=Path(__file__).resolve().parent
app=QApplication(['Equipment screenshot background probe'])
for name in ('arial.ttf','msjh.ttc','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
app.setStyle('Fusion');app.setStyleSheet((ROOT/'babelander/theme.qss').read_text(encoding='utf8'))
roi=Region(*args.roi);image=QImage(args.image)
if image.isNull():raise ValueError('Image unavailable')
image=image.copy(QRect(*args.roi)).convertToFormat(QImage.Format.Format_BGR888)
frame=np.frombuffer(image.bits(),np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*3].reshape(image.height(),image.width(),3).copy()
report={'version':__version__,'real_ocr':True,'real_model':True,'qt_platform':app.platformName(),
        'real_desktop_capture':False,'screen_geometry_simulated':True,'semantic_accuracy_scored':False,
        'roi':args.roi,'capture_calls':0,'ocr_calls':0,'results':[]}
with tempfile.TemporaryDirectory(prefix='Babelander2-image-probe-') as temp:
    assets=ROOT.parent/'recovery/test-assets'
    settings=Settings(hotkeys={},model_path=str(next((assets/'models').glob('*.gguf'))),server_path=str(assets/'runtime/llama-server.exe'))
    store=Store(temp);vault=KeyVault(temp);engine=Engine(settings,store,vault,temp)
    controller=Controller(engine,store,settings);window=MainWindow(controller,store,settings,vault,temp)
    real_ocr=controller.ocr.recognize;process=None
    def capture(region):report['capture_calls']+=1;return frame.copy()
    def recognize(pixels,token):
        report['ocr_calls']+=1;lines=real_ocr(pixels,token)
        report['ocr_lines']=[asdict(line) for line in lines];return lines
    def receive(mode):
        result=controller.take_result(mode)
        if result is None:return
        window.receive(result);widget=window.overlay(mode)
        report['results'].append({'translations':[asdict(t) for t in result.translations],
            'renderable':widget.renderable,'render_warning':widget.render_warning,'overlay':widget.text.toPlainText(),
            'geometry':[widget.x(),widget.y(),widget.width(),widget.height()],
            'full_qt_ms':round((time.perf_counter()-started)*1000,2)})
        if widget.renderable:
            target=widget.grab().toImage().convertToFormat(QImage.Format.Format_BGR888)
            destination=ROOT/args.report
            target.save(str(destination.with_suffix('.png')))
            compare=QImage(roi.width*2,roi.height,QImage.Format.Format_RGB32)
            painter=QPainter(compare);painter.drawImage(0,0,image);painter.drawImage(roi.width,0,target);painter.end()
            compare.save(str(destination.with_name(destination.stem+'-comparison.png')))
            output=np.frombuffer(target.bits(),np.uint8).reshape(target.height(),target.bytesPerLine())[:,:target.width()*3].reshape(frame.shape)
            report['weapon_art_pixels_unchanged']=bool(np.array_equal(output[15:237,15:150],frame[15:237,15:150]))
            report['large_power_number_pixels_unchanged']=bool(np.array_equal(output[139:183,172:248],frame[139:183,172:248]))
    controller.delivery.disconnect(window.receive);controller.delivery.connect(receive);controller.ocr.recognize=recognize
    controller.failed.connect(lambda mode,message,generation:report.setdefault('failures',[]).append(message))
    try:
        real_ocr(frame,Cancellation())
        engine.request('We should leave before sunset.',Mode.DIALOG,Cancellation());process=engine.local.process
        started=time.perf_counter()
        with patch('babelander.controller.capture',side_effect=capture),patch('babelander.equipment_overlay.logical_region',return_value=(app.primaryScreen(),QRect(*args.roi))):
            window.region_selected(Mode.EQUIPMENT,roi)
            deadline=started+25
            while not report['results'] and not report.get('failures') and time.perf_counter()<deadline:app.processEvents();time.sleep(.005)
            report['metrics']=controller.metrics.snapshot()
            widget=window.overlay(Mode.EQUIPMENT)
            report['glyph_sizes']=[size for _,_,size in widget.draw_items]
            report['layout_slots']=len(widget.layout_data.slots) if widget.layout_data else 0
            window.stop(Mode.EQUIPMENT);app.processEvents()
            report['stop_restored']=not widget.isVisible() and widget.layout_data is None
        report['passed']=bool(report['results']) and report['capture_calls']==1 and report['ocr_calls']==1 and report['stop_restored']
    except Exception as error:report['error']={'type':type(error).__name__,'message':str(error)};report['passed']=False
    finally:
        window.close();controller.close();controller.join();store.close()
        report['own_model_stopped']=process is None or process.poll() is not None
        report['workers_stopped']=all(not thread.is_alive() for queue in engine.queues.values() for thread in queue.threads)
destination=ROOT/args.report;destination.parent.mkdir(exist_ok=True)
destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({key:value for key,value in report.items() if key not in ('metrics','results')},ensure_ascii=True))
print(json.dumps(report['results'],ensure_ascii=True))
raise SystemExit(not report['passed'])
