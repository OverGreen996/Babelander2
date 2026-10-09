"""Local readiness, cancellation, priority and Qt checks; no user pixels/API."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace
from unittest.mock import patch
import json,tempfile,threading,time,unittest
from PySide6.QtWidgets import QApplication
from babelander.types import Mode,Cancellation,Cancelled
from babelander.settings import Settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.controller import Controller
from babelander.window import MainWindow
from babelander.backends import LocalBackend,BackendError

APP=QApplication(['Preload offscreen checks'])

def until(predicate,seconds=2):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:APP.processEvents();time.sleep(.005)
    return bool(predicate())

class Backend:
    def __init__(self):
        self.process=None;self.starts=0;self.closed=0;self.entered=threading.Event();self.release=threading.Event()
        self.release.set();self.active=0;self.maximum=0;self.order=[]
    def start(self,token=None):
        self.active+=1;self.maximum=max(self.maximum,self.active);self.entered.set();self.order.append('preload')
        try:
            while not self.release.wait(.01):
                if token:token.check()
            if token:token.check()
            if self.process is None:
                self.starts+=1;self.process=SimpleNamespace(poll=lambda:None)
        finally:self.active-=1
    def translate(self,system,text):
        self.start();return '木橋被落石堵住了。'
    def close(self):self.closed+=1;self.process=None

class PreloadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.settings=Settings(hotkeys={});self.store=Store(self.root);self.vault=KeyVault(self.root)
        self.engine=Engine(self.settings,self.store,self.vault,self.root);self.backend=Backend();self.engine.local=self.backend
        self.controller=Controller(self.engine,self.store,self.settings);self.windows=[]
    def tearDown(self):
        self.backend.release.set();self.engine.backend_release_complete.set()
        for window in self.windows:window.close()
        self.controller.close();self.controller.join();APP.processEvents();self.store.close();self.temp.cleanup()
    def window(self):
        window=MainWindow(self.controller,self.store,self.settings,self.vault,self.root);self.windows.append(window);return window
    def test_manual_only_no_start_on_window_creation(self):
        window=self.window();APP.processEvents()
        self.assertEqual(self.backend.starts,0);self.assertTrue(window.prepare_button.isEnabled());self.assertFalse(window.prepare_cancel.isEnabled())
    def test_preload_no_text_cache_history_usage_ocr_or_cloud(self):
        self.settings.providers={mode.value:'google' for mode in Mode}
        self.controller.ocr.recognize=lambda *args:(_ for _ in ()).throw(AssertionError('OCR must remain lazy'))
        self.engine.cloud.translate=lambda *args:(_ for _ in ()).throw(AssertionError('No paid request'))
        report=self.engine.prepare_local(Cancellation()).result(2)
        self.assertTrue(report['ready']);self.assertFalse(report['already_loaded'])
        self.assertFalse(self.engine.volatile)
        for table in ('cache','history','usage'):
            self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
    def test_repeated_readiness_reuses_same_backend_process(self):
        first=self.engine.prepare_local(Cancellation()).result(2);process=self.backend.process
        second=self.engine.prepare_local(Cancellation()).result(2)
        self.assertFalse(first['already_loaded']);self.assertTrue(second['already_loaded']);self.assertEqual(self.backend.starts,1)
        self.assertIs(self.backend.process,process)
    def test_concurrent_requests_coalesce(self):
        self.backend.release.clear();a=self.engine.prepare_local(Cancellation());self.assertTrue(self.backend.entered.wait(1))
        b=self.engine.prepare_local(Cancellation());self.assertIs(a,b);self.backend.release.set();self.assertTrue(a.result(2)['ready'])
        self.assertEqual(self.backend.starts,1)
    def test_one_cancelled_waiter_does_not_cancel_other(self):
        self.backend.release.clear();token=Cancellation();a=self.engine.prepare_local(token)
        b=self.engine.prepare_local(Cancellation());token.cancel();self.backend.release.set()
        self.assertIs(a,b);self.assertTrue(b.result(2)['ready'])
    def test_all_cancelled_running_preload_retires_without_ready(self):
        self.backend.release.clear();token=Cancellation();future=self.engine.prepare_local(token)
        self.assertTrue(self.backend.entered.wait(1));token.cancel()
        with self.assertRaises(Cancelled):future.result(2)
        self.assertTrue(until(lambda:not self.engine.pending));self.assertEqual(self.engine.active_local_calls,0)
        self.assertEqual(self.backend.starts,0)
    def test_cancelled_entry_not_reused_for_new_preload(self):
        self.backend.release.clear();token=Cancellation();first=self.engine.prepare_local(token)
        self.assertTrue(self.backend.entered.wait(1));token.cancel();second=self.engine.prepare_local(Cancellation())
        self.assertIsNot(first,second);self.backend.release.set()
        with self.assertRaises(Cancelled):first.result(2)
        self.assertTrue(second.result(2)['ready']);self.assertEqual(self.backend.maximum,1);self.assertEqual(self.backend.starts,1)
    def test_existing_local_queue_runs_subtitle_before_queued_preload(self):
        entered=threading.Event();release=threading.Event()
        def block():entered.set();release.wait(2)
        self.engine.queues['local'].submit(Mode.SCREEN,block);self.assertTrue(entered.wait(1))
        future=self.engine.prepare_local(Cancellation())
        subtitle=self.engine.queues['local'].submit(Mode.DIALOG,lambda:self.backend.order.append('subtitle'))
        release.set();subtitle.result(2);future.result(2);self.assertEqual(self.backend.order,['subtitle','preload'])
    def test_unload_does_not_race_active_preload(self):
        self.backend.release.clear();future=self.engine.prepare_local(Cancellation());self.assertTrue(self.backend.entered.wait(1))
        self.assertFalse(self.engine.maybe_unload(time.monotonic()+1000));self.backend.release.set();future.result(2)
        self.assertTrue(until(lambda:not self.engine.pending));self.assertTrue(self.engine.maybe_unload(self.engine.last_local_request+301))
        self.assertTrue(self.backend.closed)
    def test_zero_idle_timeout_retains_preloaded_model(self):
        self.settings.idle_unload_seconds=0;self.engine.prepare_local(Cancellation()).result(2)
        self.assertFalse(self.engine.maybe_unload(time.monotonic()+10000))
    def test_waits_for_previous_model_release_before_loading(self):
        self.engine.backend_release_complete.clear();future=self.engine.prepare_local(Cancellation());time.sleep(.06)
        self.assertFalse(self.backend.entered.is_set());self.engine.backend_release_complete.set();self.assertTrue(future.result(2)['ready'])
    def test_reconfigure_cancels_old_preload(self):
        self.backend.release.clear();future=self.engine.prepare_local(Cancellation());self.assertTrue(self.backend.entered.wait(1))
        self.engine.reconfigure(replace(self.settings,model_path='different.gguf'));self.backend.release.set()
        with self.assertRaises(Cancelled):future.result(2)
        self.assertEqual(self.backend.starts,0)
    def test_ui_loading_state_and_completion(self):
        window=self.window();self.backend.release.clear();window.prepare_model()
        self.assertFalse(window.prepare_button.isEnabled());self.assertTrue(window.prepare_cancel.isEnabled())
        self.assertIn('載入',window.model_status.text());self.backend.release.set()
        self.assertTrue(until(lambda:window.prepare_button.isEnabled()));self.assertIn('已就緒',window.model_status.text())
    def test_ui_double_click_submits_once(self):
        window=self.window();self.backend.release.clear();window.prepare_model();identifier=self.controller.preparation_id
        window.prepare_model();self.assertEqual(self.controller.preparation_id,identifier)
    def test_ui_unsaved_paths_or_profile_requires_save(self):
        window=self.window();window.model_path.setText('unsaved.gguf');window.prepare_model()
        self.assertEqual(self.backend.starts,0);self.assertIn('先儲存',window.model_status.text())
    def test_ui_cancel_suppresses_late_success(self):
        window=self.window();self.backend.release.clear();window.prepare_model();identifier=self.controller.preparation_id
        window.cancel_model_preparation();window.preparation_finished(identifier,{'ready':True})
        self.assertIn('取消',window.model_status.text());self.assertFalse(window.prepare_cancel.isEnabled())
    def test_ready_model_remains_for_other_monitor_client_after_cancel(self):
        self.engine.prepare_local(Cancellation()).result(2);self.engine.acquire_client(('dialog',1))
        window=self.window();self.backend.release.clear();window.prepare_model();self.assertTrue(self.backend.entered.wait(1))
        window.cancel_model_preparation();self.backend.release.set();time.sleep(.1)
        self.assertIsNotNone(self.backend.process);self.assertEqual(self.backend.closed,0)
    def test_close_suppresses_queued_completion(self):
        window=self.window();self.backend.release.clear();window.prepare_model();identifier=self.controller.preparation_id
        window.close();self.backend.release.set();window.preparation_finished(identifier,{'ready':True})
        self.assertTrue(window.closing);self.assertNotIn('已就緒',window.model_status.text())
    def test_ui_backend_failure_is_reported_and_can_retry(self):
        window=self.window();ordinary=self.backend.start
        self.backend.start=lambda token:(_ for _ in ()).throw(BackendError('測試模型檔案無效'))
        window.prepare_model();self.assertTrue(until(lambda:window.prepare_button.isEnabled()))
        self.assertIn('檔案無效',window.model_status.text());self.backend.start=ordinary
        window.prepare_model();self.assertTrue(until(lambda:'已就緒' in window.model_status.text()))
    def test_ui_idle_unload_clears_ready_message(self):
        window=self.window();window.prepare_model();self.assertTrue(until(lambda:'已就緒' in window.model_status.text()))
        self.assertTrue(until(lambda:not self.engine.pending));self.engine.last_local_request=time.monotonic()-301
        window.check_idle_model();self.assertIn('閒置卸載',window.model_status.text())

class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        model=self.root/'model.gguf';model.write_bytes(b'fixture');server=self.root/'server.exe';server.write_bytes(b'fixture')
        self.backend=LocalBackend(Settings(model_path=str(model),server_path=str(server)),self.root)
        self.process=SimpleNamespace(poll=lambda:None,terminate=lambda:None,wait=lambda timeout:0)
    def tearDown(self):self.backend.close();self.temp.cleanup()
    def test_cancelled_before_start_does_not_spawn(self):
        token=Cancellation();token.cancel()
        with patch('babelander.backends.subprocess.Popen') as spawn:
            with self.assertRaises(Cancelled):self.backend.start(token)
            spawn.assert_not_called()
    def test_cancel_during_health_wait_stops_owned_startup(self):
        token=Cancellation()
        def health(*args,**kwargs):token.cancel();return SimpleNamespace(status_code=503)
        with patch('babelander.backends.subprocess.Popen',return_value=self.process),patch('babelander.backends.requests.get',side_effect=health):
            with self.assertRaises(Cancelled):self.backend.start(token)
        self.assertIsNone(self.backend.process);self.assertIsNone(self.backend.log)
    def test_existing_loaded_model_health_failure_does_not_claim_ready_or_kill(self):
        self.backend.process=self.process;self.backend.port=1234
        with patch('babelander.backends.requests.get',return_value=SimpleNamespace(status_code=503)):
            with self.assertRaises(BackendError):self.backend.start(Cancellation())
        self.assertIs(self.backend.process,self.process)
    def test_existing_loaded_model_health_success_reuses_process(self):
        self.backend.process=self.process;self.backend.port=1234
        with patch('babelander.backends.requests.get',return_value=SimpleNamespace(status_code=200)),patch('babelander.backends.subprocess.Popen') as spawn:
            self.backend.start(Cancellation());spawn.assert_not_called()
        self.assertIs(self.backend.process,self.process)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(__import__('__main__')))
    report={'passed':result.wasSuccessful(),'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'qt_platform':'offscreen','backend':'controlled fake','real_game':False,'visible_windows':False,'paid_api':False}
    Path('test-results/preload-unit.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    raise SystemExit(not result.wasSuccessful())
