"""Real CPU OCR + production chat dispatcher: duplicate speaker and burst."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import json,tempfile,time
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from babelander.types import Mode,Region
from babelander.settings import Settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.controller import Controller
from babelander.window import MainWindow
from chat_fixtures import chat_frame
APP=QApplication(['Chat event checks'])
APP.setStyle('Fusion');APP.setStyleSheet(Path('babelander/theme.qss').read_text(encoding='utf8'))
QFontDatabase.addApplicationFont('C:/Windows/Fonts/msjh.ttc')
import argparse
from babelander import __version__
parser=argparse.ArgumentParser();parser.add_argument('--out',default='test-results/chat-events-a'+__version__.split('a')[-1]);args=parser.parse_args()
DEST=Path(args.out);DEST.mkdir(parents=True,exist_ok=True)
def until(predicate):
    deadline=time.monotonic()+10
    while not predicate() and time.monotonic()<deadline:APP.processEvents();time.sleep(.005)
    APP.processEvents();return bool(predicate())
report={'real_cpu_ocr':True,'real_desktop_capture':False,'qt_platform':APP.platformName(),'foreground_control_calls':0,'results':[],'checks':{}}
with tempfile.TemporaryDirectory() as directory:
    settings=Settings(hotkeys={});store=Store(directory);vault=KeyVault(directory)
    engine=Engine(settings,store,vault,directory);controller=Controller(engine,store,settings);window=MainWindow(controller,store,settings,vault,directory)
    current={};errors=[]
    def capture(region):return current['frame'].copy()
    def receive(mode):
        result=controller.take_result(mode)
        if result is None:return
        window.receive(result)
        report['results'].extend({'source':t.source,'target':t.target,'warning':t.warning,'event_id':result.event_id} for t in result.translations)
    controller.delivery.disconnect(window.receive);controller.delivery.connect(receive)
    controller.failed.connect(lambda *row:errors.append(list(row)))
    try:
        with patch('babelander.controller.capture',side_effect=capture):
            image,current['frame'],_=chat_frame([15]);window.regions[Mode.CHAT]=Region(0,0,image.width(),image.height());window.toggle_monitor(Mode.CHAT)
            assert until(lambda:len(report['results'])==1),'initial GG timeout'
            image,current['frame'],_=chat_frame([15,15])
            assert until(lambda:len(report['results'])==2),'identical appended GG lost'
            report['checks']['same_speaker_identical_GG_twice']=all(r['target']=='[Party] P016: GG' for r in report['results'])
            image,current['frame'],_=chat_frame([15,15,16,17,18,19])
            assert until(lambda:len(report['results'])>=6),'four-message burst lost'
            report['checks']['four_new_messages_fifo']= [r['target'] for r in report['results'][2:]]==['[Party] P017: GG WP','[Party] P018: TY','[Party] P019: NP','[Party] P020: BRB 2 分鐘']
            image.save(str(DEST/'original.png'));window.overlay(Mode.CHAT).grab().save(str(DEST/'translated.png'))
            before=len(report['results']);at=time.monotonic()
            while time.monotonic()-at<1.7:APP.processEvents();time.sleep(.01)
            report['checks']['unchanged_frame_no_repeats']=len(report['results'])==before
            report['checks']['no_warnings']=all(not r['warning'] for r in report['results'])
            report['checks']['latest_message_visible']=window.overlay(Mode.CHAT).text.verticalScrollBar().value()==window.overlay(Mode.CHAT).text.verticalScrollBar().maximum()
            report['sqlite_rows']={table:store.db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('cache','history','usage')}
            report['checks']['no_persistent_chat']=not any(report['sqlite_rows'].values())
            report['checks']['no_model_loaded_for_shorthand']=engine.local.process is None
            report['metrics']=controller.metrics.snapshot();report['errors']=errors
    except Exception as error:report['error']={'type':type(error).__name__,'message':str(error)}
    finally:
        window.close();controller.close();controller.join();store.close();APP.processEvents()
        report['checks']['workers_stopped']=all(not t.is_alive() for q in engine.queues.values() for t in q.threads)
report['passed']=bool(report['checks']) and all(report['checks'].values()) and 'error' not in report and not errors
(DEST/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'passed':report['passed'],'checks':report['checks'],'error':report.get('error')},ensure_ascii=True))
raise SystemExit(not report['passed'])
