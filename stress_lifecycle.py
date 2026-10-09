"""Actual GDI capture cleanup and cancellation during local-model startup."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import json
import tempfile
import threading
import time
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtGui import QPalette,QColor
from PySide6.QtCore import QPoint,Qt,QEventLoop,QTimer
from babelander.windows import dpi_aware,physical_region
from babelander.capture import capture
from babelander.settings import load_settings
from babelander.backends import LocalBackend,BackendError

dpi_aware()
app=QApplication(['Owned capture lifecycle test'])
fixture=QWidget(None,Qt.WindowType.Tool|Qt.WindowType.WindowStaysOnTopHint)
fixture.setWindowTitle('Babelander2 owned lifecycle fixture')
fixture.resize(300,180)
fixture.move(40,app.primaryScreen().availableGeometry().bottom()-fixture.height()-20)
palette=fixture.palette();palette.setColor(QPalette.ColorRole.Window,QColor('white'))
fixture.setPalette(palette);fixture.setAutoFillBackground(True)
fixture.show();app.processEvents()
loop=QEventLoop();QTimer.singleShot(200,loop.quit);loop.exec()
origin=fixture.mapToGlobal(QPoint(20,20))
from babelander.types import Region
region=Region(origin.x(),origin.y(),80,40)
u=ctypes.windll.user32;k=ctypes.windll.kernel32
k.GetCurrentProcess.restype=wintypes.HANDLE
u.GetGuiResources.argtypes=[wintypes.HANDLE,wintypes.DWORD]
u.GetGuiResources.restype=wintypes.DWORD
process=k.GetCurrentProcess()
capture(region) # Populate library and GUI caches before measuring.
before=u.GetGuiResources(process,0)
checks={}
try:
    for _ in range(300):
        pixels=capture(region)
        if pixels.min()<250:raise AssertionError('Owned white fixture was not captured')
    after=u.GetGuiResources(process,0)
    checks['300_real_captures_without_gdi_growth']=after<=before+2
finally:fixture.close()
settings=load_settings(Path(__file__).resolve().parent/'test-results/lifecycle-data')
rows=[]
with tempfile.TemporaryDirectory(prefix='Babelander2-startup-') as directory:
    for index in range(3):
        backend=LocalBackend(settings,Path(directory)/str(index))
        errors=[]
        def start():
            try:backend.start()
            except Exception as error:errors.append(type(error).__name__)
        thread=threading.Thread(target=start)
        thread.start()
        deadline=time.monotonic()+5
        while backend.process is None and thread.is_alive() and time.monotonic()<deadline:time.sleep(.005)
        owned=backend.process
        backend.close();thread.join(5)
        row={'started_process':owned is not None,'thread_stopped':not thread.is_alive(),
             'owned_process_stopped':owned is not None and owned.poll() is not None,
             'backend_process_cleared':backend.process is None,'errors':errors}
        rows.append(row)
        checks['startup_cancel_'+str(index)]=all(row[k] for k in ('started_process','thread_stopped','owned_process_stopped','backend_process_cleared')) and all(e=='BackendError' for e in errors)
report={'passed':all(checks.values()),'checks':checks,'gdi_before':before,'gdi_after':after,'startup_cancellations':rows,
        'note':'Own white fixture only; 300 captures and 3 startup cancellations, not a long-running game stress test'}
Path(__file__).with_name('test-results').joinpath('lifecycle.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
raise SystemExit(not report['passed'])
