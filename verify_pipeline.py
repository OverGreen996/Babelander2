"""Offscreen concurrency/resource-policy checks; synthetic frames, no desktop/API."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from dataclasses import replace
import json
import tempfile
import threading
import time
import unittest
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QLabel
from babelander.types import Mode,Cancellation,Cancelled,OCRLine,Translation,Region,JobResult
from babelander.settings import Settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.controller import Controller
from babelander.pipeline import LiveDispatcher,LiveEvent,Telemetry
from babelander.monitor import DialogueCapture,DialogueFrameGate,FrameSample,bright_signature,dialogue_text_key
from babelander.widgets import CardOverlay
from babelander.window import MainWindow

APP=QApplication(['Babelander2 offscreen pipeline checks'])

def until(predicate, seconds=3):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:time.sleep(.005)
    return bool(predicate())

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='Babelander2-pipeline-')
        self.root=Path(self.temp.name);self.store=Store(self.root)
        self.settings=Settings(hotkeys={},stable_ms=0,scan_ms=300,dialog_scan_ms=300)
        self.engine=Engine(self.settings,self.store,KeyVault(self.root),self.root)
        self.closed=threading.Event();self.calls=[]
        self.engine.local=SimpleNamespace(translate=self.translate,close=self.closed.set)
        self.controller=Controller(self.engine,self.store,self.settings)
        self.dispatchers=[];self.windows=[];self.releases=[]

    def translate(self,system,text):
        self.calls.append(text);return '完整中文譯文'

    def tearDown(self):
        for release in self.releases:release.set()
        for dispatcher in self.dispatchers:dispatcher.close()
        for window in self.windows:window.close()
        self.controller.close();self.controller.join();APP.processEvents()
        self.store.close();self.temp.cleanup()

    def dispatcher(self,mode=Mode.DIALOG):
        generation,token=self.controller._begin(mode)
        dispatcher=LiveDispatcher(self.controller,mode,generation,token)
        self.dispatchers.append(dispatcher)
        return dispatcher,generation,token

    def offer(self,dispatcher,text):
        revision=self.controller._revision(dispatcher.mode,dispatcher.generation)
        event=LiveEvent(revision,(OCRLine(text,(),.99),),time.perf_counter(),1,offered=time.perf_counter())
        dispatcher.offer(event);return revision

    def window(self):
        window=MainWindow(self.controller,self.store,self.settings,KeyVault(self.root),self.root)
        self.windows.append(window);return window

    def test_slow_translation_does_not_block_capture_or_ocr_latest_wins(self):
        entered=threading.Event();release=threading.Event();self.releases.append(release)
        def translate(system,text):
            self.calls.append(text)
            if len(self.calls)==1:entered.set();release.wait(5)
            return '完整中文譯文'
        self.engine.local.translate=translate
        count=[0];names=['First sentence.','Second sentence.','Third sentence.','Fourth sentence.']
        def capture(region):count[0]+=1;return min(count[0],4)
        self.controller.ocr=SimpleNamespace(recognize=lambda frame,token:[OCRLine(names[frame-1],(),.99)])
        results=[]
        self.controller.result.connect(results.append,Qt.ConnectionType.DirectConnection)
        with patch('babelander.controller.capture',side_effect=capture),patch('babelander.controller.signature',side_effect=lambda image:image),patch('babelander.controller.bright_signature',side_effect=lambda image:image),patch.object(self.controller,'_capture_evidence'):
            self.controller.monitor(Mode.DIALOG,Region(0,0,100,40))
            self.assertTrue(entered.wait(2))
            self.assertTrue(until(lambda:count[0]>=4,2))
            self.assertTrue(until(lambda:self.controller.metrics.snapshot()['counts'].get('ocr',0)==4,1))
            state=next(iter(self.controller.live.values())).snapshot()
            self.assertEqual(state,{'pending':1,'in_flight':1,'pending_limit':1})
            # Hold the translation for a full two seconds while capture continues.
            time.sleep(1.2);self.assertGreaterEqual(count[0],7)
            release.set();self.assertTrue(until(lambda:len(results)==1))
            self.controller.cancel(Mode.DIALOG)
            self.assertTrue(until(lambda:not self.controller.live))
        self.assertEqual(self.calls,[names[0],names[-1]])
        self.assertEqual(results[0].translations[0].source,names[-1])
        counts=self.controller.metrics.snapshot()['counts']
        self.assertEqual(counts['skipped_superseded'],2);self.assertEqual(counts['ui_suppressed_stale'],1)
        self.assertEqual(counts['events_created'],counts['success']+counts['skipped_superseded'])

    def test_chat_fifo_is_bounded_and_evictions_counted(self):
        entered=threading.Event();release=threading.Event();self.releases.append(release)
        def translate(system,text):
            self.calls.append(text)
            if len(self.calls)==1:entered.set();release.wait(4)
            return '完整中文譯文'
        self.engine.local.translate=translate
        dispatcher,generation,token=self.dispatcher(Mode.CHAT)
        self.offer(dispatcher,'Message 0.');self.assertTrue(entered.wait(2))
        for i in range(1,12):self.offer(dispatcher,f'Message {i}.')
        self.assertEqual(dispatcher.snapshot()['pending'],8)
        release.set();self.assertTrue(until(lambda:not dispatcher.active and not dispatcher.pending))
        self.assertEqual(self.calls,['Message 0.']+[f'Message {i}.' for i in range(4,12)])
        counts=self.controller.metrics.snapshot()['counts'];self.assertEqual(counts['skipped_capacity'],3)
        self.assertEqual(counts['events_created'],counts['success']+counts['skipped_capacity'])
        self.assertFalse(self.store.history())

    def test_bright_glyph_gate_filters_noise_and_rechecks_mixed_text(self):
        from babelander.ocr import signature
        a=np.full((40,100,3),35,dtype=np.uint8);a[10:15,20:40]=255
        b=np.random.default_rng(7).integers(0,180,size=a.shape,dtype=np.uint8);b[10:15,20:40]=255
        ink=bright_signature(a);self.assertEqual(ink,bright_signature(b))
        self.assertNotEqual(signature(a),signature(b))
        gate=DialogueFrameGate();gate.observed(signature(a),ink,0)
        self.assertFalse(gate.due(signature(b),bright_signature(b),.1))
        self.assertTrue(gate.due(signature(b),bright_signature(b),1.21))
        # Bright colored glyph changes take the immediate path; dim text
        # changing under unchanged bright glyphs remains on the watchdog.
        b[20:25,20:40]=(255,0,0)
        self.assertTrue(gate.due(signature(b),bright_signature(b),.1))
        blank=np.zeros_like(a)
        self.assertTrue(gate.due(signature(blank),bright_signature(blank),.1))

    def test_dim_frame_gate_eventually_observes_single_static_change(self):
        gate=DialogueFrameGate(fallback_ms=800);gate.observed('old',None,0)
        self.assertFalse(gate.due('new',None,.1))
        self.assertTrue(gate.due('new',None,.81))
        gate.observed('new',None,.81)
        self.assertFalse(gate.due('new',None,10))

    def test_confirmation_before_consumer_wait_is_not_lost(self):
        token=Cancellation()
        stream=DialogueCapture(lambda:None,lambda image:None,lambda image:None,self.settings,token,
                               Telemetry(),Mode.DIALOG,lambda message:None)
        first=FrameSample(1,1,10,0,0,'same','ink')
        stream.latest=FrameSample(2,1,11,0,0,'same','ink');stream.epoch=1
        # Reproduce the notification arriving before take(): no pending OCR,
        # but a fresh confirming capture is already available.
        with patch.object(stream.condition,'wait',side_effect=AssertionError('ready confirmation must not sleep')):
            self.assertIsNone(stream.take(after_seq=1,timeout=1))
        self.assertEqual(stream.sequence(),2)
        self.assertIsNotNone(stream.confirmation(first,10.5))

    def test_period_dedup_keeps_numbers_negation_and_expressive_punctuation(self):
        self.assertEqual(dialogue_text_key('Open the\ngate.'),dialogue_text_key('Open the gate'))
        for a,b in [('HP 10','HP 18'),('Value 1.0.','Value 1.0'),('Gain +12','Gain 12'),
                    ('Do not enter.','Do enter.'),('Wait?','Wait!'),('Wait...','Wait.'),
                    ('before midnight','after midnight')]:
            self.assertNotEqual(dialogue_text_key(a),dialogue_text_key(b))

    def test_same_epoch_period_noise_does_not_translate_again(self):
        self.settings.dialog_scan_ms=100;frame=[1];ocr_calls=[];results=[]
        def ocr(image,token):
            ocr_calls.append(image)
            return [OCRLine('Open the gate' if image==1 else 'Open the gate.',(),.99)]
        self.controller.ocr=SimpleNamespace(recognize=ocr)
        self.controller.result.connect(results.append,Qt.ConnectionType.DirectConnection)
        with patch('babelander.controller.capture',side_effect=lambda region:frame[0]),patch('babelander.controller.signature',side_effect=lambda image:image),patch('babelander.controller.bright_signature',return_value='same'),patch.object(self.controller,'_capture_evidence'):
            self.controller.monitor(Mode.DIALOG,Region(0,0,100,40));self.assertTrue(until(lambda:bool(results),1))
            stream=next(iter(self.controller.capture_streams.values()))
            with stream.condition:frame[0]=2;stream.gate.observed_at=float('-inf')
            self.assertTrue(until(lambda:len(ocr_calls)==2,1));time.sleep(.12)
            self.controller.cancel(Mode.DIALOG);self.assertTrue(until(lambda:not self.controller.live))
        self.assertEqual(self.calls,['Open the gate']);self.assertEqual(len(results),1)
        self.assertEqual(results[0].translations[0].source,'Open the gate')

    def test_spurious_capture_notice_does_not_finish_sequence_wait(self):
        token=Cancellation();entered=threading.Event();finished=threading.Event()
        stream=DialogueCapture(lambda:None,lambda image:None,lambda image:None,self.settings,token,
                               Telemetry(),Mode.DIALOG,lambda message:None)
        stream.latest=FrameSample(2,1,11,0,0,'same','ink');stream.epoch=1
        def consume():entered.set();stream.take(after_seq=2,timeout=1);finished.set()
        worker=threading.Thread(target=consume)
        try:
            worker.start();self.assertTrue(entered.wait(1))
            with stream.condition:stream.condition.notify_all()
            self.assertFalse(finished.wait(.03))
            with stream.condition:
                stream.latest=FrameSample(3,1,12,0,0,'same','ink');stream.condition.notify_all()
            self.assertTrue(finished.wait(.5))
        finally:
            token.cancel()
            with stream.condition:stream.condition.notify_all()
            worker.join(1)

    def test_episode_budget_backs_off_only_reliable_unchanged_bright_text(self):
        gate=DialogueFrameGate(adaptive=True)
        gate.observed('frame1','ink1',0);gate.recognized('Open the gate.',True)
        self.assertTrue(gate.due('noise2','ink1',1.21))
        gate.observed('noise2','ink1',1.21);gate.recognized('Open the gate.',True)
        self.assertFalse(gate.due('noise3','ink1',2.5));self.assertTrue(gate.due('noise3','ink1',3.22))
        gate.observed('noise3','ink1',3.22);gate.recognized('Open the gate.',True)
        self.assertEqual(gate.background_seconds,3)
        self.assertTrue(gate.due('changed-number','ink2',3.23))
        gate.observed('changed-number','ink2',3.23);gate.recognized('HP 18',True)
        self.assertEqual(gate.background_seconds,1.2)
        gate.observed('same','ink2',4.5);gate.recognized('HP 18',False)
        self.assertEqual(gate.background_seconds,1.2)
        gate.observed('dim',None,5);gate.recognized('Dim sentence.',True)
        gate.observed('dim2',None,6);gate.recognized('Dim sentence.',True)
        self.assertFalse(gate.due('dim3',None,6.79));self.assertTrue(gate.due('dim3',None,6.81))

    def test_return_to_previous_glyphs_during_slow_ocr_requires_current_epoch(self):
        self.settings.dialog_scan_ms=100
        entered=threading.Event();release=threading.Event();self.releases.append(release)
        frame=[1];ocr_calls=[];results=[]
        def ocr(image,token):
            ocr_calls.append(image)
            if len(ocr_calls)==1:entered.set();release.wait(3)
            return [OCRLine('Returned sentence.' if image==1 else 'Transient sentence.',(),.99)]
        self.controller.ocr=SimpleNamespace(recognize=ocr)
        self.controller.result.connect(results.append,Qt.ConnectionType.DirectConnection)
        with patch('babelander.controller.capture',side_effect=lambda region:frame[0]),patch('babelander.controller.signature',side_effect=lambda image:image),patch('babelander.controller.bright_signature',side_effect=lambda image:image),patch.object(self.controller,'_capture_evidence'):
            self.controller.monitor(Mode.DIALOG,Region(0,0,100,40));self.assertTrue(entered.wait(1))
            stream=next(iter(self.controller.capture_streams.values()))
            frame[0]=2;self.assertTrue(until(lambda:stream.latest.ink==2,1))
            frame[0]=1;self.assertTrue(until(lambda:stream.latest.epoch==3,1))
            release.set();self.assertTrue(until(lambda:bool(results),1))
            self.controller.cancel(Mode.DIALOG);self.assertTrue(until(lambda:not self.controller.live))
        self.assertEqual(ocr_calls,[1,1]);self.assertEqual(self.calls,['Returned sentence.'])
        self.assertEqual(results[0].capture_epoch,3)

    def test_return_during_watchdog_ocr_replaces_pending_even_if_raw_was_seen(self):
        self.settings.dialog_scan_ms=100;frame=[1];raw=[1];token=Cancellation()
        stream=DialogueCapture(lambda:frame[0],lambda image:raw[0],lambda image:image,self.settings,token,
                               Telemetry(),Mode.DIALOG,lambda message:None)
        try:
            stream.start()
            first=None
            self.assertTrue(until(lambda:stream.pending is not None,1));first=stream.take()
            stream.observed(first,'Same sentence.',True)
            with stream.condition:stream.gate.observed_at=float('-inf');raw[0]=2
            self.assertTrue(until(lambda:stream.pending is not None,1));old=stream.take()
            frame[0]=2;self.assertTrue(until(lambda:stream.latest.ink==2,1))
            frame[0]=1;self.assertTrue(until(lambda:stream.latest.epoch==3,1))
            self.assertEqual(stream.pending.sample.key,old.sample.key)
            self.assertEqual(stream.pending.sample.epoch,3)
            stream.observed(old,'Same sentence.',True)
            self.assertEqual(stream.take().sample.epoch,3)
        finally:token.cancel();stream.close()

    def test_ocr_controls_roundtrip_without_changing_translation_cache(self):
        from babelander.settings import save_settings,load_settings
        self.settings.ocr_threads=4;self.settings.adaptive_ocr_recheck=True
        save_settings(self.root,self.settings);loaded=load_settings(self.root)
        self.assertEqual(loaded.ocr_threads,4);self.assertTrue(loaded.adaptive_ocr_recheck)
        for value in (0,5,True):
            with self.assertRaises(ValueError):replace(self.settings,ocr_threads=value).validate()
        with self.assertRaises(ValueError):replace(self.settings,adaptive_ocr_recheck=1).validate()
        first=self.engine.request('A complete sentence.',Mode.DIALOG,Cancellation())
        self.settings.ocr_threads=2;self.settings.adaptive_ocr_recheck=False
        self.assertTrue(self.engine.request('A complete sentence.',Mode.DIALOG,Cancellation()).cache_hit)

    def test_stability_deadline_captures_again_without_waiting_full_scan(self):
        self.settings.dialog_scan_ms=800;self.settings.stable_ms=120
        captures=[];ocr_calls=[];results=[];entered=time.perf_counter()
        def capture(region):captures.append(time.perf_counter());return 1
        self.controller.ocr=SimpleNamespace(recognize=lambda frame,token:(ocr_calls.append(frame),[OCRLine('Stable sentence.',(),.99)])[1])
        self.controller.result.connect(results.append,Qt.ConnectionType.DirectConnection)
        with patch('babelander.controller.capture',side_effect=capture),patch('babelander.controller.signature',return_value='same'),patch('babelander.controller.bright_signature',return_value='same'),patch.object(self.controller,'_capture_evidence'):
            self.controller.monitor(Mode.DIALOG,Region(0,0,100,40))
            self.assertTrue(until(lambda:bool(results),.5))
            self.controller.cancel(Mode.DIALOG);self.assertTrue(until(lambda:not self.controller.live))
        self.assertGreaterEqual(len(captures),2)
        self.assertGreaterEqual(captures[1]-captures[0],.10)
        self.assertLess(captures[1]-entered,.4)
        self.assertEqual(len(ocr_calls),1)

    def test_speed_settings_apply_persist_and_reach_engine(self):
        from babelander.settings import load_settings
        window=self.window()
        self.assertFalse(window.reuse_lines.isChecked())
        self.assertFalse(window.mixed_trigger.isChecked())
        window.ocr_threads.setCurrentIndex(window.ocr_threads.findData(4))
        window.reuse_lines.setChecked(True)
        window.mixed_trigger.setChecked(True)
        window.apply_settings()
        saved=load_settings(self.root)
        self.assertEqual(saved.ocr_threads,4)
        self.assertTrue(saved.reuse_dialogue_lines)
        self.assertTrue(saved.mixed_text_trigger)
        self.assertTrue(self.controller.settings.reuse_dialogue_lines)
        self.assertTrue(self.controller.settings.mixed_text_trigger)
        self.assertIs(self.controller.engine.settings,self.controller.settings)

    def test_line_layout_is_per_session_and_only_used_for_dialogue(self):
        self.settings.reuse_dialogue_lines=True
        hints=[];results=[]
        def ocr(image,token,layout=None,layout_key=None):
            hints.append(layout)
            return [OCRLine('A complete sentence.',(),.99)]
        self.controller.ocr=SimpleNamespace(recognize=ocr)
        self.controller.result.connect(results.append,Qt.ConnectionType.DirectConnection)
        with patch('babelander.controller.capture',return_value=1),patch('babelander.controller.signature',return_value=1),patch('babelander.controller.bright_signature',return_value=1),patch.object(self.controller,'_capture_evidence'):
            for expected in (1,2):
                self.controller.monitor(Mode.DIALOG,Region(0,0,100,40))
                self.assertTrue(until(lambda:len(results)>=expected))
                self.controller.cancel(Mode.DIALOG)
                self.assertTrue(until(lambda:not self.controller.live))
            self.controller.submit_region(Mode.SCREEN,Region(0,0,100,40))
            self.assertTrue(until(lambda:len(hints)>=3))
        self.assertIsNotNone(hints[0]);self.assertIsNotNone(hints[1])
        self.assertIsNot(hints[0],hints[1])
        self.assertIsNone(hints[2])

    def test_new_candidate_invalidates_old_translation_before_stable_deadline(self):
        entered=threading.Event();release=threading.Event();self.releases.append(release)
        candidate=threading.Event();frame=[1];results=[]
        def translate(system,text):entered.set();release.wait(3);return '完整中文譯文'
        def ocr(image,token):
            if image==2:self.settings.stable_ms=1000;candidate.set()
            return [OCRLine('First sentence.' if image==1 else 'Second sentence.',(),.99)]
        self.engine.local.translate=translate;self.controller.ocr=SimpleNamespace(recognize=ocr)
        self.controller.result.connect(results.append,Qt.ConnectionType.DirectConnection)
        with patch('babelander.controller.capture',side_effect=lambda region:frame[0]),patch('babelander.controller.signature',side_effect=lambda image:image),patch('babelander.controller.bright_signature',side_effect=lambda image:image),patch.object(self.controller,'_capture_evidence'):
            self.controller.monitor(Mode.DIALOG,Region(0,0,100,40));self.assertTrue(entered.wait(1))
            frame[0]=2;self.assertTrue(candidate.wait(1))
            self.assertTrue(until(lambda:self.controller.revisions[Mode.DIALOG]>=2,.5))
            release.set()
            self.assertTrue(until(lambda:self.controller.metrics.snapshot()['counts'].get('ui_suppressed_stale',0)==1,.5))
            self.assertFalse(results)
            self.controller.cancel(Mode.DIALOG);self.assertTrue(until(lambda:not self.controller.live))

    def test_ocr_time_counts_toward_stability_but_requires_another_frame(self):
        self.settings.dialog_scan_ms=100;self.settings.stable_ms=100
        captures=[];results=[];ocr_calls=[]
        def capture(region):captures.append(time.perf_counter());return 1
        def ocr(frame,token):ocr_calls.append(frame);time.sleep(.16);return [OCRLine('Stable sentence.',(),.99)]
        self.controller.ocr=SimpleNamespace(recognize=ocr)
        self.controller.result.connect(results.append,Qt.ConnectionType.DirectConnection)
        with patch('babelander.controller.capture',side_effect=capture),patch('babelander.controller.signature',return_value='same'),patch('babelander.controller.bright_signature',return_value='same'),patch.object(self.controller,'_capture_evidence'):
            self.controller.monitor(Mode.DIALOG,Region(0,0,100,40))
            self.assertTrue(until(lambda:bool(results),.5))
            self.controller.cancel(Mode.DIALOG);self.assertTrue(until(lambda:not self.controller.live))
        self.assertGreaterEqual(len(captures),2);self.assertEqual(len(ocr_calls),1)
        # Capture now continues during the 160 ms OCR, and a fresh frame after
        # OCR still confirms it without adding another full scan interval.
        self.assertGreaterEqual(captures[1]-captures[0],.08)
        self.assertLess(captures[1]-captures[0],.15)
        self.assertTrue(any(.15<=at-captures[0]<.26 for at in captures[2:]))

    def test_confirmation_rejects_too_early_and_different_epoch_frames(self):
        stream=DialogueCapture(lambda:None,lambda image:None,lambda image:None,self.settings,Cancellation(),Telemetry(),Mode.DIALOG,lambda message:None)
        first=FrameSample(1,1,10,0,0,'same','ink')
        stream.latest=FrameSample(2,1,10.05,0,0,'same','ink');stream.epoch=1
        self.assertIsNone(stream.confirmation(first,10.1))
        stream.latest=FrameSample(3,2,10.2,0,0,'same','ink');stream.epoch=2
        self.assertIsNone(stream.confirmation(first,10.1))
        stream.latest=FrameSample(4,1,10.2,0,0,'different','changed');stream.epoch=1
        self.assertIsNone(stream.confirmation(first,10.1))

    def test_dim_structure_change_advances_epoch_and_invalidates_old_result(self):
        self.settings.mixed_text_trigger=True;self.settings.dialog_scan_ms=100
        frame=[0];token=Cancellation();metrics=Telemetry()
        stream=DialogueCapture(lambda:np.full((20,30,3),frame[0],dtype=np.uint8),lambda image:'raw-'+str(image[0,0,0]),lambda image:'same-white',self.settings,token,metrics,Mode.DIALOG,lambda message:None)
        with patch('babelander.subtitle_trigger.dim_signature',side_effect=lambda image:None if image[0,0,0]==0 else b'dim-added'):
            stream.start()
            try:
                candidate=stream.take(timeout=1);self.assertIsNotNone(candidate)
                stream.observed(candidate,'Base sentence',True)
                frame[0]=1
                self.assertTrue(until(lambda:stream.snapshot()['epoch']==2,1))
                self.assertFalse(stream.current(candidate.sample))
                changed=stream.take(timeout=1);self.assertEqual(changed.sample.structure,b'dim-added')
                self.assertEqual(changed.sample.ink,candidate.sample.ink)
                self.assertEqual(metrics.snapshot()['counts']['dim_structure_changed'],1)
            finally:token.cancel();stream.close()

    def test_slow_ocr_does_not_block_capture_and_superseded_frames_are_counted(self):
        self.settings.dialog_scan_ms=100
        entered=threading.Event();release=threading.Event();self.releases.append(release)
        frame=[1];ocr_calls=[];results=[]
        def ocr(image,token):
            ocr_calls.append(image)
            if image==1:entered.set();release.wait(3)
            return [OCRLine(f'Sentence number {image}.',(),.99)]
        self.controller.ocr=SimpleNamespace(recognize=ocr)
        self.controller.result.connect(results.append,Qt.ConnectionType.DirectConnection)
        with patch('babelander.controller.capture',side_effect=lambda region:frame[0]),patch('babelander.controller.signature',side_effect=lambda image:image),patch('babelander.controller.bright_signature',side_effect=lambda image:image),patch.object(self.controller,'_capture_evidence'):
            self.controller.monitor(Mode.DIALOG,Region(0,0,100,40));self.assertTrue(entered.wait(1))
            stream=next(iter(self.controller.capture_streams.values()))
            for value in (2,3,4):
                frame[0]=value
                self.assertTrue(until(lambda:stream.latest.ink==value,1))
                self.assertEqual(stream.snapshot()['pending'],1)
            captures=self.controller.metrics.snapshot()['counts']['capture']
            time.sleep(.22)
            self.assertGreater(self.controller.metrics.snapshot()['counts']['capture'],captures)
            self.assertEqual(ocr_calls,[1])
            self.assertEqual(self.controller.metrics.snapshot()['counts']['ocr_candidate_superseded'],2)
            release.set();self.assertTrue(until(lambda:bool(results),1))
            self.controller.cancel(Mode.DIALOG);self.assertTrue(until(lambda:not self.controller.live))
        self.assertEqual(ocr_calls,[1,4]);self.assertEqual(self.calls,['Sentence number 4.'])
        self.assertEqual(results[0].translations[0].source,'Sentence number 4.')
        self.assertEqual(self.controller.metrics.snapshot()['counts']['ocr_result_superseded'],1)

    def test_capture_change_blocks_old_translation_before_next_ocr_finishes(self):
        self.settings.dialog_scan_ms=100
        translating=threading.Event();ocr_entered=threading.Event()
        translation_release=threading.Event();ocr_release=threading.Event()
        self.releases.extend([translation_release,ocr_release]);frame=[1];results=[]
        def translate(system,text):translating.set();translation_release.wait(3);return '完整中文譯文'
        def ocr(image,token):
            if image==2:ocr_entered.set();ocr_release.wait(3)
            return [OCRLine('Old sentence.' if image==1 else 'Current sentence.',(),.99)]
        self.engine.local.translate=translate;self.controller.ocr=SimpleNamespace(recognize=ocr)
        self.controller.result.connect(results.append,Qt.ConnectionType.DirectConnection)
        with patch('babelander.controller.capture',side_effect=lambda region:frame[0]),patch('babelander.controller.signature',side_effect=lambda image:image),patch('babelander.controller.bright_signature',side_effect=lambda image:image),patch.object(self.controller,'_capture_evidence'):
            self.controller.monitor(Mode.DIALOG,Region(0,0,100,40));self.assertTrue(translating.wait(1))
            frame[0]=2;self.assertTrue(ocr_entered.wait(1));translation_release.set()
            self.assertTrue(until(lambda:self.controller.metrics.snapshot()['counts'].get('ui_suppressed_stale',0)==1,1))
            self.assertFalse(results)
            self.controller.cancel(Mode.DIALOG);ocr_release.set()
            self.assertTrue(until(lambda:not self.controller.live,1))
        self.assertFalse(results)

    def test_dialogue_roi_limit_checked_before_capture_thread_starts(self):
        errors=[]
        self.controller.failed.connect(lambda *args:errors.append(args),Qt.ConnectionType.DirectConnection)
        with patch('babelander.controller.capture') as capture:
            self.controller.monitor(Mode.DIALOG,Region(0,0,5000,5000))
            self.assertTrue(until(lambda:bool(errors),1));self.assertTrue(until(lambda:not self.controller.live,1))
            capture.assert_not_called()

    def test_capture_producer_error_stops_and_releases_monitor(self):
        errors=[]
        self.controller.failed.connect(lambda *args:errors.append(args),Qt.ConnectionType.DirectConnection)
        with patch('babelander.controller.capture',side_effect=RuntimeError('Synthetic capture failure')):
            self.controller.monitor(Mode.DIALOG,Region(0,0,100,40))
            self.assertTrue(until(lambda:bool(errors),1));self.assertTrue(until(lambda:not self.controller.live,1))
        self.assertIn('Synthetic capture failure',errors[0][1]);self.assertFalse(self.controller.capture_streams)

    def test_changed_frame_after_slow_ocr_does_not_confirm_old_candidate(self):
        self.settings.dialog_scan_ms=100;self.settings.stable_ms=100
        frame=[1];results=[]
        def ocr(image,token):
            if image==1:time.sleep(.16);frame[0]=2
            return [OCRLine('Old candidate.' if image==1 else 'Current candidate.',(),.99)]
        self.controller.ocr=SimpleNamespace(recognize=ocr)
        self.controller.result.connect(results.append,Qt.ConnectionType.DirectConnection)
        with patch('babelander.controller.capture',side_effect=lambda region:frame[0]),patch('babelander.controller.signature',side_effect=lambda image:image),patch('babelander.controller.bright_signature',side_effect=lambda image:image),patch.object(self.controller,'_capture_evidence'):
            self.controller.monitor(Mode.DIALOG,Region(0,0,100,40))
            self.assertTrue(until(lambda:bool(results),.6))
            self.controller.cancel(Mode.DIALOG);self.assertTrue(until(lambda:not self.controller.live))
        self.assertEqual(self.calls,['Current candidate.'])

    def test_subtitle_scan_setting_roundtrips_and_rejects_unbounded_rate(self):
        from babelander.settings import save_settings,load_settings
        self.settings.dialog_scan_ms=150;save_settings(self.root,self.settings)
        self.assertEqual(load_settings(self.root).dialog_scan_ms,150)
        with self.assertRaises(ValueError):replace(self.settings,dialog_scan_ms=0).validate()
        window=self.window();window.dialog_scan.setValue(180);window.apply_settings()
        self.assertEqual(self.controller.settings.dialog_scan_ms,180)

    def test_chat_observation_setting_roundtrips_independently(self):
        from babelander.settings import save_settings,load_settings
        self.settings.chat_scan_ms=150;save_settings(self.root,self.settings)
        loaded=load_settings(self.root)
        self.assertEqual(loaded.chat_scan_ms,150)
        self.assertEqual(loaded.scan_ms,300)
        self.assertEqual(loaded.dialog_scan_ms,300)
        for value in (0,99,10001,True,100.5):
            with self.subTest(value=value),self.assertRaises(ValueError):replace(self.settings,chat_scan_ms=value).validate()

    def test_old_settings_load_new_chat_default_without_writing_file(self):
        from babelander.settings import load_settings
        path=self.root/'settings.json';content='{"scan_ms":500,"dialog_scan_ms":200,"hotkeys":{}}'
        path.write_text(content,encoding='utf8')
        loaded=load_settings(self.root)
        self.assertEqual((loaded.chat_scan_ms,loaded.scan_ms,loaded.dialog_scan_ms),(100,500,200))
        self.assertEqual(path.read_text(encoding='utf8'),content)

    def test_chat_observation_control_keeps_other_intervals(self):
        window=self.window();window.chat_scan.setValue(200);window.apply_settings()
        self.assertEqual(self.controller.settings.chat_scan_ms,200)
        self.assertEqual(self.controller.settings.dialog_scan_ms,300)
        self.assertEqual(self.controller.settings.scan_ms,300)
        self.assertEqual(window.chat_scan.accessibleName(),'聊天觀察間隔')

    def test_fast_chat_poll_skips_unchanged_ocr_and_does_not_use_old_scan(self):
        self.settings.scan_ms=800;self.settings.chat_scan_ms=100;captures=[];ocr_calls=[]
        self.controller.ocr=SimpleNamespace(recognize=lambda frame,token,**kw:(ocr_calls.append(frame),
            [OCRLine('Bob: GG',((0,0),(60,0),(60,20),(0,20)),.99)])[1])
        def capture(region):captures.append(time.monotonic());return 1
        with patch('babelander.controller.capture',side_effect=capture),patch('babelander.controller.signature',side_effect=lambda image:image),patch.object(self.controller,'_capture_evidence'):
            self.controller.monitor(Mode.CHAT,Region(0,0,100,40))
            self.assertTrue(until(lambda:len(captures)>=3,.65))
            self.controller.cancel(Mode.CHAT);self.assertTrue(until(lambda:not self.controller.live))
        self.assertEqual(len(ocr_calls),1)
        self.assertTrue(all(b-a>=.07 for a,b in zip(captures,captures[1:])))

    def test_chat_short_poll_never_overlaps_slow_ocr(self):
        self.settings.chat_scan_ms=100;active=[0];peak=[0];calls=[]
        def ocr(frame,token,**kw):
            active[0]+=1;peak[0]=max(peak[0],active[0]);calls.append(frame)
            try:time.sleep(.15);token.check();return []
            finally:active[0]-=1
        self.controller.ocr=SimpleNamespace(recognize=ocr)
        def capture(region):return len(calls)+1
        with patch('babelander.controller.capture',side_effect=capture),patch('babelander.controller.signature',side_effect=lambda image:image),patch.object(self.controller,'_capture_evidence'):
            self.controller.monitor(Mode.CHAT,Region(0,0,100,40))
            self.assertTrue(until(lambda:len(calls)>=2,.8))
            self.controller.cancel(Mode.CHAT);self.assertTrue(until(lambda:not self.controller.live))
        self.assertEqual(peak[0],1)
        self.assertEqual(active[0],0)

    def test_other_image_work_can_enter_during_continuously_busy_chat(self):
        self.settings.chat_scan_ms=100;entered=threading.Event();first=threading.Event();calls=[]
        other=Cancellation();roi=Region(0,0,100,40)
        def ocr(frame,token,**kw):
            calls.append(frame);first.set();time.sleep(.15);token.check();return []
        self.controller.ocr=SimpleNamespace(recognize=ocr)
        def acquire():
            try:
                with self.controller._image(roi,other):entered.set()
            except Cancelled:pass
        worker=threading.Thread(target=acquire)
        try:
            with patch('babelander.controller.capture',side_effect=lambda region:len(calls)+1),patch('babelander.controller.signature',side_effect=lambda image:image),patch.object(self.controller,'_capture_evidence'):
                self.controller.monitor(Mode.CHAT,roi)
                self.assertTrue(first.wait(.5));worker.start()
                self.assertTrue(entered.wait(.8),'busy chat starved another image task')
                self.controller.cancel(Mode.CHAT);self.assertTrue(until(lambda:not self.controller.live))
        finally:
            other.cancel();self.controller.cancel(Mode.CHAT)
            if worker.ident is not None:worker.join(1)
        self.assertFalse(worker.is_alive())

    def test_image_admission_preserves_arrival_order(self):
        roi=Region(0,0,20,20);order=[];workers=[]
        def work(index):
            with self.controller._image(roi,Cancellation()):order.append(index)
        with self.controller._image(roi,Cancellation()):
            for index in range(3):
                worker=threading.Thread(target=work,args=(index,));workers.append(worker);worker.start()
                self.assertTrue(until(lambda:len(self.controller.image_waiters)==index+1))
        for worker in workers:worker.join(1)
        self.assertEqual(order,[0,1,2]);self.assertFalse(self.controller.image_waiters)

    def test_cancelled_image_queue_head_does_not_block_next(self):
        roi=Region(0,0,20,20);cancel=Cancellation();outcome=[]
        def work(token,label):
            try:
                with self.controller._image(roi,token):outcome.append(label)
            except Cancelled:outcome.append('cancelled')
        with self.controller._image(roi,Cancellation()):
            first=threading.Thread(target=work,args=(cancel,'first'));first.start()
            self.assertTrue(until(lambda:len(self.controller.image_waiters)==1))
            second=threading.Thread(target=work,args=(Cancellation(),'second'));second.start()
            self.assertTrue(until(lambda:len(self.controller.image_waiters)==2))
            cancel.cancel();first.join(1)
            self.assertEqual(outcome,['cancelled'])
        second.join(1)
        self.assertEqual(outcome,['cancelled','second']);self.assertEqual(self.controller.image_active,0)
        self.assertFalse(self.controller.image_waiters)

    def test_failed_output_suppressed_until_session_or_configuration_changes(self):
        self.engine.local.translate=lambda system,text:(self.calls.append(text),'12')[1]
        dispatcher,generation,token=self.dispatcher()
        text='A genuinely complete sentence.'
        for expected in (1,2):
            self.offer(dispatcher,text)
            self.assertTrue(until(lambda:self.controller.metrics.snapshot()['counts'].get('success',0)>=expected))
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.controller.metrics.snapshot()['counts']['negative_suppressed'],1)
        self.settings.profile='shared';self.offer(dispatcher,text)
        self.assertTrue(until(lambda:len(self.calls)==2))
        dispatcher.close()
        # New sessions carry no old negative entries. Keep another active client
        # to prevent this synthetic backend being released between sessions.
        self.engine.acquire_client('fixture')
        second,_,_=self.dispatcher();self.offer(second,text)
        self.assertTrue(until(lambda:len(self.calls)==3))
        self.engine.release_client('fixture')

    def test_receiver_rejects_stale_revision_and_old_session(self):
        window=self.window();generation,token=self.controller._begin(Mode.DIALOG)
        old=self.controller._revision(Mode.DIALOG,generation)
        result=JobResult(Mode.DIALOG,generation,(Translation('First.','第一句','local','fixture'),),event_id=old)
        self.controller._revision(Mode.DIALOG,generation)
        window.receive(result);self.assertEqual(window.pages[Mode.DIALOG].target.toPlainText(),'')
        self.controller.cancel(Mode.DIALOG);window.receive(replace(result,event_id=0))
        self.assertEqual(window.pages[Mode.DIALOG].target.toPlainText(),'')
        self.assertEqual(self.controller.metrics.snapshot()['counts']['ui_slot_suppressed'],2)

    def test_actual_qt_queued_notice_after_stop_uses_only_new_session_result(self):
        window=self.window();generation,token=self.controller._begin(Mode.DIALOG)
        old=JobResult(Mode.DIALOG,generation,(Translation('OLD SECRET','舊的譯文','local','fixture'),))
        worker=threading.Thread(target=lambda:self.controller._publish(old));worker.start();worker.join(1)
        window.stop(Mode.DIALOG)
        generation,token=self.controller._begin(Mode.DIALOG)
        current=JobResult(Mode.DIALOG,generation,(Translation('New sentence.','新的譯文','local','fixture'),))
        self.controller._publish(current)
        APP.processEvents()
        self.assertEqual(window.pages[Mode.DIALOG].target.toPlainText(),'新的譯文')
        self.assertNotIn('OLD SECRET',window.pages[Mode.DIALOG].source.toPlainText())

    def test_chat_decorations_are_filtered_before_events_and_evidence_stays_raw(self):
        text=OCRLine('Jo: GG',((10,10),(130,10),(130,40),(10,40)),.99)
        shape=OCRLine('■',((250,12),(258,12),(258,20),(250,20)),.99)
        self.controller.ocr=SimpleNamespace(recognize=lambda *a,**kw:[text,shape])
        results=[];evidence=[]
        self.controller.result.connect(results.append,Qt.ConnectionType.DirectConnection)
        with patch('babelander.controller.capture',return_value=1),patch('babelander.controller.signature',return_value=1),patch.object(self.controller,'_capture_evidence',side_effect=lambda *args:evidence.append(args[-1])):
            self.controller.monitor(Mode.CHAT,Region(0,0,300,100))
            self.assertTrue(until(lambda:bool(results)))
            self.controller.cancel(Mode.CHAT);self.assertTrue(until(lambda:not self.controller.live))
        self.assertEqual([t.source for r in results for t in r.translations],['Jo: GG'])
        self.assertIn(shape,evidence[0])
        stats=self.controller.metrics.snapshot()
        self.assertEqual(stats['counts']['chat_decorations_filtered'],1)

    def test_blank_clear_cannot_resurrect_old_overlay_when_toggled(self):
        window=self.window();revision=self.controller._revision(Mode.DIALOG,0)
        window.receive(JobResult(Mode.DIALOG,0,(Translation('Old sentence.','舊的譯文','local','fixture'),),event_id=revision))
        revision=self.controller._revision(Mode.DIALOG,0)
        window.receive(JobResult(Mode.DIALOG,0,(),event_id=revision))
        window.toggle_overlay(Mode.DIALOG)
        self.assertEqual(window.overlay(Mode.DIALOG).text.toPlainText(),'')

    def test_guard_failure_never_falls_back_to_original_in_any_float_mode(self):
        window=self.window()
        for mode in Mode:
            failure=Translation('SECRET ORIGINAL','SECRET ORIGINAL','local','fixture',warning='validation failed')
            window.receive(JobResult(mode,0,(failure,)))
            self.assertEqual(window.pages[mode].target.toPlainText(),'')
            if mode!=Mode.REPLY:
                self.assertFalse(window.overlay(mode).isVisible())
                self.assertNotIn('SECRET ORIGINAL',window.overlay(mode).text.toPlainText())

    def test_stale_status_does_not_displace_pending_new_status(self):
        generation,token=self.controller._begin(Mode.DIALOG)
        self.controller.cancel(Mode.DIALOG)
        current=self.controller.generations[Mode.DIALOG]
        self.controller._status('dialog','新的狀態',current)
        self.controller._status('dialog','舊的狀態',generation)
        self.assertEqual(self.controller.take_status('dialog'),('dialog','新的狀態',current))

    def test_blank_event_invalidates_already_queued_translation(self):
        generation,token=self.controller._begin(Mode.DIALOG)
        old=self.controller._revision(Mode.DIALOG,generation)
        self.controller._publish(JobResult(Mode.DIALOG,generation,(Translation('First.','第一句','local','fixture'),),event_id=old))
        revision=self.controller._revision(Mode.DIALOG,generation)
        self.controller._publish(JobResult(Mode.DIALOG,generation,(),event_id=revision))
        result=self.controller.take_result(Mode.DIALOG)
        self.assertEqual(result.event_id,revision);self.assertFalse(result.translations)

    def test_target_cards_exclude_original_warning_and_confidence_labels(self):
        overlay=CardOverlay('裝備卡');self.windows.append(overlay)
        overlay.set_translations((Translation('SECRET ORIGINAL','中文譯文','local','fixture',ocr_confidence=.9),
                                  Translation('FAILED ORIGINAL','FAILED ORIGINAL','local','fixture',warning='bad')))
        self.assertEqual(overlay.text.toPlainText(),'中文譯文')
        labels=[label.text() for label in overlay.text.findChildren(QLabel)]
        self.assertEqual(labels,['中文譯文'])
        overlay.set_font(30);self.assertEqual(overlay.text.toPlainText(),'中文譯文')

    def test_blocked_ui_uses_one_notice_and_bounded_chat_payload(self):
        notices=[];self.controller.delivery.connect(notices.append,Qt.ConnectionType.DirectConnection)
        for i in range(150):
            self.controller._publish(JobResult(Mode.CHAT,0,(Translation(str(i),str(i),'local','fixture'),)))
        self.assertEqual(notices,[Mode.CHAT])
        result=self.controller.take_result(Mode.CHAT)
        self.assertEqual(len(result.translations),100)
        self.assertEqual([t.target for t in result.translations],[str(i) for i in range(50,150)])
        self.controller.cancel(Mode.CHAT)
        self.controller._publish(JobResult(Mode.CHAT,1,(Translation('new','新的','local','fixture'),)))
        self.assertEqual(len(self.controller.take_result(Mode.CHAT).translations),1)

    def test_capture_preview_is_shared_small_snapshot_and_notice_has_no_pixels(self):
        notices=[];self.controller.captured.connect(notices.append,Qt.ConnectionType.DirectConnection)
        frame=np.zeros((1200,2400,3),dtype=np.uint8)
        for _ in range(20):self.controller._capture_evidence(Mode.SCREEN,0,Cancellation(),frame,())
        self.assertEqual(notices,[None])
        snapshot=self.controller.take_capture()
        self.assertIs(snapshot,self.controller.latest_snapshot)
        self.assertLessEqual(len(snapshot.pixels),640*400*3)
        self.controller.cancel(Mode.SCREEN);self.assertIsNone(self.controller.latest_snapshot)

    def test_image_limit_is_checked_before_capture_and_only_one_owner(self):
        with patch('babelander.controller.capture') as capture:
            with self.assertRaises(ValueError):
                with self.controller._image(Region(0,0,5000,5000),Cancellation()):capture(None)
            capture.assert_not_called()
        first=Cancellation();second=Cancellation();entered=threading.Event();outcome=[]
        def competing():
            try:
                with self.controller._image(Region(0,0,20,20),second):entered.set()
            except Cancelled:outcome.append('cancelled')
        with self.controller._image(Region(0,0,20,20),first):
            worker=threading.Thread(target=competing);worker.start();time.sleep(.06)
            self.assertEqual(self.controller.image_active,1);self.assertFalse(entered.is_set())
            second.cancel();worker.join(1);self.assertEqual(outcome,['cancelled'])
        self.assertEqual(self.controller.image_active,0)

    def test_coordinator_admission_is_bounded_before_executor_submission(self):
        release=threading.Event();self.releases.append(release)
        for _ in range(8):self.controller._submit(Mode.SCREEN,0,Cancellation(),lambda *args:release.wait(3))
        self.controller._submit(Mode.SCREEN,0,Cancellation(),lambda *args:None)
        self.assertEqual(self.controller.metrics.snapshot()['counts']['coordinator_capacity'],1)
        release.set()

    def test_status_notifications_are_coalesced(self):
        notices=[];self.controller.status_delivery.connect(notices.append,Qt.ConnectionType.DirectConnection)
        for i in range(1000):self.controller._status('dialog',str(i),0)
        self.assertEqual(notices,['dialog'])
        self.assertEqual(self.controller.take_status('dialog'),('dialog','999',0))

    def test_cache_and_rule_hits_do_not_extend_model_idle_timer(self):
        self.engine.request('A complete sentence.',Mode.DIALOG,Cancellation())
        activity=self.engine.last_local_request
        time.sleep(.01)
        result=self.engine.request('A complete sentence.',Mode.DIALOG,Cancellation())
        self.assertTrue(result.cache_hit);self.assertEqual(result.backend_state,'cache');self.assertEqual(result.model_ms,0)
        self.engine.request('Do not enter the dungeon yet.',Mode.DIALOG,Cancellation())
        self.assertEqual(self.engine.last_local_request,activity)

    def test_stop_releases_idle_model_in_background_without_killing_other_client(self):
        self.engine.acquire_client('other');self.engine.request_release()
        time.sleep(.03);self.assertFalse(self.closed.is_set())
        self.engine.release_client('other');self.assertTrue(self.closed.wait(2))
        self.assertIsNone(self.engine.local.process)

    def test_immediate_restart_waits_for_old_model_exit_before_new_allocation(self):
        closing=threading.Event();release=threading.Event();entered=threading.Event();self.releases.append(release)
        self.engine.local.close=lambda:(closing.set(),release.wait(3))
        new_backend=SimpleNamespace(translate=lambda *args:(entered.set(),'完整中文譯文')[1],close=lambda:None)
        result=[]
        with patch('babelander.engine.LocalBackend',return_value=new_backend):
            self.engine.request_release();self.assertTrue(closing.wait(2))
            worker=threading.Thread(target=lambda:result.append(self.engine.request('A new complete sentence.',Mode.DIALOG,Cancellation())))
            worker.start();time.sleep(.06);self.assertFalse(entered.is_set())
            release.set();worker.join(2);self.assertTrue(entered.is_set());self.assertEqual(len(result),1)

    def test_one_cancelled_waiter_preserves_shared_model_request(self):
        entered=threading.Event();release=threading.Event();self.releases.append(release)
        def translate(system,text):entered.set();release.wait(3);return '完整中文譯文'
        self.engine.local.translate=translate
        tokens=[Cancellation(),Cancellation()];results=[]
        def request(token):
            try:results.append(self.engine.request('Shared complete sentence.',Mode.DIALOG,token).target)
            except Cancelled:results.append('cancelled')
        workers=[threading.Thread(target=request,args=(token,)) for token in tokens]
        workers[0].start();self.assertTrue(entered.wait(2));workers[1].start()
        self.assertTrue(until(lambda:len(next(iter(self.engine.pending.values())).clients)==2))
        tokens[0].cancel();self.engine.request_release();workers[0].join(1)
        self.assertFalse(self.closed.is_set());release.set();workers[1].join(2)
        self.assertCountEqual(results,['cancelled','完整中文譯文']);self.assertTrue(self.closed.wait(2))

    def test_telemetry_is_bounded_text_free_and_backend_timings_not_invented(self):
        metrics=Telemetry()
        for i in range(1000):metrics.add('capture',Mode.DIALOG,capture_ms=i)
        report=metrics.snapshot();self.assertEqual(len(report['recent']),128)
        self.assertEqual(report['counts']['capture'],1000);self.assertTrue(report['timings']['capture_ms']['p95']>900)
        self.assertIsNone(report['ttft_ms']);self.assertIsNone(report['prefill_ms']);self.assertIsNone(report['decode_ms'])
        self.assertFalse(report['text_or_images_retained'])

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(PipelineTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    from babelander import __version__
    report={'version':__version__,'passed':result.wasSuccessful(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'qt_platform':APP.platformName(),'real_desktop_capture':False,'real_model':False,'paid_api':False,
            'scope':'Synthetic concurrency/resource-policy tests. No game recall/quality or native allocation bound assertion.',
            'details':[{'test':str(test),'traceback':error} for test,error in result.failures+result.errors]}
    (Path(__file__).resolve().parent/'test-results/pipeline.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
