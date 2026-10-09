"""Native Qt worker lifecycle; controlled installer, zero network."""
from pathlib import Path
import json
import tempfile
import threading
import time
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer,QEventLoop
from babelander.asset_ui import AssetPanel
app=QApplication(['Asset panel lifecycle audit'])
def events():
    loop=QEventLoop();QTimer.singleShot(20,loop.quit);loop.exec()
def until(predicate):
    end=time.monotonic()+5
    while time.monotonic()<end:
        if predicate():return
        events()
    raise AssertionError('Worker/UI timed out')
checks={};installed=[]
with tempfile.TemporaryDirectory(prefix='Babelander2-asset-ui-') as directory:
    panel=AssetPanel(directory);panel.installed.connect(lambda *paths:installed.append(paths))
    entered=threading.Event()
    def waiting(root,token,progress):
        progress('受控下載示範',25,100);entered.set()
        while not token.event.wait(.01):pass
        token.check()
    with patch('babelander.asset_ui.install',side_effect=waiting):
        panel.start_button.click();until(entered.is_set);events()
        checks['worker_loading_controls']=not panel.start_button.isEnabled() and panel.cancel_button.isEnabled() and panel.progress.value()==25
        panel.cancel_button.click();until(lambda:panel.worker is None)
        checks['cancel_restores_controls']=panel.start_button.isEnabled() and not panel.cancel_button.isEnabled() and '已取消' in panel.status.text()
        checks['cancel_never_applies_paths']=not installed
    def success(root,token,progress):
        progress('已驗證示範',1,1);return 'fixture.gguf','fixture-server.exe'
    with patch('babelander.asset_ui.install',side_effect=success):
        panel.start_button.click();until(lambda:panel.worker is None)
        checks['success_emits_paths_once']=installed==[('fixture.gguf','fixture-server.exe')] and panel.progress.value()==100
    with patch('babelander.asset_ui.install',side_effect=ValueError('SHA-256 不符')):
        panel.start_button.click();until(lambda:panel.worker is None)
        checks['failure_preserves_paths_and_controls']=len(installed)==1 and 'SHA-256' in panel.status.text() and panel.start_button.isEnabled()
    entered.clear()
    with patch('babelander.asset_ui.install',side_effect=waiting):
        panel.start();until(entered.is_set);worker=panel.worker;panel.shutdown()
        checks['close_cancels_and_joins_worker']=not worker.isRunning()
        until(lambda:panel.worker is None)
    panel.close()
report={'passed':all(checks.values()),'checks':checks,'network':'Controlled installer; no network requests, model assets or user settings changed'}
Path(__file__).with_name('test-results').joinpath('asset-ui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2));raise SystemExit(not report['passed'])
