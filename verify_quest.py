"""Quest lifecycle, raw numeric pixels, semantic grouping and glossary checks."""
import json,time,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from verify_equipment import EquipmentTests, APP, ROI, line, until
from babelander.types import Mode, Cancellation, Translation, OCRLine
from babelander.quest_layout import quest_blocks,numeric_lines,LITERAL,label_rule
from babelander.equipment_layout import capture_layout
from babelander.equipment_overlay import EquipmentOverlay
from babelander.engine import Engine
from babelander.security import KeyVault
from PySide6.QtWidgets import QPushButton
from PySide6.QtGui import QImage,QPainter,QFont,QFontDatabase,QColor

class QuestTests(unittest.TestCase):
    setUp=EquipmentTests.setUp;tearDown=EquipmentTests.tearDown
    capture=EquipmentTests.capture;recognize=EquipmentTests.recognize;image=EquipmentTests.image;window=EquipmentTests.window
    def start(self):self.controller.submit_region(Mode.QUEST,ROI)
    def test_single_capture_ocr_and_immutable_roi(self):
        self.start();self.assertTrue(until(lambda:bool(self.results)))
        time.sleep(.06);self.assertEqual((self.captures,self.ocr_calls),(1,1))
        self.assertEqual(self.results[0].equipment_layout.region,ROI)
        self.assertFalse(self.controller.live or self.controller.capture_streams)
    def test_monitor_rejected_before_work(self):
        with self.assertRaisesRegex(ValueError,'單次'):self.controller.monitor(Mode.QUEST,ROI)
        self.assertEqual(self.captures,0)
    def test_slow_translation_never_recaptures(self):
        self.engine.block=True;self.start();self.assertTrue(self.engine.entered.wait(1))
        time.sleep(.06);self.assertEqual((self.captures,self.ocr_calls),(1,1))
        self.engine.release.set();self.assertTrue(until(lambda:bool(self.results)))
    def test_cancel_suppresses_late_output(self):
        self.engine.block=True;self.start();self.assertTrue(self.engine.entered.wait(1))
        self.controller.cancel(Mode.QUEST);self.engine.release.set();self.controller.join();self.assertFalse(self.results)
    def test_new_selection_supersedes_old(self):
        self.engine.block=True;self.start();self.assertTrue(self.engine.entered.wait(1))
        self.lines=[line('New objective.')];self.start();self.engine.release.set()
        self.assertTrue(until(lambda:bool(self.results)));self.controller.join()
        self.assertEqual(len(self.results),1);self.assertEqual(self.results[0].translations[0].source,'New objective.')
    def test_manual_text_requires_roi_for_overlay(self):
        self.controller.submit_text(Mode.QUEST,'Find the gate.')
        self.assertTrue(until(lambda:bool(self.results)))
        self.assertEqual(self.captures,0);self.assertIsNone(self.results[0].equipment_layout)
        window=self.window();window.receive(self.results[0]);self.assertFalse(window.overlay(Mode.QUEST).renderable)
    def test_controls_no_drag_timer_or_monitor(self):
        window=self.window();page=window.pages[Mode.QUEST]
        texts=[b.text() for b in page.findChildren(QPushButton)]
        self.assertTrue(hasattr(page,'once_button'));self.assertFalse(hasattr(page,'monitor_button'))
        self.assertIn('取消／還原',texts);self.assertNotIn('浮層設定',texts);self.assertNotIn('恢復浮層互動',texts)
        self.assertIsInstance(window.overlay(Mode.QUEST),EquipmentOverlay);self.assertNotIn(Mode.QUEST,window.overlay_timers)
    def test_stop_clears_backdrop_and_cannot_revive_result(self):
        window=self.window();self.start();self.assertTrue(until(lambda:bool(self.results),qt=True))
        result=self.results[0];window.receive(result);self.assertTrue(window.overlay(Mode.QUEST).renderable)
        window.stop(Mode.QUEST);window.receive(result)
        self.assertIsNone(window.overlay(Mode.QUEST).layout_data);self.assertFalse(window.overlay(Mode.QUEST).isVisible())
    def test_low_confidence_prose_still_blocked(self):
        self.lines=[line('Do not open the gate.',confidence=.52)];self.start()
        self.assertTrue(until(lambda:bool(self.results)));self.assertFalse(self.engine.calls)
        self.assertTrue(self.results[0].translations[0].warning)
    def test_low_confidence_literal_stays_raw_pixels(self):
        self.lines=[line('01:30',confidence=.52)];self.start();self.assertTrue(until(lambda:bool(self.results)))
        layout=self.results[0].equipment_layout
        self.assertEqual(layout.slots[0].literal,'01:30')
        self.assertTrue(np.array_equal(np.frombuffer(layout.pixels,np.uint8).reshape(420,400,3),self.image()))
    def test_title_and_description_not_merged(self):
        lines=[line('Disable the Turrets',20),line('Disable the turrets without damaging the reactor.',50)]
        self.assertEqual(len(quest_blocks(self.image(),lines)),2)
    def test_narrative_wrap_keeps_conditions(self):
        lines=[line('If the guard returns,',20),line('do not enter the dungeon.',48)]
        self.assertEqual(len(quest_blocks(np.full((420,400,3),28,np.uint8),lines)),1)
    def test_progress_and_headings_remain_independent(self):
        lines=[line('Objectives',20),line('Find the scouts.',48),line('2 / 4',77)]
        self.assertEqual(len(quest_blocks(np.full((420,400,3),28,np.uint8),lines)),3)
    def test_overlapping_numeric_fragments_join_without_guessing(self):
        lines=[line('1／',20,x=40,w=56),line('4',24,x=93,w=26)]
        result=numeric_lines(np.full((420,400,3),28,np.uint8),lines)
        self.assertEqual([l.text for l in result],['1/4']);self.assertEqual(result[0].confidence,.99)
    def test_real_slash_pixels_distinguish_214_from_2_over_4(self):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/arial.ttf')
        from equipment_game_fixtures import Canvas
        c=Canvas(180,90,(20,27,36),(133,220,171),(245,205,125))
        c.text('2 / 4',30,50,20);c.p.end()
        frame=np.frombuffer(c.image.bits(),np.uint8).reshape(90,c.image.bytesPerLine())[:,:540].reshape(90,180,3).copy()
        box=((23,27),(88,27),(88,57),(23,57))
        repaired=numeric_lines(frame,[OCRLine('214',box,.91)])[0]
        self.assertEqual(repaired.text,'2/4')
    def test_vertical_digit_one_never_changed_to_slash(self):
        frame=np.full((420,400,3),28,np.uint8);frame[24:40,58:60]=240
        result=numeric_lines(frame,[line('1',20,x=50,w=25)])
        self.assertEqual(result[0].text,'1')
    def test_unknown_labels_and_user_glossary_do_not_use_exact_rule(self):
        self.assertIsNone(label_rule('Accept the invitation',{}));self.assertIsNone(label_rule('Accept',{'[GL0]':'採用'}))
        self.assertEqual(label_rule('Objectives:',{}),'任務目標：')
    def test_exact_labels_skip_model_and_user_term_wins(self):
        engine=Engine(self.settings,self.store,KeyVault(self.root),self.root)
        engine.local=SimpleNamespace(translate=lambda *a:(_ for _ in ()).throw(AssertionError('label must skip model')),close=lambda:None)
        try:
            self.assertEqual(engine.request('Objectives',Mode.QUEST,Cancellation()).target,'任務目標')
            self.store.save_term('Objectives','目標清單','quest')
            self.assertEqual(engine.request('Objectives',Mode.QUEST,Cancellation()).target,'目標清單')
        finally:engine.close();engine.join()
    def test_echo_retry_is_bounded_and_unknown_text_not_hardcoded(self):
        calls=[]
        def translate(system,text):calls.append((system,text));return text if len(calls)==1 else '未知任務'
        engine=Engine(self.settings,self.store,KeyVault(self.root),self.root)
        engine.local=SimpleNamespace(translate=translate,close=lambda:None)
        try:
            result=engine.request('An Unknown Quest',Mode.QUEST,Cancellation())
            self.assertEqual(result.target,'未知任務');self.assertEqual(len(calls),2)
        finally:engine.close();engine.join()
    def test_unreliable_translation_blocks_whole_overlay(self):
        window=self.window();widget=window.overlay(Mode.QUEST)
        blocks=quest_blocks(self.image(),self.lines)
        widget.set_translations([Translation(self.lines[0].text,'','local','test',warning='需核對')],capture_layout(ROI,self.image(),blocks))
        self.assertFalse(widget.renderable);self.assertFalse(widget.isVisible())

if __name__=='__main__':
    from babelander import __version__
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(QuestTests))
    Path(f"test-results/quest-unit-a{__version__.split('a')[-1]}.json").write_text(json.dumps({'passed':result.wasSuccessful(),'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'real_desktop_capture':False},indent=2),encoding='utf8')
    raise SystemExit(not result.wasSuccessful())
