"""Thirty-minute real GDI/OCR/model/Qt monitor, owned fixture only."""
from pathlib import Path
import argparse
import ctypes
from ctypes import wintypes
import json
import tempfile
import time
from PySide6.QtCore import Qt,QPoint,QTimer,QEventLoop
from PySide6.QtGui import QPainter,QFont,QColor,QImage,QFontDatabase
from PySide6.QtWidgets import QApplication,QWidget
from babelander.windows import dpi_aware
from babelander.types import Mode,Region
from babelander.settings import load_settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.controller import Controller
from babelander.window import MainWindow


def run():
    parser=argparse.ArgumentParser();parser.add_argument('--soak-test',action='store_true');parser.add_argument('--offscreen-fixture',action='store_true');parser.add_argument('--seconds',type=int,default=1800);parser.add_argument('--report',default='soak.json')
    arguments=parser.parse_args();seconds=arguments.seconds
    if seconds<180:parser.error('Resource test requires at least 180 seconds')
    from . import __version__
    import os,sys,hashlib
    if arguments.offscreen_fixture:
        os.environ['QT_QPA_PLATFORM']='offscreen'
    report_path=Path(arguments.report).resolve()
    report_path.parent.mkdir(parents=True,exist_ok=True)
    exe_sha=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest() if getattr(sys,'frozen',False) else None
    def log(value):
        with report_path.with_suffix('.progress.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(value,ensure_ascii=False)+'\n')
        if sys.stdout:print(json.dumps(value,ensure_ascii=False),flush=True)
    dpi_aware();app=QApplication(['Babelander2 owned soak fixture'])
    if arguments.offscreen_fixture:
        font_root=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
        for name in ('arial.ttf','segoeui.ttf','msjh.ttc'):
            if (font_root/name).is_file():QFontDatabase.addApplicationFont(str(font_root/name))
        if 'Arial' not in QFontDatabase.families():raise RuntimeError('Offscreen test requires the Windows Arial font.')
    app.setStyle('Fusion')
    root=Path(__file__).resolve().parent
    app.setStyleSheet((root/'theme.qss').read_text(encoding='utf-8'))
    class Fixture(QWidget):
        def __init__(self):
            super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.WindowStaysOnTopHint)
            self.setWindowTitle('Owned OCR longevity fixture, no user content')
            self.resize(1120,150);self.move(40,40);self.text=''
        def paintEvent(self,event):
            p=QPainter(self);p.fillRect(self.rect(),QColor('white'));p.setPen(QColor('black'))
            p.setFont(QFont('Arial',26));p.drawText(24,85,self.text)
    def events(ms=100):
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
    k=ctypes.windll.kernel32;u=ctypes.windll.user32;ps=ctypes.windll.psapi
    k.GetCurrentProcess.restype=wintypes.HANDLE
    u.GetGuiResources.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    k.GetProcessHandleCount.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    ps.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD]
    process=k.GetCurrentProcess()
    k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.OpenProcess.restype=wintypes.HANDLE
    k.CloseHandle.argtypes=[wintypes.HANDLE]
    k.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    def resources(handle=process):
        memory=Counters();memory.cb=ctypes.sizeof(memory);handles=wintypes.DWORD()
        if not ps.GetProcessMemoryInfo(handle,ctypes.byref(memory),memory.cb):raise ctypes.WinError()
        if not k.GetProcessHandleCount(handle,ctypes.byref(handles)):raise ctypes.WinError()
        stamps=[wintypes.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(handle,*[ctypes.byref(s) for s in stamps]):raise ctypes.WinError()
        cpu=sum((s.dwHighDateTime<<32)+s.dwLowDateTime for s in stamps[2:])/10000000
        return {'rss_mb':round(memory.WorkingSetSize/1048576,2),'private_mb':round(memory.PrivateUsage/1048576,2),
                'gdi':u.GetGuiResources(handle,0),'handles':handles.value,'cpu_seconds':round(cpu,3)}
    def model_resources():
        child=engine.local.process
        if child is None or child.poll() is not None:return None
        handle=k.OpenProcess(0x410,False,child.pid)
        if not handle:return {'pid':child.pid,'error':'OpenProcess unavailable'}
        try:return {'pid':child.pid,**resources(handle),'vram_mb':None,'vram_reason':'Per-process WDDM VRAM not measured.'}
        finally:k.CloseHandle(handle)
    results,errors,samples=[],[],[]
    with tempfile.TemporaryDirectory(prefix='Babelander2-soak-') as directory:
        settings=load_settings(Path(directory));settings.model_path=os.environ.get('BABELANDER_V2_MODEL',settings.model_path);settings.server_path=os.environ.get('BABELANDER_V2_SERVER',settings.server_path);settings.scan_ms=300;settings.stable_ms=150
        settings.hotkeys={}
        store=Store(directory);engine=Engine(settings,store,KeyVault(directory),directory)
        controller=Controller(engine,store,settings)
        window=MainWindow(controller,store,settings,KeyVault(directory),directory)
        controller.failed.connect(lambda mode,message,generation:errors.append({'mode':mode,'message':message}))
        def receive(result):
            row={'elapsed':round(time.monotonic()-started,2),'ms':round(result.total_ms,2),'warnings':sum(bool(t.warning) for t in result.translations),'count':len(result.translations),
                 'event_id':result.event_id,'stages':dict(result.stages),'backend_states':[t.backend_state for t in result.translations],
                 'translations':[{'source':t.source,'target':t.target,'warning':t.warning,'confidence':t.ocr_confidence} for t in result.translations]}
            results.append(row)
            if row['warnings']:log(row)
        controller.result.connect(receive)
        fixture=Fixture()
        capture_patch=None
        def render_frame():
            import numpy as np
            image=QImage(fixture.size(),QImage.Format.Format_RGB32)
            image.fill(QColor('white'));fixture.render(image)
            return np.frombuffer(image.bits(),dtype=np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)[10:140,10:1110,:3].copy()
        if arguments.offscreen_fixture:
            from unittest.mock import patch
            frame=render_frame()
            # Qt raster rendering stays on the main thread; worker gets a copy.
            capture_patch=patch('babelander.controller.capture',side_effect=lambda region:frame.copy())
            capture_patch.start()
        else:
            window.show();fixture.show()
        events(250)
        origin=fixture.mapToGlobal(QPoint(10,10));region=Region(origin.x(),origin.y(),1100,130)
        started=time.monotonic();next_change=0;next_sample=0;changes=0
        texts=['Alice, we must leave before sunset.','Wait for me.','Do not enter the dungeon yet.','We will meet near the ancient gate.']
        checks={};owned=None;phases={'cold_ui':resources()}
        try:
            window.regions[Mode.DIALOG]=region;window.toggle_monitor(Mode.DIALOG)
            while time.monotonic()-started<seconds:
                elapsed=time.monotonic()-started
                if elapsed>=next_change:
                    fixture.text=texts[changes%len(texts)];fixture.update();changes+=1;next_change=elapsed+3
                    if arguments.offscreen_fixture:frame=render_frame()
                if elapsed>=next_sample:
                    # Force fresh model inference once per minute; no paid API.
                    store.clear_cache()
                    row={'elapsed':round(elapsed,2),'results':len(results),**resources(),'model':model_resources()};samples.append(row)
                    log(row);next_sample=elapsed+60
                if errors:break
                events(100)
            owned=engine.local.process
            phases['running']={'app':resources(),'model':model_resources()}
            window.stop(Mode.DIALOG);events(150)
            stop_started=time.monotonic()
            while owned is not None and owned.poll() is None and time.monotonic()-stop_started<5:events(50)
            phases['stopped']={'app':resources(),'model':model_resources(),'release_wait_ms':round((time.monotonic()-stop_started)*1000,2)}
            checks['stop_releases_owned_model_before_close']=owned is not None and owned.poll() is not None
            checks['image_ownership_released']=controller.image_active==0
            checks['preview_snapshot_bound']=controller.latest_snapshot is None
            pipeline=controller.metrics.snapshot()
            checks['duration_completed']=time.monotonic()-started>=seconds
            checks['ongoing_results']=len(results)>=seconds/6 and bool(results) and results[-1]['elapsed']>=seconds-10
            checks['no_controller_errors']=not errors
            checks['no_translation_warnings']=bool(results) and not any(r['warnings'] for r in results)
            # Compare post-warmup windows, ignoring first OCR/Qt/model initialization.
            warm=[s for s in samples if s['elapsed']>=120]
            checks['bounded_gdi']=bool(warm) and max(s['gdi'] for s in warm)-min(s['gdi'] for s in warm)<=10
            if arguments.offscreen_fixture:
                checks.pop('bounded_gdi')
                checks['offscreen_platform_without_desktop_capture']=app.platformName()=='offscreen'
            checks['bounded_handles']=bool(warm) and max(s['handles'] for s in warm)-min(s['handles'] for s in warm)<=30
            checks['bounded_private_memory']=bool(warm) and max(s['private_mb'] for s in warm)-min(s['private_mb'] for s in warm)<=64
        finally:
            fixture.close();window.close();controller.join();store.close()
            if capture_patch:capture_patch.stop()
            checks['workers_stopped']=all(not t.is_alive() for q in engine.queues.values() for t in q.threads)
            checks['release_worker_stopped']=not engine.release_worker.is_alive()
            checks['owned_model_stopped']=owned is not None and owned.poll() is not None
    report={'version':__version__,'frozen':bool(getattr(sys,'frozen',False)),'exe_sha256':exe_sha,'qt_platform':app.platformName(),'passed':all(checks.values()),'duration_seconds':round(time.monotonic()-started,2),'checks':checks,'changes':changes,'samples':samples,'results':results,'errors':errors,'pipeline':pipeline,'phases':phases,'real_desktop_capture':not arguments.offscreen_fixture,'scope':('Offscreen owned raster fixture: Qt/OCR/local CUDA/monitor, no Win32 desktop capture or GDI lifetime validation.' if arguments.offscreen_fixture else 'Owned fixture on real desktop.')+' No games or paid cloud soak; app and model process RAM measured separately; per-process VRAM and game frametime are N/A.'}
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    log({'passed':report['passed'],'checks':checks,'results':len(results)})
    return int(not report['passed'])
