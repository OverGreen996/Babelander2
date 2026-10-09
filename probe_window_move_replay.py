"""Real OCR/CUDA/Qt with controlled foreground transitions, never desktop focus."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import hashlib,json,tempfile,time
import numpy as np
from PySide6.QtCore import QRect,Qt
from PySide6.QtGui import QFontDatabase,QImage,QPainter,QFont,QColor
from PySide6.QtWidgets import QApplication
from babelander.settings import Settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.controller import Controller
from babelander.window import MainWindow
from babelander.window_focus import WindowInfo,WindowBinding,WindowFocus
from babelander.types import Region,Mode,Cancellation

ROOT=Path(__file__).parent
APP=QApplication(['Background focus replay'])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/arial.ttf')
class ForegroundFixture:
    def __init__(self):
        self.target=WindowInfo(100,123,100,(0,0,1600,900),(0,0,1600,900),monitor=1,dpi=96,monitor_bounds=(0,0,2560,1440));self.front=self.target
    def info(self,hwnd):return self.target if hwnd==100 else None
    def foreground(self):return self.front
    def enumerate(self):return [self.target]

sentences=['Before activating the beacon, gather everyone inside the shelter.',
           'The wooden bridge is blocked by fallen rocks.',
           'Before crossing the flooded canyon, inspect every rope on the damaged suspension bridge.']
def frame(text):
    image=QImage(1100,120,QImage.Format.Format_BGR888);image.fill(QColor(25,29,35))
    painter=QPainter(image);font=QFont('Arial');font.setPixelSize(24);painter.setFont(font);painter.setPen(QColor('white'))
    painter.drawText(QRect(16,12,1068,100),Qt.TextFlag.TextWordWrap,text);painter.end()
    return np.frombuffer(image.bits(),np.uint8).reshape(120,image.bytesPerLine())[:,:3300].reshape(120,1100,3).copy()
frames=[frame(text) for text in sentences]
frozen={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*.py')}
report={'real_cpu_ocr':True,'real_cuda_model':True,'qt_platform':'offscreen','foreground_api':'controlled fixture',
        'real_game_validated':False,'real_desktop_capture':False,'visible_windows':False,'foreground_control_calls':0,
        'application_sha256':frozen,'checks':{}}

def until(predicate,seconds=10):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:APP.processEvents();time.sleep(.005)
    return bool(predicate())

with tempfile.TemporaryDirectory(prefix='Babelander-focus-replay-') as directory:
    assets=ROOT.parent/'recovery/test-assets';root=Path(directory)
    settings=Settings(hotkeys={},stable_ms=0,dialog_scan_ms=100,
        model_path=str(next((assets/'models').glob('*.gguf'))),server_path=str(assets/'runtime/llama-server.exe'))
    store=Store(root);vault=KeyVault(root);engine=Engine(settings,store,vault,root)
    controller=Controller(engine,store,settings);window=MainWindow(controller,store,settings,vault,root)
    foreground=ForegroundFixture();window.window_focus=WindowFocus(foreground)
    window.regions[Mode.DIALOG]=Region(0,0,1100,120)
    window.window_bindings[Mode.DIALOG]=WindowBinding.from_info(foreground.target)
    current={'frame':frames[0],'captures':0,'regions':[]};backend=None
    def capture(region):
        current['captures']+=1;current['regions'].append((region.x,region.y,region.width,region.height))
        return current['frame'].copy()
    page=window.pages[Mode.DIALOG]
    def displayed(text):return ' '.join(page.source.toPlainText().split())==text and bool(page.target.toPlainText())
    try:
        controller.ocr.recognize(frames[0],Cancellation())
        engine.request('Before activating the beacon, gather everyone.',Mode.DIALOG,Cancellation())
        backend=engine.local.process;assert backend is not None
        store.clear_cache()
        with patch('babelander.controller.capture',side_effect=capture):
            window.toggle_monitor(Mode.DIALOG)
            assert until(lambda:displayed(sentences[0])),'first cue did not display'
            old_generation=controller.generations[Mode.DIALOG]
            foreground.front=None;window.check_window_focus()
            assert until(lambda:not controller.capture_streams and not controller.live)
            paused_count=current['captures'];time.sleep(.25);APP.processEvents()
            report['checks']['paused_capture_count_unchanged']=current['captures']==paused_count
            report['checks']['paused_overlay_hidden']=not window.overlay(Mode.DIALOG).isVisible()
            report['checks']['warm_model_retained']=engine.local.process is backend and backend.poll() is None
            current['frame']=frames[1];foreground.front=foreground.target
            at=time.perf_counter();window.check_window_focus()
            assert until(lambda:displayed(sentences[1])),'fresh resume cue did not display'
            report['resume_to_full_qt_ms']=round((time.perf_counter()-at)*1000,2)
            report['checks']['fresh_generation_on_return']=controller.generations[Mode.DIALOG]>old_generation
            report['checks']['fresh_source_on_return']=displayed(sentences[1])
            report['checks']['same_model_process_on_return']=engine.local.process is backend
            foreground.target=replace(foreground.target,client=(80,60,1680,960));foreground.front=foreground.target
            current['frame']=frames[2];at=time.perf_counter();window.check_window_focus()
            report['checks']['move_paused_before_rebase']=Mode.DIALOG in window.focus_paused and window.regions[Mode.DIALOG]==Region(0,0,1100,120)
            assert until(lambda:displayed(sentences[2]) and window.regions[Mode.DIALOG]==Region(80,60,1100,120)),'moved cue did not display'
            report['move_observed_to_full_qt_ms']=round((time.perf_counter()-at)*1000,2)
            report['checks']['moved_capture_region_correct']=current['regions'][-1]==(80,60,1100,120)
            report['checks']['same_model_after_move']=engine.local.process is backend
            report['checks']['old_guard_replaced_on_move']=controller.generations[Mode.DIALOG]>old_generation
            current['frame']=frame('Before opening the sealed chamber, verify every protective rune on both sides of the ancient stone door.')
            assert until(lambda:engine.active_local_calls>0),'could not observe third cue model call'
            foreground.front=None;window.check_window_focus()
            assert until(lambda:engine.active_local_calls==0 and not controller.capture_streams and not controller.live)
            APP.processEvents()
            report['checks']['late_real_model_result_did_not_show']=not window.overlay(Mode.DIALOG).isVisible() and not window.overlay(Mode.DIALOG).text.toPlainText()
            window.stop(Mode.DIALOG)
            foreground.front=foreground.target;at_count=current['captures'];window.check_window_focus()
            time.sleep(.25);APP.processEvents()
            report['checks']['manual_stop_did_not_resume']=current['captures']==at_count and Mode.DIALOG not in window.monitoring
            report['metrics']=controller.metrics.snapshot()
            report['completed']=True
    except Exception as error:report['error']={'type':type(error).__name__,'message':str(error)}
    finally:
        window.close();controller.join();store.close();APP.processEvents()
        report['owned_model_stopped']=backend is None or backend.poll() is not None
        report['workers_stopped']=all(not t.is_alive() for queue in engine.queues.values() for t in queue.threads)
report['source_unchanged']=all(hashlib.sha256((ROOT/'babelander'/n).read_bytes()).hexdigest()==sha for n,sha in frozen.items())
report['passed']=bool(report.get('completed')) and all(report['checks'].values()) and report['owned_model_stopped'] and report['workers_stopped'] and report['source_unchanged']
(ROOT/'test-results/window-move-replay-a16.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k not in ('application_sha256','metrics')},indent=2));raise SystemExit(not report['passed'])
