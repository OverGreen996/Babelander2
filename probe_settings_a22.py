"""Render and check the chat observation setting offscreen at desktop sizes."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import json,tempfile
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from babelander.settings import Settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.controller import Controller
from babelander.window import MainWindow
ROOT=Path(__file__).resolve().parent;out=ROOT/'test-results/settings-a22';out.mkdir(parents=True,exist_ok=True)
app=QApplication(['Offscreen settings preview']);app.setStyle('Fusion')
app.setStyleSheet((ROOT/'babelander/theme.qss').read_text(encoding='utf8'))
QFontDatabase.addApplicationFont('C:/Windows/Fonts/msjh.ttc')
checks={}
with tempfile.TemporaryDirectory(prefix='Babelander-settings-') as d:
    settings=Settings(hotkeys={});store=Store(d);vault=KeyVault(d);engine=Engine(settings,store,vault,d)
    controller=Controller(engine,store,settings);window=MainWindow(controller,store,settings,vault,Path(d))
    try:
        window.stack.setCurrentIndex(8);window.navigation.button(8).setChecked(True);window.show()
        scroll=window.stack.currentWidget()
        for w,h in ((1190,860),(880,680)):
            window.resize(w,h);app.processEvents();scroll.ensureWidgetVisible(window.chat_scan,30,80);app.processEvents()
            window.grab().save(str(out/f'settings-{w}.png'))
            checks[f'{w}-field-in-viewport']=scroll.viewport().rect().contains(window.chat_scan.mapTo(scroll.viewport(),window.chat_scan.rect().center()))
            checks[f'{w}-no-horizontal-scroll']=scroll.horizontalScrollBar().maximum()==0
        checks['default-100ms']=window.chat_scan.value()==100
        checks['field-label']=window.chat_scan.accessibleName()=='聊天觀察間隔'
        checks['field-description']='CPU' in window.chat_scan.accessibleDescription()
        checks['keyboard-focus']=window.chat_scan.focusPolicy().value!=0
    finally:window.close();controller.close();controller.join();store.close();app.processEvents()
report={'checks':checks,'passed':all(checks.values()),'qt_platform':app.platformName(),'foreground_control_calls':0,'real_desktop_capture':False}
(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'passed':report['passed'],'checks':len(checks)}));raise SystemExit(not report['passed'])
