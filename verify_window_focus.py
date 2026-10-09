"""Foreground policies and real controller races; offscreen, fake Win32/backend."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json,tempfile,threading,time,unittest
import numpy as np
from PySide6.QtWidgets import QApplication
from babelander.window_focus import (WindowInfo,WindowBinding,WindowFocus,FocusState,FocusGuard,FocusCancellation,
                                     choose_binding,evaluate,rebase_region)
from babelander.types import Region,Mode,Cancellation,Cancelled,OCRLine,JobResult,Translation
from babelander.settings import Settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.controller import Controller
from babelander.window import MainWindow

APP=QApplication(['Foreground checks offscreen'])
TARGET=WindowInfo(100,123,100,(0,0,800,600),(0,0,800,620),monitor=1,dpi=96,monitor_bounds=(-1920,-1080,1920,1080))
BINDING=WindowBinding.from_info(TARGET)
ROI=Region(30,40,400,100)

class FakeWindows:
    def __init__(self):self.target=TARGET;self.front=TARGET;self.windows=[TARGET];self.reads=0
    def info(self,hwnd):self.reads+=1;return self.target if self.target and hwnd==self.target.hwnd else None
    def foreground(self):self.reads+=1;return self.front
    def enumerate(self):return self.windows

class NativePolicyTests(unittest.TestCase):
    def test_active_and_away(self):
        self.assertEqual(evaluate(BINDING,TARGET,TARGET),FocusState.ACTIVE)
        self.assertEqual(evaluate(BINDING,TARGET,replace(TARGET,pid=999,owner=200)),FocusState.AWAY)
    def test_null_foreground_is_away(self):self.assertEqual(evaluate(BINDING,TARGET,None),FocusState.AWAY)
    def test_owned_popup_is_active(self):self.assertEqual(evaluate(BINDING,TARGET,replace(TARGET,hwnd=101)),FocusState.ACTIVE)
    def test_same_process_different_root_pauses(self):self.assertEqual(evaluate(BINDING,TARGET,replace(TARGET,hwnd=102,owner=102)),FocusState.AWAY)
    def test_minimized_hidden_cloaked(self):
        for field,state in (('minimized',FocusState.MINIMIZED),('visible',FocusState.AWAY),('cloaked',FocusState.AWAY)):
            value=False if field=='visible' else True
            self.assertEqual(evaluate(BINDING,replace(TARGET,**{field:value}),TARGET),state)
    def test_destroyed_or_reused_pid_is_invalid(self):
        for target in (None,replace(TARGET,pid=456),replace(TARGET,owner=300)):
            self.assertEqual(evaluate(BINDING,target,TARGET),FocusState.INVALID)
    def test_moved_and_resized_require_reselect(self):
        for rect in ((20,20,820,620),(0,0,1024,768)):
            self.assertEqual(evaluate(BINDING,replace(TARGET,client=rect),TARGET),FocusState.MOVED)
    def test_picker_own_process_is_skipped(self):
        own=replace(TARGET,pid=os.getpid(),hwnd=500)
        self.assertEqual(choose_binding([own,TARGET],ROI,os.getpid()),BINDING)
    def test_hidden_cloaked_minimized_shell_are_skipped(self):
        for ignored in (replace(TARGET,visible=False),replace(TARGET,cloaked=True),replace(TARGET,minimized=True),replace(TARGET,shell=True)):
            self.assertEqual(choose_binding([ignored,TARGET],ROI,os.getpid()),BINDING)
    def test_partial_other_window_cannot_bind_through_it(self):
        top=replace(TARGET,hwnd=200,pid=456,client=(0,0,100,80),outer=(0,0,100,80))
        self.assertIsNone(choose_binding([top,TARGET],ROI,os.getpid()))
    def test_roi_across_window_border_rejected(self):self.assertIsNone(choose_binding([TARGET],Region(780,50,80,30),os.getpid()))
    def test_binding_contains_only_identity_and_geometry(self):self.assertEqual(set(vars(BINDING)),{'hwnd','pid','owner','client','monitor','dpi','monitor_bounds'})
    def test_translation_preserves_client_offset_and_dimensions(self):
        moved=replace(TARGET,client=(60,90,860,690))
        binding,region=rebase_region(BINDING,moved,ROI)
        self.assertEqual(binding,WindowBinding.from_info(moved));self.assertEqual(region,Region(90,130,400,100))
    def test_negative_screen_coordinates_and_repeated_moves_do_not_drift(self):
        binding,region=BINDING,ROI
        for x,y in ((-1000,-400),(-700,-100),(0,0)):
            target=replace(TARGET,client=(x,y,x+800,y+600))
            binding,region=rebase_region(binding,target,region)
            self.assertEqual((region.x-x,region.y-y,region.width,region.height),(30,40,400,100))
        self.assertEqual(region,ROI)
    def test_rebase_rejects_resize_dpi_monitor_or_display_geometry_change(self):
        for target in (replace(TARGET,client=(0,0,900,600)),replace(TARGET,dpi=144),replace(TARGET,monitor=2),
                       replace(TARGET,monitor_bounds=(0,0,1024,768))):
            self.assertEqual(evaluate(BINDING,target,target),FocusState.MOVED)
            self.assertIsNone(rebase_region(BINDING,target,ROI))
    def test_rebase_rejects_offscreen_roi_or_bad_original_roi(self):
        self.assertIsNone(rebase_region(BINDING,replace(TARGET,client=(1800,0,2600,600)),ROI))
        self.assertIsNone(rebase_region(BINDING,TARGET,Region(780,0,100,30)))
    def test_rebase_never_rebinds_another_window_or_unavailable_target(self):
        for target in (None,replace(TARGET,hwnd=200),replace(TARGET,pid=456),replace(TARGET,owner=200),
                       replace(TARGET,visible=False),replace(TARGET,minimized=True),replace(TARGET,cloaked=True)):
            self.assertIsNone(rebase_region(BINDING,target,ROI))
    def test_rebase_requires_known_monitor_and_dpi(self):
        for binding in (replace(BINDING,monitor=0),replace(BINDING,dpi=0),replace(BINDING,monitor_bounds=None)):
            self.assertIsNone(rebase_region(binding,TARGET,ROI))
    def test_guard_loss_latches_and_new_guard_recovers(self):
        api=FakeWindows();focus=WindowFocus(api);guard=FocusGuard(focus,BINDING)
        self.assertTrue(guard());api.front=None;self.assertFalse(guard());api.front=TARGET
        self.assertFalse(guard());self.assertTrue(FocusGuard(focus,BINDING)())
    def test_guarded_token_cancelled_on_loss(self):
        api=FakeWindows();guard=FocusGuard(WindowFocus(api),BINDING);token=FocusCancellation(guard)
        token.check();api.front=None
        with self.assertRaises(Cancelled):token.check()
        self.assertTrue(token.cancelled())
    def test_api_error_invalid_not_active(self):
        api=FakeWindows();api.info=lambda hwnd:(_ for _ in ()).throw(OSError('read failure'))
        self.assertEqual(WindowFocus(api).state(BINDING),FocusState.INVALID)
    def test_offscreen_has_no_native_focus_reader(self):
        focus=WindowFocus();self.assertFalse(focus.enabled);self.assertIsNone(focus.bind(ROI))

class FocusPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.settings=Settings(hotkeys={},stable_ms=0,dialog_scan_ms=100,scan_ms=300)
        self.store=Store(self.root);self.vault=KeyVault(self.root)
        self.engine=Engine(self.settings,self.store,self.vault,self.root)
        self.calls=[];self.closed=[];self.release=threading.Event();self.entered=threading.Event()
        self.engine.local=SimpleNamespace(translate=self.translate,close=lambda:self.closed.append(1))
        self.controller=Controller(self.engine,self.store,self.settings)
        self.window=MainWindow(self.controller,self.store,self.settings,self.vault,self.root)
        self.api=FakeWindows();self.window.window_focus=WindowFocus(self.api)
        self.window.regions[Mode.DIALOG]=ROI;self.window.window_bindings[Mode.DIALOG]=BINDING
        self.frames=0;self.regions_seen=[];self.ocr_calls=0;self.text='Before activating the beacon, gather everyone.'
        self.slow=False
        self.controller.ocr=SimpleNamespace(recognize=self.recognize,recover_equipment=lambda image,lines,token,*args:lines)
        self.capture_patch=patch('babelander.controller.capture',side_effect=self.capture);self.capture_patch.start()
    def tearDown(self):
        self.release.set();self.window.close();self.controller.join();APP.processEvents()
        self.capture_patch.stop();self.store.close();self.temp.cleanup()
    def translate(self,system,text):
        self.calls.append(text)
        if self.slow and len(self.calls)==1:self.entered.set();self.release.wait(4)
        return '完整中文譯文'
    def capture(self,region):
        self.frames+=1
        self.regions_seen.append(region)
        return np.full((100,400,3),min(250,20+self.frames),np.uint8)
    def recognize(self,frame,token,**kwargs):
        token.check();self.ocr_calls+=1
        return [OCRLine(self.text,((8,10),(380,10),(380,40),(8,40)),.99)]
    def until(self,predicate,timeout=2,events=True):
        deadline=time.monotonic()+timeout
        while not predicate() and time.monotonic()<deadline:
            if events:APP.processEvents()
            time.sleep(.005)
        return bool(predicate())
    def start(self):self.window.toggle_monitor(Mode.DIALOG)
    def away(self):self.api.front=None;self.window.check_window_focus()
    def back(self):self.api.front=TARGET;self.window.check_window_focus()
    def test_capture_stops_and_overlay_clears_while_away(self):
        self.start();self.assertTrue(self.until(lambda:self.frames>=2))
        overlay=self.window.overlay(Mode.DIALOG);overlay.set_text('上一句');overlay.show()
        self.away();self.assertTrue(self.until(lambda:not self.controller.capture_streams))
        count=self.frames;time.sleep(.2);APP.processEvents()
        self.assertEqual(count,self.frames);self.assertFalse(overlay.isVisible());self.assertFalse(overlay.text.toPlainText())
        self.assertIn(Mode.DIALOG,self.window.monitoring);self.assertIn(Mode.DIALOG,self.window.focus_paused)
        self.assertIn('自動暫停',self.window.pages[Mode.DIALOG].status.text())
    def test_resume_new_generation_and_new_capture(self):
        self.start();self.assertTrue(self.until(lambda:self.frames>=1));generation=self.controller.generations[Mode.DIALOG]
        self.away();self.assertTrue(self.until(lambda:not self.controller.capture_streams));count=self.frames
        self.text='The bridge cannot be crossed until morning.';self.back()
        self.assertTrue(self.until(lambda:self.frames>count));self.assertGreater(self.controller.generations[Mode.DIALOG],generation)
        self.assertNotIn(Mode.DIALOG,self.window.focus_paused)
    def test_manual_stop_during_pause_never_auto_resumes(self):
        self.start();self.assertTrue(self.until(lambda:self.frames>=1));self.away();self.window.stop(Mode.DIALOG)
        self.assertTrue(self.until(lambda:not self.controller.capture_streams));count=self.frames;self.back();APP.processEvents()
        self.assertEqual(count,self.frames);self.assertNotIn(Mode.DIALOG,self.window.monitoring);self.assertFalse(self.window.focus_timer.isActive())
    def test_late_translation_cannot_restore_overlay(self):
        self.slow=True;self.start();self.assertTrue(self.until(self.entered.is_set))
        old=self.controller.generations[Mode.DIALOG];self.away();self.release.set()
        self.assertTrue(self.until(lambda:not self.controller.capture_streams))
        self.assertGreater(self.controller.generations[Mode.DIALOG],old)
        self.assertFalse(self.window.overlay(Mode.DIALOG).isVisible());self.assertFalse(self.window.pages[Mode.DIALOG].target.toPlainText())
    def test_guard_stops_worker_even_when_gui_poll_is_not_running(self):
        self.start();self.assertTrue(self.until(lambda:self.frames>=1));self.window.focus_timer.stop()
        self.api.front=None
        self.assertTrue(self.until(lambda:not self.controller.capture_streams,events=False))
        count=self.frames;time.sleep(.12);self.assertEqual(count,self.frames)
        self.assertTrue(self.window.focus_guards[Mode.DIALOG].interrupted.is_set())
    def test_quick_loss_and_return_still_restarts_generation(self):
        self.start();self.assertTrue(self.until(lambda:self.frames>=1));self.window.focus_timer.stop()
        old=self.controller.generations[Mode.DIALOG];guard=self.window.focus_guards[Mode.DIALOG]
        self.api.front=None;self.assertFalse(guard());self.api.front=TARGET;self.window.check_window_focus()
        self.assertGreater(self.controller.generations[Mode.DIALOG],old);self.assertIsNot(guard,self.window.focus_guards[Mode.DIALOG])
    def test_short_pause_does_not_request_model_unload(self):
        self.start();self.assertTrue(self.until(lambda:self.frames>=1));self.away()
        self.assertTrue(self.until(lambda:not self.controller.capture_streams));time.sleep(.06)
        self.assertFalse(self.engine.release_when_unused);self.assertFalse(self.closed)
    def test_minimized_pauses_and_restored_resumes(self):
        self.start();self.assertTrue(self.until(lambda:self.frames>=1));self.api.target=replace(TARGET,minimized=True)
        self.window.check_window_focus();self.assertIn(Mode.DIALOG,self.window.focus_paused)
        self.api.target=TARGET;self.back();self.assertNotIn(Mode.DIALOG,self.window.focus_paused)
    def test_destroyed_window_never_restarts(self):
        self.start();self.api.target=None;self.window.check_window_focus()
        self.assertNotIn(Mode.DIALOG,self.window.monitoring);self.assertIn('重新框選',self.window.pages[Mode.DIALOG].status.text())
        self.api.target=TARGET;self.back();self.assertNotIn(Mode.DIALOG,self.window.monitoring)
    def move(self,x=30,y=30):
        self.api.target=replace(TARGET,client=(x,y,x+800,y+600));self.api.front=self.api.target
        self.window.check_window_focus();self.window.focus_timer.stop()
    def settle(self,mode=Mode.DIALOG):
        self.assertTrue(self.until(lambda:not self.controller.working(mode)))
        relocation,at=self.window.focus_moves[mode]
        self.window.focus_moves[mode]=(relocation,at-.21)
        self.window.check_window_focus();self.window.focus_timer.stop()
    def test_moved_window_pauses_then_reads_translated_roi_with_new_guard(self):
        self.start();self.assertTrue(self.until(lambda:self.frames>=1));old=self.window.focus_guards[Mode.DIALOG]
        self.move();self.assertTrue(self.until(lambda:not self.controller.capture_streams))
        self.assertIn(Mode.DIALOG,self.window.monitoring);self.assertIn(Mode.DIALOG,self.window.focus_paused)
        self.assertEqual(self.window.regions[Mode.DIALOG],ROI);count=self.frames
        self.window.check_window_focus();self.assertEqual(self.frames,count)
        self.settle();self.assertTrue(self.until(lambda:self.frames>count))
        self.assertEqual(self.regions_seen[-1],Region(60,70,400,100))
        self.assertIsNot(old,self.window.focus_guards[Mode.DIALOG]);self.assertFalse(old())
    def test_changing_move_candidate_restarts_stability_wait(self):
        self.start();self.move();relocation,_=self.window.focus_moves[Mode.DIALOG]
        self.window.focus_moves[Mode.DIALOG]=(relocation,time.monotonic()-1)
        self.move(70,50);self.assertEqual(self.window.regions[Mode.DIALOG],ROI)
        self.settle();self.assertEqual(self.window.regions[Mode.DIALOG],Region(100,90,400,100))
    def test_resize_dpi_monitor_changes_stop_continuous_monitor(self):
        for target in (replace(TARGET,client=(0,0,900,600)),replace(TARGET,dpi=144),replace(TARGET,monitor=2)):
            self.api.target=TARGET;self.api.front=TARGET;self.window.window_bindings[Mode.DIALOG]=BINDING;self.start()
            self.api.target=target;self.window.check_window_focus()
            self.assertNotIn(Mode.DIALOG,self.window.monitoring);self.assertIn('重新框選',self.window.pages[Mode.DIALOG].status.text())
    def test_manual_stop_during_move_prevents_restart(self):
        self.start();self.move();self.window.stop(Mode.DIALOG)
        self.assertFalse(self.window.focus_moves);self.assertTrue(self.until(lambda:not self.controller.capture_streams))
        count=self.frames;self.window.check_window_focus();self.assertEqual(self.frames,count)
        self.assertNotIn(Mode.DIALOG,self.window.monitoring)
    def test_move_while_away_relocates_but_waits_for_foreground(self):
        self.start();self.away();self.move();self.api.front=None;self.settle()
        self.assertIn(Mode.DIALOG,self.window.focus_paused);self.assertEqual(self.window.regions[Mode.DIALOG],Region(60,70,400,100))
        self.api.front=self.api.target;self.window.check_window_focus()
        self.assertTrue(self.until(lambda:self.regions_seen and self.regions_seen[-1]==Region(60,70,400,100)))
    def test_late_result_from_before_move_cannot_show(self):
        self.slow=True;self.start();self.assertTrue(self.until(self.entered.is_set))
        self.move();self.release.set();self.assertTrue(self.until(lambda:not self.controller.live))
        APP.processEvents();self.assertFalse(self.window.overlay(Mode.DIALOG).isVisible())
        self.assertFalse(self.window.pages[Mode.DIALOG].target.toPlainText())
    def test_completed_card_move_removes_without_relocation_or_replay(self):
        self.equipment();self.window.capture_once(Mode.EQUIPMENT)
        self.assertTrue(self.until(lambda:self.window.pages[Mode.EQUIPMENT].target.toPlainText()))
        self.api.target=replace(TARGET,client=(30,30,830,630));self.window.check_window_focus()
        self.assertNotIn(Mode.EQUIPMENT,self.window.focus_modes);self.assertFalse(self.window.overlay(Mode.EQUIPMENT).isVisible())
        self.assertEqual(self.frames,1);self.assertEqual(self.window.regions[Mode.EQUIPMENT],ROI)
    def test_chat_move_updates_region_and_clears_old_log(self):
        self.window.regions[Mode.CHAT]=ROI;self.window.window_bindings[Mode.CHAT]=BINDING
        self.window.toggle_monitor(Mode.CHAT);self.window.chat_messages=['過期聊天']
        self.move();self.assertEqual(self.window.chat_messages,[]);self.settle(Mode.CHAT)
        self.assertEqual(self.window.regions[Mode.CHAT],Region(60,70,400,100))
    def test_worker_observes_move_even_before_gui_poll(self):
        self.start();self.assertTrue(self.until(lambda:self.frames>=1));self.window.focus_timer.stop()
        self.api.target=replace(TARGET,client=(30,30,830,630))
        self.assertTrue(self.until(lambda:not self.controller.capture_streams,events=False))
        count=self.frames;time.sleep(.12);self.assertEqual(self.frames,count)
    def test_new_move_work_waits_for_running_ocr_to_release_roi(self):
        entered=threading.Event();release=threading.Event()
        ordinary=self.controller.ocr.recognize
        def slow_ocr(frame,token):
            entered.set();release.wait(2);return ordinary(frame,token)
        self.controller.ocr.recognize=slow_ocr
        try:
            self.start();self.assertTrue(self.until(entered.is_set));self.move()
            relocation,at=self.window.focus_moves[Mode.DIALOG]
            self.window.focus_moves[Mode.DIALOG]=(relocation,at-1)
            count=self.frames;generation=self.controller.generations[Mode.DIALOG]
            for _ in range(5):self.window.check_window_focus()
            self.assertEqual(self.controller.generations[Mode.DIALOG],generation)
            self.assertEqual(self.window.regions[Mode.DIALOG],ROI);self.assertTrue(self.controller.working(Mode.DIALOG))
            release.set();self.settle();self.assertTrue(self.until(lambda:self.frames>count))
            self.assertEqual(self.window.regions[Mode.DIALOG],Region(60,70,400,100))
        finally:release.set()
    def test_move_back_to_original_resumes_without_coordinate_drift(self):
        self.start();self.move();self.api.target=TARGET;self.api.front=TARGET;self.window.check_window_focus()
        self.assertEqual(self.window.regions[Mode.DIALOG],ROI);self.assertFalse(self.window.focus_moves)
        self.assertNotIn(Mode.DIALOG,self.window.focus_paused)
    def test_stopped_binding_can_follow_move_on_manual_restart(self):
        self.api.target=replace(TARGET,client=(30,30,830,630));self.api.front=self.api.target;self.start()
        self.window.focus_timer.stop();self.assertEqual(self.frames,0);self.settle()
        self.assertTrue(self.until(lambda:self.regions_seen and self.regions_seen[-1]==Region(60,70,400,100)))
    def test_repeated_moves_leave_one_binding_and_no_pending_roi(self):
        self.start();self.assertTrue(self.until(lambda:self.frames>=1))
        for x,y in ((30,30),(70,50),(0,0))*4:
            self.move(x,y);self.settle()
            self.assertEqual(self.window.regions[Mode.DIALOG],Region(x+30,y+40,400,100))
        self.window.stop(Mode.DIALOG);self.assertTrue(self.until(lambda:not self.controller.live and not self.controller.capture_streams))
        self.assertFalse(self.window.focus_moves);self.assertEqual(self.controller.image_active,0)
    def test_start_while_away_waits_without_capture_or_model(self):
        self.api.front=None;self.start();time.sleep(.03)
        self.assertEqual(self.frames,0);self.assertFalse(self.calls);self.assertIn(Mode.DIALOG,self.window.focus_paused)
        self.back();self.assertTrue(self.until(lambda:self.frames>=1))
    def test_pause_status_not_overwritten_by_cancel_notice(self):
        self.start();self.away();APP.processEvents()
        self.assertIn('自動暫停',self.window.pages[Mode.DIALOG].status.text())
    def test_user_hidden_overlay_stays_hidden_after_return(self):
        self.window.overlay_hidden.add(Mode.DIALOG);self.start();self.assertTrue(self.until(lambda:self.frames>=1))
        self.away();self.back();self.assertTrue(self.until(lambda:self.frames>=2))
        self.assertIn(Mode.DIALOG,self.window.overlay_hidden);self.assertFalse(self.window.overlay(Mode.DIALOG).isVisible())
    def test_overlay_hotkey_cannot_reveal_paused_text(self):
        self.start();self.away();self.window.toggle_overlay(Mode.DIALOG)
        self.assertFalse(self.window.overlay(Mode.DIALOG).isVisible())
    def test_capture_focus_changes_mid_copy_does_not_reach_ocr(self):
        def changed(region):self.frames+=1;self.api.front=None;return np.zeros((100,400,3),np.uint8)
        self.capture_patch.stop();self.capture_patch=patch('babelander.controller.capture',side_effect=changed);self.capture_patch.start()
        self.start();self.assertTrue(self.until(lambda:self.frames>=1));self.assertEqual(self.ocr_calls,0)
    def test_region_selection_binds_without_activating_game(self):
        self.window.region_selected(Mode.DIALOG,ROI)
        self.assertEqual(self.window.window_bindings[Mode.DIALOG],BINDING)
        self.assertTrue(self.window.isMinimized());self.assertIn(Mode.DIALOG,self.window.monitoring)
    def test_ambiguous_region_binding_refuses_continuous_monitor(self):
        self.api.windows=[];self.window.region_selected(Mode.DIALOG,ROI)
        self.assertNotIn(Mode.DIALOG,self.window.monitoring);self.assertIn('重新框選',self.window.pages[Mode.DIALOG].status.text())
    def test_paused_mode_manual_text_cancels_resume_intent(self):
        self.start();self.away();self.window.pages[Mode.DIALOG].source.setPlainText('Fresh manual input.')
        self.window.translate_text(Mode.DIALOG);self.back()
        self.assertNotIn(Mode.DIALOG,self.window.monitoring);self.assertNotIn(Mode.DIALOG,self.window.focus_modes)
    def test_close_stops_foreground_timer(self):
        self.start();self.window.close();self.assertFalse(self.window.focus_timer.isActive())
    def equipment(self):
        self.window.regions[Mode.EQUIPMENT]=ROI;self.window.window_bindings[Mode.EQUIPMENT]=BINDING
    def test_one_shot_card_does_not_recapture_on_return(self):
        self.equipment();self.window.capture_once(Mode.EQUIPMENT)
        self.assertTrue(self.until(lambda:self.window.pages[Mode.EQUIPMENT].target.toPlainText()))
        self.assertEqual(self.frames,1);self.api.front=None;self.window.check_window_focus()
        self.assertFalse(self.window.overlay(Mode.EQUIPMENT).isVisible());self.back();APP.processEvents()
        self.assertEqual(self.frames,1);self.assertNotIn(Mode.EQUIPMENT,self.window.focus_modes)
    def test_initial_card_while_away_waits_for_first_capture_only(self):
        self.equipment();self.api.front=None;self.window.capture_once(Mode.EQUIPMENT)
        self.assertEqual(self.frames,0);self.assertIn(Mode.EQUIPMENT,self.window.focus_pending_once)
        self.back();self.assertTrue(self.until(lambda:self.window.pages[Mode.EQUIPMENT].target.toPlainText()))
        self.assertEqual(self.frames,1);self.api.front=None;self.window.check_window_focus();self.back()
        self.assertEqual(self.frames,1)
    def test_manual_cancel_initial_pending_card_prevents_first_capture(self):
        self.equipment();self.api.front=None;self.window.capture_once(Mode.EQUIPMENT)
        self.window.stop(Mode.EQUIPMENT);self.back();APP.processEvents();self.assertEqual(self.frames,0)
    def test_chat_pauses_and_clears_visible_log_before_fresh_session(self):
        self.window.regions[Mode.CHAT]=ROI;self.window.window_bindings[Mode.CHAT]=BINDING
        self.window.chat_messages=['上一段聊天'];self.window.toggle_monitor(Mode.CHAT)
        self.assertTrue(self.until(lambda:self.frames>=1));old=self.controller.generations[Mode.CHAT]
        self.away();self.assertEqual(self.window.chat_messages,[]);self.assertIn(Mode.CHAT,self.window.focus_paused)
        self.back();self.assertGreater(self.controller.generations[Mode.CHAT],old)
    def test_paused_model_still_unloads_after_existing_idle_timeout(self):
        self.start();self.assertTrue(self.until(lambda:self.frames>=1));self.away()
        self.assertTrue(self.until(lambda:not self.controller.capture_streams and not self.engine.pending))
        self.engine.local.process=SimpleNamespace(poll=lambda:None)
        self.engine.last_local_request=time.monotonic()-self.settings.idle_unload_seconds-1
        self.window.check_idle_model();self.assertTrue(self.closed)
    def test_failed_binding_cannot_start_unguarded_monitor(self):
        self.window.window_bindings.clear();self.start()
        self.assertNotIn(Mode.DIALOG,self.window.monitoring);self.assertEqual(self.frames,0)
        self.assertIn('重新框選',self.window.pages[Mode.DIALOG].status.text())
    def test_repeated_focus_cycles_do_not_accumulate_workers_or_roi(self):
        self.start();self.assertTrue(self.until(lambda:self.frames>=1))
        for _ in range(12):
            self.away()
            self.assertTrue(self.until(lambda:not self.controller.capture_streams and not self.controller.live))
            self.back()
            self.assertTrue(self.until(lambda:bool(self.controller.capture_streams)))
        self.away()
        self.assertTrue(self.until(lambda:not self.controller.capture_streams and not self.controller.live))
        self.assertEqual(self.controller.image_active,0);self.assertIsNone(self.controller.latest_snapshot)
        self.assertIn(Mode.DIALOG,self.window.monitoring)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(__import__('__main__')))
    report={'passed':result.wasSuccessful(),'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'qt_platform':'offscreen','foreground_api':'controlled fake','real_game':False,'model':'controlled fake','visible_windows':False,'hotkeys':False}
    Path('test-results/window-focus-unit.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    raise SystemExit(not result.wasSuccessful())
