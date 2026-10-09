"""Equipment lifecycle/Qt checks; offscreen with controlled OCR/backend delays."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import tempfile
import threading
import time
import unittest
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from babelander.types import Mode,Cancellation,OCRLine,Translation,Region,JobResult
from babelander.settings import Settings,save_settings,load_settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.controller import Controller
from babelander.window import MainWindow
from babelander.equipment_layout import equipment_blocks,capture_layout,decoration_on_rule,equipment_decoration,solid_gem_shape,colors,contrast,readable_color
from babelander.equipment_overlay import EquipmentOverlay,fitted_text
from babelander.layout import OCRBlock
from babelander.types import EquipmentSlot
from babelander.windows import physical_region,logical_region,place_physical
from PySide6.QtCore import QRect
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QPushButton
from unittest.mock import Mock
from babelander.engine import Engine
from babelander.equipment_fast_rules import numeric_field,slot_field,level_restriction
from babelander.equipment_lexicon import EquipmentDictionary
from babelander.glossary import Dictionary,Entry

APP=QApplication(['Equipment offscreen checks'])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/msjh.ttc')
ROI=Region(100,80,400,420)

def until(predicate,seconds=3,qt=False):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:
        if qt:APP.processEvents()
        time.sleep(.005)
    return bool(predicate())

def line(text,y=20,confidence=.99,x=20,w=180):
    return OCRLine(text,((x,y),(x+w,y),(x+w,y+22),(x,y+22)),confidence)

class Backend:
    def __init__(self):
        self.calls=[];self.entered=threading.Event();self.release=threading.Event()
        self.block=False;self.cooperative=False
    def request(self,text,mode,token):
        token.check();self.calls.append(text)
        if self.block and len(self.calls)==1:
            self.entered.set()
            deadline=time.monotonic()+4
            while not self.release.wait(.01) and time.monotonic()<deadline:
                if self.cooperative:token.check()
        token.check()
        return Translation(text,'完整中文譯文','local','test')
    def acquire_client(self,*args):pass
    def release_client(self,*args):pass
    def request_release(self):pass
    def close(self):self.release.set()
    def join(self):pass
    def maybe_unload(self):return False

class EquipmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.settings=Settings(hotkeys={});self.store=Store(self.root);self.engine=Backend()
        self.controller=Controller(self.engine,self.store,self.settings)
        self.captures=0;self.ocr_calls=0;self.results=[];self.windows=[];self.widgets=[]
        self.lines=[line('Ancient blade.')]
        self.controller.ocr=SimpleNamespace(recognize=self.recognize,recover_equipment=lambda image,lines,token,on_retry=None,on_reserved=None:lines)
        self.controller.result.connect(self.results.append,Qt.ConnectionType.DirectConnection)
        self.cp=patch('babelander.controller.capture',side_effect=self.capture);self.cp.start()
    def tearDown(self):
        self.engine.release.set()
        for window in self.windows:window.close()
        for widget in self.widgets:widget.close()
        self.controller.close();self.controller.join();APP.processEvents()
        self.cp.stop();self.store.close();self.temp.cleanup()
    def image(self):
        image=np.full((420,400,3),28,np.uint8)
        image[1:4]=(12,70,200);image[24:38,30:180]=(180,220,245)
        return image
    def capture(self,region):self.captures+=1;return self.image()
    def recognize(self,image,token):self.ocr_calls+=1;token.check();return self.lines
    def start(self):self.controller.submit_region(Mode.EQUIPMENT,ROI)
    def window(self):
        window=MainWindow(self.controller,self.store,self.settings,KeyVault(self.root),self.root)
        self.windows.append(window);return window
    def overlay(self):
        blocks=equipment_blocks(self.image(),self.lines)
        widget=EquipmentOverlay();self.widgets.append(widget)
        widget.set_translations([Translation(b.text,'譯文','local','test') for b in blocks],capture_layout(ROI,self.image(),blocks))
        return widget
    def test_single_capture_ocr_and_no_monitor(self):
        self.start();self.assertTrue(until(lambda:bool(self.results)))
        time.sleep(.12);self.assertEqual((self.captures,self.ocr_calls),(1,1))
        self.assertFalse(self.controller.live or self.controller.capture_streams)
        layout=self.results[0].equipment_layout;self.assertEqual(layout.region,ROI)
        self.assertEqual(len(layout.pixels),400*420*3)
        self.assertFalse(any(isinstance(v,np.ndarray) for v in vars(layout).values()))
    def test_recovered_number_reaches_snapshot_and_layout_once(self):
        retry=[]
        def recover(image,lines,token,on_retry=None,on_reserved=None):
            retry.append(1);token.check();on_retry(1,1)
            return lines+[line('7',20,x=300,w=20)]
        self.controller.ocr.recover_equipment=recover
        self.start();self.assertTrue(until(lambda:bool(self.results)))
        self.assertEqual((self.captures,self.ocr_calls,len(retry)),(1,1,1))
        self.assertIn('7',[l.text for l in self.controller.latest_snapshot.lines])
        self.assertIn('7',[s.literal for s in self.results[0].equipment_layout.slots])
    def test_cancel_during_recovery_does_not_publish(self):
        entered=threading.Event()
        def recover(image,lines,token,on_retry=None,on_reserved=None):
            token.cancel();entered.set();token.check()
        self.controller.ocr.recover_equipment=recover
        self.start();self.assertTrue(entered.wait(1));time.sleep(.03)
        self.assertFalse(self.results);self.assertFalse(self.engine.calls)
    def test_screen_capture_never_invokes_equipment_recovery(self):
        self.controller.ocr.recover_equipment=lambda *a:(_ for _ in ()).throw(AssertionError('screen must not retry numeric fields'))
        self.controller.submit_region(Mode.SCREEN,ROI)
        self.assertTrue(until(lambda:bool(self.results)));self.assertEqual(self.results[0].mode,Mode.SCREEN)
    def test_monitor_rejected_before_work(self):
        generation=self.controller.generations[Mode.EQUIPMENT]
        with self.assertRaisesRegex(ValueError,'單次'):self.controller.monitor(Mode.EQUIPMENT,ROI)
        self.assertEqual(generation,self.controller.generations[Mode.EQUIPMENT]);self.assertEqual(self.captures,0)
    def test_manual_text_does_not_invent_overlay(self):
        self.controller.submit_text(Mode.EQUIPMENT,'Old blade.')
        self.assertTrue(until(lambda:bool(self.results)))
        self.assertIsNone(self.results[0].equipment_layout);self.assertEqual(self.captures,0)
        window=self.window();window.receive(self.results[0])
        self.assertFalse(window.overlay(Mode.EQUIPMENT).isVisible())
        self.assertIn('框選',window.pages[Mode.EQUIPMENT].ocr_note.text())
    def test_slow_model_does_not_repeat_ocr(self):
        self.engine.block=True;self.start();self.assertTrue(self.engine.entered.wait(1))
        time.sleep(.12);self.assertEqual((self.captures,self.ocr_calls),(1,1))
        self.engine.release.set();self.assertTrue(until(lambda:bool(self.results)))
    def test_cancel_suppresses_late_output(self):
        self.engine.block=True;self.start();self.assertTrue(self.engine.entered.wait(1))
        self.controller.cancel(Mode.EQUIPMENT);self.engine.release.set();self.controller.join()
        self.assertEqual(self.results,[])
    def test_second_selection_supersedes_first(self):
        self.engine.block=True;self.start();self.assertTrue(self.engine.entered.wait(1))
        self.lines=[line('Second blade.')];self.start();self.engine.release.set()
        self.assertTrue(until(lambda:bool(self.results)));self.controller.join()
        self.assertEqual(len(self.results),1);self.assertEqual(self.results[0].translations[0].source,'Second blade.')
    def test_remove_source_glyphs_preserve_decorations_without_mutating_frame(self):
        image=self.image();original=image.copy()
        layout=capture_layout(ROI,image,[OCRBlock(tuple(self.lines))])
        clean=np.frombuffer(layout.pixels,np.uint8).reshape(image.shape)
        self.assertTrue(np.all(clean[18:44,18:202]==28))
        self.assertTrue(np.array_equal(clean[:10],image[:10]))
        self.assertTrue(np.array_equal(image,original))
    def test_two_columns_keep_original_coordinates(self):
        lines=[line('Damage: 12',50,x=20,w=120),line('Armor: 20',50,x=230,w=140),
               line('Level: 10',90,x=20,w=100),line('Health: 35',90,x=230,w=140)]
        blocks=equipment_blocks(self.image(),lines);layout=capture_layout(ROI,self.image(),blocks)
        self.assertEqual(len(blocks),4)
        left,right=layout.slots[:2];self.assertEqual((left.bounds[0],right.bounds[0]),(20,230))
        self.assertLess(left.bounds[2],right.bounds[0]);self.assertLess(left.bounds[3],90)
    def test_full_conditional_paragraph(self):
        lines=[line('If health is below 30%,',20,w=220),line('gain +12% movement speed.',52,w=260),
               line('Otherwise, gain +3% armor.',84,w=260)]
        blocks=equipment_blocks(self.image(),lines);self.assertEqual(len(blocks),1)
        self.assertIn('Otherwise',blocks[0].inference_text)
        self.assertEqual(capture_layout(ROI,self.image(),blocks).slots[0].source_bounds,(20,20,280,106))
    def test_title_color_splits_description(self):
        image=self.image();image[64:77,30:180]=240
        blocks=equipment_blocks(image,[line('Old Lantern',20),line('A dented lantern.',60)])
        self.assertEqual(len(blocks),2)
        layout=capture_layout(ROI,image,blocks)
        self.assertEqual(layout.slots[0].color,(245,220,180));self.assertEqual(layout.slots[1].color,(240,240,240))
    def test_missing_outside_overlapping_positions_rejected(self):
        for lines in ([OCRLine('Missing',(),.99)],[line('Outside',x=390)], [line('One',20),line('Two',25)]):
            with self.subTest(lines=lines),self.assertRaises(ValueError):
                capture_layout(ROI,self.image(),[OCRBlock((item,)) for item in lines])
        with self.assertRaises(ValueError):capture_layout(Region(0,0,100,40),self.image(),[OCRBlock(tuple(self.lines))])
    def test_complete_text_wraps_and_fits(self):
        slot=EquipmentSlot((10,10,70,30),(10,10,150,90),(255,255,255),24)
        text='完整保留這段裝備效果，並且可以在原欄位換行。'
        layout,size=fitted_text(text,slot)
        self.assertIsNotNone(layout);self.assertEqual(layout.text(),text)
        self.assertLessEqual(layout.boundingRect().height(),80);self.assertLessEqual(size,24)
    def test_overflow_is_hidden_without_truncation_or_relocation(self):
        widget=self.overlay();data=widget.layout_data;geometry=widget.geometry()
        widget.set_translations([Translation('source','超長譯文'*2000,'local','test')],data)
        self.assertFalse(widget.renderable);self.assertEqual(widget.draw_items,[])
        self.assertEqual(widget.geometry(),geometry);self.assertIn('完整',widget.render_warning)
    def test_unreliable_paragraph_does_not_show_partial_card(self):
        widget=self.overlay();widget.set_translations([Translation('source','','local','test',warning='review')],widget.layout_data)
        self.assertFalse(widget.renderable);self.assertIn('核對',widget.render_warning)
    def test_overlay_exact_roi_target_only_and_passthrough(self):
        widget=self.overlay();widget.show();APP.processEvents()
        self.assertEqual(widget.geometry(),QRect(100,80,400,420))
        self.assertEqual((widget.grab().width(),widget.grab().height()),(400,420))
        self.assertEqual(widget.text.toPlainText(),'譯文');self.assertTrue(widget.transparent_input)
    def test_clear_releases_layout_pixels_and_text(self):
        widget=self.overlay();widget.set_text('')
        self.assertIsNone(widget.layout_data);self.assertTrue(widget.image.isNull())
        self.assertEqual(widget.translations,());self.assertEqual(widget.draw_items,[])
    def test_old_detached_geometry_is_ignored(self):
        widget=self.overlay();geometry=widget.geometry()
        widget.restore_state({'x':500,'y':300,'width':750,'height':600})
        widget.adjust_geometry();widget.set_font(30);self.assertEqual(widget.geometry(),geometry)
    def test_single_shot_controls_no_monitor_drag_or_persisted_geometry(self):
        window=self.window();page=window.pages[Mode.EQUIPMENT]
        self.assertFalse(hasattr(page,'monitor_button'))
        texts=[b.text() for b in page.findChildren(QPushButton)]
        self.assertIn('框選裝備卡',texts);self.assertIn('取消／還原',texts)
        self.assertNotIn('恢復浮層互動',texts);self.assertNotIn('浮層設定',texts)
        window.overlay(Mode.EQUIPMENT);self.assertNotIn(Mode.EQUIPMENT,window.overlay_timers)
    def test_selection_submits_once_and_restore_cannot_revive_stale_result(self):
        window=self.window()
        with patch.object(self.controller,'submit_region') as submit,patch.object(self.controller,'monitor') as monitor:
            window.region_selected(Mode.EQUIPMENT,ROI)
            submit.assert_called_once_with(Mode.EQUIPMENT,ROI,focus_guard=None);monitor.assert_not_called()
        self.start();self.assertTrue(until(lambda:bool(self.results),qt=True))
        result=self.results[0];window.receive(result);self.assertTrue(window.overlay(Mode.EQUIPMENT).renderable)
        window.stop(Mode.EQUIPMENT);window.receive(result);window.toggle_overlay(Mode.EQUIPMENT)
        self.assertFalse(window.overlay(Mode.EQUIPMENT).isVisible());self.assertIsNone(window.overlay(Mode.EQUIPMENT).layout_data)
    def test_negative_monitor_origin_and_dpi_inverse(self):
        for ratio in (1,1.5,2):
            screen=SimpleNamespace(name=lambda:'secondary',geometry=lambda:QRect(-1920,0,round(1920/ratio),round(1080/ratio)),devicePixelRatio=lambda:ratio)
            with patch('babelander.windows.monitor_rectangles',return_value={'secondary':(-1920,0,0,1080)}),patch('babelander.windows.QGuiApplication.screens',return_value=[screen]),patch('babelander.windows.QGuiApplication.platformName',return_value='windows'):
                region=physical_region(screen,QRect(40,60,200,180));chosen,logical=logical_region(region)
                self.assertIs(chosen,screen);self.assertEqual(logical,QRect(-1880,60,200,180))
    def test_native_placement_exact_pixels_no_activation_and_offscreen_isolation(self):
        native=Mock(return_value=True)
        def read(handle,pointer):
            pointer._obj.left=100;pointer._obj.top=80;pointer._obj.right=500;pointer._obj.bottom=500
            return True
        with patch('babelander.windows.ctypes.windll.user32.SetWindowPos',native),patch('babelander.windows.ctypes.windll.user32.GetWindowRect',side_effect=read):
            place_physical(SimpleNamespace(winId=lambda:123),ROI);native.assert_not_called()
            with patch('babelander.windows.QGuiApplication.platformName',return_value='windows'):
                place_physical(SimpleNamespace(winId=lambda:123),ROI)
        self.assertEqual(native.call_args.args[2:],(100,80,400,420,0x10))
    def test_native_position_mismatch_and_cross_monitor_roi_rejected(self):
        with patch('babelander.windows.QGuiApplication.platformName',return_value='windows'),patch('babelander.windows.ctypes.windll.user32.SetWindowPos',return_value=True),patch('babelander.windows.ctypes.windll.user32.GetWindowRect',return_value=False):
            with self.assertRaises(OSError):place_physical(SimpleNamespace(winId=lambda:123),ROI)
        with self.assertRaises(ValueError):logical_region(Region(750,20,100,100))
    def test_replacement_keeps_model_warm_but_explicit_stop_releases(self):
        self.start();self.assertTrue(until(lambda:bool(self.results)))
        with patch.object(self.engine,'request_release') as release:
            self.start();self.assertTrue(until(lambda:len(self.results)==2))
            release.assert_not_called()
            self.controller.cancel(Mode.EQUIPMENT);release.assert_called_once()
    def test_legacy_monitor_settings_ignored(self):
        (self.root/'settings.json').write_text(json.dumps({'equipment_scan_ms':200,'equipment_stable_ms':100,'dialog_scan_ms':100}),encoding='utf8')
        settings=load_settings(self.root);self.assertEqual(settings.dialog_scan_ms,100)
        self.assertFalse(hasattr(settings,'equipment_scan_ms'))
    def test_signed_affixes_are_separate_rows_and_keep_source_color(self):
        lines=[line('+ 132 Strength',50),line('+ 89 Vitality',76),line('+ 14% Critical Chance',102)]
        blocks=equipment_blocks(self.image(),lines);self.assertEqual(len(blocks),3)
        slots=capture_layout(ROI,self.image(),blocks).slots
        self.assertEqual([slot.bounds[1] for slot in slots],[50,76,102])
        self.assertTrue(all(slot.color==colors(self.image(),slot.source_bounds)[1] for slot in slots))
    def test_large_numeric_cell_not_merged_with_smaller_stat_label(self):
        lines=[OCRLine('721',((20,50),(95,50),(95,94),(20,94)),.99),line('Attack Power',60,x=95,w=120)]
        blocks=equipment_blocks(self.image(),lines);self.assertEqual([b.text for b in blocks],['721','Attack Power'])
    def test_numeric_cell_retains_original_pixels_and_size(self):
        self.lines=[line('721')];image=self.image()
        layout=capture_layout(ROI,image,equipment_blocks(image,self.lines))
        self.assertEqual(layout.pixels,image.tobytes());self.assertEqual(layout.slots[0].literal,'721')
        widget=EquipmentOverlay();self.widgets.append(widget)
        widget.set_translations([Translation('721','721','local','test')],layout)
        self.assertTrue(widget.renderable);self.assertEqual(widget.draw_items,[])
        widget.set_translations([Translation('721','722','local','test')],layout)
        self.assertFalse(widget.renderable)
    def test_small_ocr_padding_overlap_tolerated_but_draw_slots_separate(self):
        blocks=[OCRBlock((line('Legendary',20),)),OCRBlock((line('Artifact',40),))]
        layout=capture_layout(ROI,self.image(),blocks)
        self.assertLess(layout.slots[0].bounds[3],layout.slots[1].bounds[1])
    def test_only_tiny_low_confidence_letter_on_long_rule_filtered(self):
        image=self.image();image[230,40:360]=150
        mark=OCRLine('B',((30,223),(42,223),(42,237),(30,237)),.57)
        self.assertTrue(decoration_on_rule(image,mark))
        self.assertFalse(decoration_on_rule(self.image(),mark))
        self.assertFalse(decoration_on_rule(image,replace_line:=OCRLine('1',mark.box,.57)))
        self.assertFalse(decoration_on_rule(image,OCRLine('B',mark.box,.9)))
        ignored=[];blocks=equipment_blocks(image,[mark,line('Damage: 12',250)],ignored.append)
        self.assertEqual(ignored,[mark]);self.assertEqual(len(blocks),1)
    def test_type_level_and_duplicate_sockets_stay_in_original_rows(self):
        lines=[line('Two-Handed Sword',20),line('Item Level 90',50),line('Empty Socket',100),line('Empty Socket',130)]
        self.assertEqual(len(equipment_blocks(self.image(),lines)),4)
    def test_signed_and_uncolonized_fields_preserve_exact_values(self):
        for source,target in [('+ 132 Strength','+132 力量'),('+ 14% Critical Chance','+14% 暴擊率'),
                              ('Item Level 90','物品等級 90'),('Sell Price: 56,320','售價：56,320')]:
            self.assertEqual(numeric_field(source,Dictionary([])),target)
        self.assertIsNone(numeric_field('+ 132 Strength if injured',Dictionary([])))
        self.assertIsNone(numeric_field('+ 132 Unknown Field',Dictionary([])))
    def test_signed_rule_honors_complete_override_and_rejects_partial(self):
        self.assertEqual(numeric_field('+ 132 Strength',Dictionary([Entry('Strength','強度')])),'+132 強度')
        self.assertIsNone(numeric_field('+ 14% Critical Chance',Dictionary([Entry('Chance','機率')])))
    def test_known_stat_fields_are_exact_and_bypass_model(self):
        engine=Engine(self.settings,self.store,KeyVault(self.root),self.root)
        engine.local=SimpleNamespace(translate=lambda *args:(_ for _ in ()).throw(AssertionError('model must not run')),close=lambda:None)
        try:
            for source,target in [('Critical Chance: 18%','暴擊率：18%'),('Critical Damage: +36.0%','暴擊傷害：+36.0%'),
                                  ('Durability: 130 / 130','耐久度：130 / 130'),('Damage: 2,904.1','傷害：2,904.1'),
                                  ('+ 132 Strength','+132 力量'),('+ 14% Critical Chance','+14% 暴擊率'),
                                  ('Item Level 90','物品等級 90'),('721','721')]:
                self.assertEqual(engine.request(source,Mode.EQUIPMENT,Cancellation()).target,target)
            self.store.save_term('Critical Chance','致命一擊機率','equipment')
            self.assertEqual(engine.request('Critical Chance: 18%',Mode.EQUIPMENT,Cancellation()).target,'致命一擊機率：18%')
        finally:engine.close();engine.join()
    def test_stat_rule_rejects_unknown_labels_extra_clauses_and_partial_overrides(self):
        dictionary=Dictionary([])
        for source in ('Mystery Stat: 18%','Damage: 125 unless poisoned','Durability: 130 / 130 while equipped'):
            self.assertIsNone(numeric_field(source,dictionary))
        self.assertIsNone(numeric_field('Critical Chance: 18%',Dictionary([Entry('Chance','機率')])))

    def test_bright_and_mid_tone_backgrounds_have_readable_semantic_colors(self):
        for background in ((187,220,231),(241,235,230),(110,110,110),(20,28,34)):
            for preferred in ((230,190,111),(229,185,98),(134,202,231),(211,215,217)):
                color=readable_color(preferred,background)
                self.assertGreaterEqual(contrast(color,background[::-1]),4.5)
        image=np.full((420,400,3),230,np.uint8);image[55:67,30:150]=35
        layout=capture_layout(ROI,image,[OCRBlock((line('+ 132 Strength',50),))])
        self.assertEqual(layout.slots[0].color,(35,35,35))
    def test_vertical_underscore_art_is_preserved_but_horizontal_text_not_filtered(self):
        tall=OCRLine('_',((260,50),(271,50),(271,75),(260,75)),.99)
        horizontal=OCRLine('_',((20,50),(45,50),(45,61),(20,61)),.4)
        self.assertTrue(equipment_decoration(tall,[tall]))
        self.assertFalse(equipment_decoration(horizontal,[horizontal]))
        self.assertFalse(equipment_decoration(OCRLine('+',tall.box,.4),[]))
        image=self.image();image[50:75,260:271]=(80,100,150)
        blocks=equipment_blocks(image,[tall,line('Damage: 12',100)])
        clean=np.frombuffer(capture_layout(ROI,image,blocks).pixels,np.uint8).reshape(image.shape)
        self.assertTrue(np.array_equal(clean[50:75,260:271],image[50:75,260:271]))
    def test_socket_circle_requires_shape_and_adjacent_socket_label(self):
        mark=OCRLine('O',((20,100),(40,100),(40,120),(20,120)),.95)
        socket=line('Empty Socket',100,x=52,w=130)
        self.assertTrue(equipment_decoration(mark,[mark,socket]))
        for other in (line('Damage: 10',100,x=52),line('Empty Socket',150,x=52),line('Empty Socket',100,x=220)):
            self.assertFalse(equipment_decoration(mark,[mark,other]))
        self.assertFalse(equipment_decoration(OCRLine('0',mark.box,.95),[socket]))
    def test_heading_and_rarity_not_merged_when_same_font_and_color(self):
        lines=[line('Old Lantern',20),line('Legendary',50),line('Lantern',80),line('Item Level 90',110)]
        self.assertEqual([b.text for b in equipment_blocks(self.image(),lines)],[l.text for l in lines])
    def test_paragraph_does_not_jump_over_intervening_atomic_field(self):
        lines=[line('Forged by the artisan',20),line('Item Level 90',50),line('and blessed by sunlight.',80)]
        blocks=equipment_blocks(self.image(),lines)
        self.assertEqual(len(blocks),3)
        capture_layout(ROI,self.image(),blocks)
    def test_empty_horizontal_ocr_padding_tolerated_and_slots_do_not_overlap(self):
        image=np.full((420,400,3),28,np.uint8)
        a=line('Damage: 12',50,x=20,w=130);b=line('Armor: 20',50,x=145,w=130)
        blocks=[OCRBlock((a,)),OCRBlock((b,))]
        layout=capture_layout(ROI,image,blocks)
        self.assertLess(layout.slots[0].bounds[2],layout.slots[1].bounds[0])
        image[55:65,145:150]=240
        with self.assertRaises(ValueError):capture_layout(ROI,image,blocks)
    def test_large_horizontal_overlap_rejected_even_if_empty(self):
        image=np.full((420,400,3),28,np.uint8)
        with self.assertRaises(ValueError):capture_layout(ROI,image,[OCRBlock((line('First',50,x=20,w=180),)),OCRBlock((line('Second',50,x=130,w=150),))])
    def test_vertical_ocr_padding_does_not_shift_next_row_sideways(self):
        image=np.full((420,400,3),28,np.uint8)
        blocks=[OCRBlock((line('Legendary',20,x=23,w=93),)),OCRBlock((line('Dagger',40,x=22,w=76),))]
        layout=capture_layout(ROI,image,blocks)
        self.assertEqual([slot.bounds[0] for slot in layout.slots],[23,22])
    def test_level_prohibition_retains_before_and_does_not_accept_other_relations(self):
        self.assertEqual(level_restriction('Do not equip this item before level 97.',Dictionary([])),'未達等級 97 前，請勿裝備此物品。')
        self.assertEqual(level_restriction("Don't equip this item before level 20",Dictionary([])),'未達等級 20 前，請勿裝備此物品。')
        for source in ('Equip this item before level 20.','Do not equip this item after level 20.',
                       'Do not equip this item before level 20 unless injured.','Do not equip this item before level 20. Deal 10 damage.'):
            self.assertIsNone(level_restriction(source,Dictionary([])))
        self.assertIsNone(level_restriction('Do not equip this item before level 97.',Dictionary([Entry('this item','神聖裝備')])))

    def test_centered_duration_wrap_stays_one_complete_effect(self):
        lines=[line('Attacks slow enemies for 4',50,x=50,w=300),line('seconds.',80,x=160,w=80)]
        blocks=equipment_blocks(self.image(),lines)
        self.assertEqual(len(blocks),1);self.assertIn('4\nseconds.',blocks[0].text)
        slot=capture_layout(ROI,self.image(),blocks).slots[0]
        self.assertEqual(slot.alignment,'center');self.assertEqual(slot.bounds[2],350)

    def test_numeric_peers_keep_label_columns_out_of_paragraphs(self):
        lines=[line('Attack',50,w=70),line('18',50,x=300,w=40),line('Defense',80,w=80),line('27',80,x=300,w=40),line('No special effect.',110,w=180)]
        self.assertEqual(len(equipment_blocks(self.image(),lines)),5)

    def test_socket_and_equipment_part_effects_remain_separate(self):
        for texts in [('Ruby socket','Sapphire socket','Prismatic socket'),('Weapon: +18% magic damage','Armor: +12% cold resistance','Jewelry: +9% maximum health')]:
            lines=[line(t,50+i*28) for i,t in enumerate(texts)]
            self.assertEqual(len(equipment_blocks(self.image(),lines)),3)

    def test_all_short_headings_split_from_their_own_descriptions(self):
        lines=[line('First heading',20),line('First description.',50),line('Second heading',110),line('Second description.',140)]
        image=self.image();image[20:42,20:200]=(90,160,230);image[50:72,20:200]=220
        image[110:132,20:200]=(180,120,80);image[140:162,20:200]=220
        self.assertEqual(len(equipment_blocks(image,lines)),4)

    def test_red_green_and_purple_fields_are_not_recolored(self):
        for rgb in ((220,90,110),(90,205,120),(180,130,235)):
            image=self.image();image[55:65,35:150]=rgb[::-1]
            slot=capture_layout(ROI,image,[OCRBlock((line('+18% Critical Chance',50),))]).slots[0]
            self.assertEqual(slot.color,rgb)

    def test_small_thin_text_keeps_opaque_color_not_antialias_shade(self):
        image=self.image();image[55:65,35:140]=(225,210,200);image[58:62,70:95]=(250,235,225)
        self.assertEqual(colors(image,(20,50,200,72))[1],(225,235,250))

    def test_small_gold_highlight_does_not_recolor_gray_paragraph(self):
        image=self.image();image[53:68,30:160]=(180,180,180);image[53:68,170:190]=(20,190,250)
        self.assertEqual(colors(image,(20,50,200,72))[1],(180,180,180))

    def test_solid_diamond_removed_but_real_digits_and_hollow_shapes_not(self):
        import cv2
        image=self.image();quad=np.array([[100,60],[130,90],[100,120],[70,90]],np.int32)
        cv2.fillConvexPoly(image,quad,(180,140,220))
        mark=OCRLine('4',tuple(map(tuple,quad)),.6)
        self.assertTrue(solid_gem_shape(image,mark))
        self.assertFalse(solid_gem_shape(image,OCRLine('4',mark.box,.99)))
        hollow=self.image();cv2.polylines(hollow,[quad],True,(180,140,220),3)
        self.assertFalse(solid_gem_shape(hollow,mark))
        digits=self.image();cv2.putText(digits,'4',(78,110),cv2.FONT_HERSHEY_SIMPLEX,1.4,(240,240,240),2)
        self.assertFalse(solid_gem_shape(digits,mark))

    def test_performance_bar_preserved_without_leaving_source_glyphs(self):
        image=self.image();image[77:84,20:350]=(100,150,200)
        image[53:70,24:65]=240
        layout=capture_layout(ROI,image,[OCRBlock((line('Accuracy',50,w=100),))])
        backdrop=np.frombuffer(layout.pixels,np.uint8).reshape(image.shape)
        self.assertTrue(np.array_equal(backdrop[77:84,20:350],image[77:84,20:350]))
        self.assertFalse(np.any(backdrop[53:70,24:65]==240))

    def test_slot_effect_rule_preserves_part_sign_stat_and_overrides(self):
        self.assertEqual(slot_field('Armor: +12% cold resistance',Dictionary([])),'防具：+12% 冰冷抗性')
        self.assertEqual(slot_field('Jewelry: -9 maximum health',Dictionary([])),'飾品：-9 最大生命值')
        self.assertEqual(slot_field('Weapon: +18% magic damage',Dictionary([Entry('magic damage','法術傷害')])),'武器：+18% 法術傷害')
        for text in ('Weapon: +18% magic damage unless poisoned','Armor: +12% mystery stat'):
            self.assertIsNone(slot_field(text,Dictionary([])))
        self.assertIsNone(slot_field('Weapon: +18% magic damage',Dictionary([Entry('magic','秘法')])) )

    def test_socket_colors_keep_or_and_and_do_not_guess_unknown_colors(self):
        self.assertEqual(slot_field('Fits: blue or white sockets',Dictionary([])),'適用插槽：藍色或白色')
        self.assertEqual(slot_field('Fits: red and green sockets',Dictionary([])),'適用插槽：紅色及綠色')
        self.assertIsNone(slot_field('Fits: orange sockets',Dictionary([])))
        self.assertIsNone(slot_field('Fits: blue sockets unless damaged',Dictionary([])))
        self.assertIsNone(slot_field('Fits: blue sockets',Dictionary([Entry('blue','蒼藍')])) )

    def test_interface_active_label_does_not_corrupt_active_in_sentences(self):
        dictionary=EquipmentDictionary(Dictionary([]))
        self.assertEqual(list(dictionary.protect('ACTIVE')[1].values()),['主動'])
        protected,mapping=dictionary.protect('Do not remove while the shield is active.')
        self.assertIn('active',protected);self.assertNotIn('主動',mapping.values())
        self.assertEqual(list(EquipmentDictionary(Dictionary([Entry('ACTIVE','啟動技')])).protect('ACTIVE')[1].values()),['啟動技'])

    def test_full_width_colon_and_general_level_keep_exact_numeric_values(self):
        self.assertEqual(numeric_field('Level： 17',Dictionary([])),'等級：17')
        self.assertEqual(numeric_field('Quality: +7.5%',Dictionary([])),'品質：+7.5%')

    def test_known_name_parts_generalize_and_respect_user_names(self):
        engine=Engine(self.settings,self.store,KeyVault(self.root),self.root)
        engine.local=SimpleNamespace(translate=lambda *a:(_ for _ in ()).throw(AssertionError('known nouns must not call model')),close=lambda:None)
        try:
            for source,target in [('Runed weapon','符文武器'),('Bronze Guard','青銅守衛'),('Iron Pack','鐵背包'),('Steel spear','鋼長矛'),('Rare burst carbine','稀有點放卡賓槍')]:
                self.assertEqual(engine.request(source,Mode.EQUIPMENT,Cancellation()).target,target)
            self.store.save_term('Runed weapon','刻印神器','equipment')
            self.assertEqual(engine.request('Runed weapon',Mode.EQUIPMENT,Cancellation()).target,'刻印神器')
        finally:engine.close();engine.join()

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EquipmentTests))
    report={'passed':result.wasSuccessful(),'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'real_desktop_capture':False}
    from babelander import __version__
    path=Path('test-results/equipment-checks-a'+__version__.split('a')[-1]+'.json');path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report,indent=2),encoding='utf8')
    raise SystemExit(not result.wasSuccessful())
