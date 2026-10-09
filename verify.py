"""Regression suite for source-only v2; fake transports never contact APIs."""
from bootstrap import prepare
prepare()
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
import json
import sys
import tempfile
import threading
import time
import unittest

from babelander.settings import Settings,load_settings,save_settings
from babelander.types import Mode,Cancellation,Cancelled,Region,Translation,OCRLine
from babelander.layout import OCRBlock,card_blocks
from babelander.storage import Store
from babelander.security import KeyVault,crypt
from babelander.glossary import Dictionary,Entry,restore_terms
from babelander.engine import Engine
from babelander.scheduler import Scheduler
from babelander.validation import validate
from babelander.controller import Controller,new_chat_lines,chunks
from babelander.backends import CloudBackend,BackendError

ROOT = Path(__file__).resolve().parent


class CoreTests(unittest.TestCase):
    @staticmethod
    def line(text,x=0,y=0,width=420,height=20,confidence=.99):
        return OCRLine(text,((x,y),(x+width,y),(x+width,y+height),(x,y+height)),confidence)
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def engine(self, output='完整中文譯文'):
        engine = Engine(Settings(),self.store,KeyVault(self.root),self.root)
        calls = []
        def translate(system,text):
            calls.append((system,text))
            return output(system,text) if callable(output) else output
        engine.local = SimpleNamespace(translate=translate,close=lambda:None)
        self.addCleanup(lambda:(engine.close(),engine.join()))
        return engine,calls

    def test_settings_roundtrip_and_chat_remains_local(self):
        settings = Settings(providers={'chat':'azure','dialog':'google'})
        save_settings(self.root,settings)
        restored = load_settings(self.root)
        self.assertEqual(restored.provider(Mode.CHAT),'local')
        self.assertEqual(restored.provider(Mode.DIALOG),'google')
        self.assertFalse(any(name.endswith('_key') or name=='credentials' for name in json.loads((self.root/'settings.json').read_text())))

    def test_wrapped_conditions_and_otherwise_are_one_block(self):
        lines = [self.line('If health is below 30%,',y=0),self.line('gain +12% Movement Speed for 5 seconds.',y=28),self.line('Otherwise, gain +3% Fire Resistance.',y=56),self.line('Gain +50% Fire Resistance for 10 seconds.',y=84)]
        blocks = card_blocks(lines)
        self.assertEqual(len(blocks),2)
        self.assertEqual(blocks[0].lines,tuple(lines[:3]))
        engine,calls = self.engine('不應使用模型。')
        controller = Controller(engine,self.store,engine.settings)
        try:
            translated = controller._translate_blocks(Mode.EQUIPMENT,Cancellation(),blocks)
            self.assertEqual(len(calls),0)
            self.assertIn('否則',translated[0].target)
            self.assertIn('30%',translated[0].target)
            self.assertIn('+12%',translated[0].target)
            self.assertIn('+3%',translated[0].target)
            self.assertEqual(translated[0].source,blocks[0].text)
        finally:controller.close();controller.join()

    def test_columns_bullets_and_paragraph_gaps_remain_separate(self):
        lines = [self.line('Left first',x=0,y=0,width=180),self.line('Right first',x=380,y=0,width=180),
                 self.line('left continuation.',x=0,y=28,width=180),self.line('right continuation.',x=380,y=28,width=180),
                 self.line('• Independent effect',x=0,y=56,width=180),self.line('New paragraph',x=0,y=160,width=180)]
        blocks = card_blocks(lines)
        self.assertEqual([b.text for b in blocks],['Left first\nleft continuation.','Right first\nright continuation.','• Independent effect','New paragraph'])

    def test_same_baseline_fragments_join_without_crossing_columns(self):
        blocks = card_blocks([self.line('Fire',width=45),self.line('Resistance:',x=55,width=120),self.line('+50%',x=380,width=70)])
        self.assertEqual([b.text for b in blocks],['Fire Resistance:','+50%'])

    def test_orphan_otherwise_keeps_original_and_never_calls_backend(self):
        engine,calls = self.engine()
        controller = Controller(engine,self.store,engine.settings)
        try:
            result = controller._translate_blocks(Mode.EQUIPMENT,Cancellation(),card_blocks([self.line('Otherwise, gain +3% Fire Resistance.')]))[0]
            self.assertTrue(result.warning)
            self.assertEqual(result.target,'')
            self.assertFalse(calls)
        finally:controller.close();controller.join()

    def test_low_confidence_ocr_never_sends_to_cloud(self):
        engine,calls = self.engine()
        engine.settings.providers['equipment']='azure'
        cloud_calls=[]
        engine.cloud = SimpleNamespace(translate=lambda *args:cloud_calls.append(args))
        controller = Controller(engine,self.store,engine.settings)
        try:
            block = OCRBlock((self.line('Gain +50% Fire Resistance for 10 seconds.',confidence=.52),))
            result = controller._translate_blocks(Mode.EQUIPMENT,Cancellation(),[block])[0]
            self.assertEqual(result.target,'');self.assertEqual(result.source,block.text)
            self.assertIn('52%',result.warning)
            self.assertEqual(result.ocr_confidence,.52)
            self.assertFalse(cloud_calls)
            self.assertFalse(self.store.usage())
        finally:controller.close();controller.join()

    def test_long_condition_is_not_truncated_or_sent(self):
        engine,calls = self.engine()
        controller = Controller(engine,self.store,engine.settings)
        try:
            text='If health is below 30%, '+('preserve this condition and action. '*30)
            result=controller._translate_blocks(Mode.EQUIPMENT,Cancellation(),[OCRBlock((self.line(text),))])[0]
            self.assertEqual(result.target,'');self.assertEqual(result.source,text)
            self.assertIn('600',result.warning)
            self.assertFalse(calls)
        finally:controller.close();controller.join()

    def test_overlay_and_confidence_settings_roundtrip(self):
        settings=Settings(ocr_review_threshold=.82,overlays={'dialog':{'x':-1920,'y':400,'width':700,'height':260,'background':False}})
        save_settings(self.root,settings)
        loaded=load_settings(self.root)
        self.assertEqual(loaded.overlays,settings.overlays)
        self.assertEqual(loaded.ocr_review_threshold,.82)
        with self.assertRaises(ValueError):Settings(ocr_review_threshold=1.5).validate()
        with self.assertRaises(ValueError):Settings(overlays={'dialog':{'width':-1}}).validate()

    def test_time_quantities_accept_chinese_and_english_numerals(self):
        validate('我五分鐘後回來，請不要開始。','I will return in 5 minutes. Please do not start.',True)
        validate('我十五分鐘後回來。','I will return in 15 minutes.',True)
        validate('Wait five minutes.','等待 5 分鐘。')
        with self.assertRaises(ValueError):
            validate('我五分鐘後回來。','I will return in 50 minutes.',True)

    def test_past_never_accepts_experience_negation(self):
        for source in ('I have never crossed an ice field.','He has never crossed an ice field.','They had never crossed an ice field.'):
            for target in ('尚未穿越過冰原。','未曾穿越過冰原。','從未穿越過冰原。','沒有穿越過冰原。'):
                validate(source,target)

    def test_experience_negation_does_not_relax_commands_or_accept_future_word(self):
        for source,target in [('Never cross the ice field.','尚未穿越冰原。'),
                              ('Do not cross the ice field.','尚未穿越冰原。'),
                              ('They have never crossed it, but do not enter.','他們尚未穿越，請進入。'),
                              ('They have never crossed the ice field.','他們未來會穿越冰原。'),
                              ('They have never crossed the ice field.','他們穿越過冰原。')]:
            with self.assertRaises(ValueError):validate(source,target)

    def test_duration_units_and_common_negation_cannot_disappear(self):
        with self.assertRaises(ValueError):
            validate('Wait 5 minutes.','等待 5 秒。')
        with self.assertRaises(ValueError):
            validate('Do not leave the area.','離開此區域。')
        with self.assertRaises(ValueError):
            validate('請不要開始。','Please start.',True)
        validate('Do not leave the area.','請勿離開此區域。')
        validate('我五分鐘後回來，請不要開始。',"I'll be back in five minutes. Please don't start yet.",True)

    def test_hidpi_secondary_monitor_origin_not_scaled_twice(self):
        from PySide6.QtCore import QRect
        from babelander.windows import physical_region
        screen = SimpleNamespace(geometry=lambda:QRect(-2560,240,1280,720),name=lambda:'friendly name',devicePixelRatio=lambda:2.0)
        with patch('babelander.windows.monitor_rectangles',return_value={}):
            self.assertEqual(physical_region(screen,QRect(20,30,200,100)),Region(-2520,300,400,200))

    def test_replaced_generation_cannot_publish_or_write_history(self):
        from PySide6.QtCore import Qt
        entered,release = threading.Event(),threading.Event()
        def output(system,text):
            if text=='Old message.':
                entered.set();release.wait(3)
            return '舊訊息。' if text=='Old message.' else '新訊息。'
        engine,_ = self.engine(output)
        controller = Controller(engine,self.store,engine.settings)
        results,done = [],threading.Event()
        controller.result.connect(lambda r:(results.append(r),done.set()),Qt.ConnectionType.DirectConnection)
        try:
            controller.submit_text(Mode.DIALOG,'Old message.')
            self.assertTrue(entered.wait(2))
            controller.submit_text(Mode.DIALOG,'New message.')
            release.set()
            self.assertTrue(done.wait(3))
            self.assertEqual([r.text for r in results],['新訊息。'])
            self.assertEqual([r[1] for r in self.store.history()],['New message.'])
        finally:
            release.set();controller.close();controller.join()

    def test_card_inference_blocks_yield_to_queued_subtitle(self):
        entered,release = threading.Event(),threading.Event()
        order = []
        def output(system,text):
            order.append(text)
            if text=='Card first.':
                entered.set();release.wait(3)
            return '完整中文。'
        engine,_ = self.engine(output)
        controller = Controller(engine,self.store,engine.settings)
        pool = ThreadPoolExecutor(2)
        try:
            cards = pool.submit(controller._translate,Mode.EQUIPMENT,Cancellation(),['Card first.','Card second.'])
            self.assertTrue(entered.wait(2))
            subtitle = pool.submit(engine.request,'New subtitle.',Mode.DIALOG,Cancellation())
            deadline = time.monotonic()+2
            while time.monotonic()<deadline:
                with engine.lock:
                    queued = len(engine.pending)>=2
                if queued:break
                time.sleep(.005)
            self.assertTrue(queued)
            release.set();cards.result(3);subtitle.result(3)
            self.assertEqual(order,['Card first.','New subtitle.','Card second.'])
        finally:
            release.set();pool.shutdown();controller.close();controller.join()

    def test_blank_subtitle_clears_and_same_text_returns_after_blank(self):
        from PySide6.QtCore import Qt
        from babelander.types import OCRLine
        engine,_ = self.engine('等等我。')
        engine.settings.stable_ms = 0
        controller = Controller(engine,self.store,engine.settings)
        generation,token = controller._begin(Mode.DIALOG)
        controller.ocr = SimpleNamespace(recognize=lambda frame,t:[] if frame==0 else [OCRLine('Wait for me.',(),1.0)])
        results = []
        def receive(result):
            results.append(result)
            if len(results)==3:token.cancel()
        controller.result.connect(receive,Qt.ConnectionType.DirectConnection)
        frames = iter([1,0,1])
        frame_index = [0]
        def grab(region):
            deadline = time.monotonic()+2
            while len(results)<frame_index[0] and time.monotonic()<deadline:time.sleep(.005)
            frame_index[0] += 1
            return next(frames)
        try:
            with patch('babelander.controller.capture',side_effect=grab),patch('babelander.controller.signature',side_effect=lambda f:f),patch('babelander.controller.bright_signature',side_effect=lambda f:f),patch.object(controller,'_capture_evidence'),patch.object(token.event,'wait',side_effect=lambda delay:time.sleep(.02)):
                controller._monitor(Mode.DIALOG,generation,token,Region(0,0,100,40))
            self.assertEqual([r.text for r in results],['等等我。','','等等我。'])
        finally:
            controller.close();controller.join()

    def test_capture_evidence_immutable_bounded_and_stale_suppressed(self):
        import numpy as np
        from PySide6.QtCore import Qt
        from babelander.evidence import evidence
        frame = np.zeros((1200,2400,3),dtype=np.uint8)
        box = [[0,0],[100,0],[100,20],[0,20]]
        snapshot = evidence(Mode.SCREEN,0,frame,[OCRLine('Text',box,float('nan'))])
        self.assertLessEqual(len(snapshot.pixels),640*400*3)
        box[0][0] = 99; frame.fill(255)
        self.assertEqual(snapshot.lines[0].box[0][0],0)
        self.assertEqual(snapshot.lines[0].confidence,0)
        self.assertEqual(snapshot.pixels[0],0)
        engine,_ = self.engine(); controller = Controller(engine,self.store,engine.settings)
        received = []
        controller.captured.connect(received.append,Qt.ConnectionType.DirectConnection)
        try:
            controller._capture_evidence(Mode.SCREEN,0,Cancellation(),frame,[])
            controller.cancel(Mode.SCREEN)
            controller._capture_evidence(Mode.SCREEN,0,Cancellation(),frame,[])
            self.assertEqual(len(received),1)
        finally:controller.close();controller.join()

    def test_monitor_transient_capture_recovers_without_duplicate_request(self):
        import numpy as np
        from PySide6.QtCore import Qt
        from babelander.capture import CaptureUnavailable
        engine,calls = self.engine('等等我。'); engine.settings.stable_ms = 0
        controller = Controller(engine,self.store,engine.settings)
        generation,token = controller._begin(Mode.DIALOG)
        controller.ocr = SimpleNamespace(recognize=lambda frame,t:[self.line('Wait for me.')])
        results = []; errors = []
        controller.result.connect(lambda result:(results.append(result),token.cancel()),Qt.ConnectionType.DirectConnection)
        controller.failed.connect(lambda *args:errors.append(args),Qt.ConnectionType.DirectConnection)
        frame = np.zeros((40,100,3),dtype=np.uint8)
        try:
            real_wait = token.event.wait
            with patch('babelander.controller.capture',side_effect=[CaptureUnavailable('temporary'),frame]) as grab,patch.object(token.event,'wait',side_effect=lambda delay:False if delay==1 else real_wait(2)) as wait:
                controller._monitor(Mode.DIALOG,generation,token,Region(0,0,100,40))
            self.assertEqual(grab.call_count,2); self.assertEqual(len(results),1)
            self.assertEqual(len(calls),1); self.assertFalse(errors)
            self.assertEqual(wait.call_args_list[0].args,(1,))
        finally:controller.close();controller.join()

    def test_monitor_capture_retry_limit_and_cancel_wait(self):
        from PySide6.QtCore import Qt
        from babelander.capture import CaptureUnavailable
        engine,calls = self.engine(); controller = Controller(engine,self.store,engine.settings)
        errors = []; controller.failed.connect(lambda *args:errors.append(args),Qt.ConnectionType.DirectConnection)
        try:
            generation,token = controller._begin(Mode.DIALOG)
            with patch('babelander.controller.capture',side_effect=CaptureUnavailable('temporary')) as grab,patch.object(token.event,'wait',return_value=False) as wait:
                controller._monitor(Mode.DIALOG,generation,token,Region(0,0,100,40))
            self.assertEqual(grab.call_count,3); self.assertEqual(len(errors),1)
            self.assertEqual([c.args for c in wait.call_args_list],[(1,),(2,)])
            self.assertFalse(calls)
            generation,token = controller._begin(Mode.DIALOG); errors.clear()
            with patch('babelander.controller.capture',side_effect=CaptureUnavailable('temporary')) as grab,patch.object(token.event,'wait',side_effect=lambda delay:token.cancel()):
                controller._monitor(Mode.DIALOG,generation,token,Region(0,0,100,40))
            self.assertEqual(grab.call_count,1); self.assertFalse(errors)
        finally:controller.close();controller.join()

    def test_monitor_does_not_retry_translation_or_resource_failure(self):
        import numpy as np
        from PySide6.QtCore import Qt
        engine,_ = self.engine(); engine.settings.stable_ms = 0
        controller = Controller(engine,self.store,engine.settings)
        controller.ocr = SimpleNamespace(recognize=lambda frame,t:[self.line('Wait for me.')])
        errors = []; controller.failed.connect(lambda *args:errors.append(args),Qt.ConnectionType.DirectConnection)
        try:
            generation,token = controller._begin(Mode.DIALOG)
            with patch('babelander.controller.capture',return_value=np.zeros((40,100,3),dtype=np.uint8)) as grab,patch.object(engine,'request',side_effect=BackendError('service timeout')) as request:
                controller._monitor(Mode.DIALOG,generation,token,Region(0,0,100,40))
            self.assertGreaterEqual(grab.call_count,1); self.assertEqual(request.call_count,1)
            self.assertEqual(len(errors),1)
            generation,token = controller._begin(Mode.DIALOG); errors.clear()
            with patch('babelander.controller.capture',side_effect=RuntimeError('resource allocation failed')) as grab:
                controller._monitor(Mode.DIALOG,generation,token,Region(0,0,100,40))
            self.assertEqual(grab.call_count,1); self.assertEqual(len(errors),1)
        finally:controller.close();controller.join()

    def test_invalid_settings_do_not_overwrite_file(self):
        save_settings(self.root,Settings())
        before = (self.root/'settings.json').read_bytes()
        with self.assertRaises(ValueError):
            save_settings(self.root,Settings(scan_ms=0))
        self.assertEqual(before,(self.root/'settings.json').read_bytes())

    def test_subtitle_retries_when_identical_text_confidence_recovers(self):
        from PySide6.QtCore import Qt
        engine,calls = self.engine('等等我。');engine.settings.stable_ms = 0
        controller = Controller(engine,self.store,engine.settings)
        generation,token = controller._begin(Mode.DIALOG)
        controller.ocr = SimpleNamespace(recognize=lambda frame,t:[self.line('Wait for me.',confidence=.50 if frame==1 else .99)])
        results = []
        def receive(result):
            results.append(result)
            if len(results)==2:token.cancel()
        controller.result.connect(receive,Qt.ConnectionType.DirectConnection)
        frames=iter([1,2])
        frame_index = [0]
        def grab(region):
            deadline = time.monotonic()+2
            while len(results)<frame_index[0] and time.monotonic()<deadline:time.sleep(.005)
            frame_index[0] += 1
            return next(frames)
        try:
            with patch('babelander.controller.capture',side_effect=grab),patch('babelander.controller.signature',side_effect=lambda f:f),patch('babelander.controller.bright_signature',side_effect=lambda f:f),patch.object(controller,'_capture_evidence'),patch.object(token.event,'wait',side_effect=lambda delay:time.sleep(.02)):
                controller._monitor(Mode.DIALOG,generation,token,Region(0,0,100,40))
            self.assertEqual(len(results),2);self.assertTrue(results[0].translations[0].warning)
            self.assertFalse(results[1].translations[0].warning);self.assertEqual(results[1].text,'等等我。')
        finally:controller.close();controller.join()

    def test_presentation_changes_do_not_invalidate_paid_cache_or_reload_model(self):
        engine,_ = self.engine();engine.settings.providers['screen']='azure'
        calls=[]
        engine.cloud=SimpleNamespace(translate=lambda *args:(calls.append(args),'完整中文譯文')[1])
        first=engine.request('A complete sentence.',Mode.SCREEN,Cancellation())
        local=engine.local
        changed=replace(engine.settings,overlays={'dialog':{'x':100,'y':200,'width':700,'height':300,'background':False}},font_size=32,scan_ms=1200,monthly_limit=1)
        engine.reconfigure(changed)
        second=engine.request('A complete sentence.',Mode.SCREEN,Cancellation())
        self.assertTrue(second.cache_hit);self.assertEqual(len(calls),1);self.assertIs(engine.local,local)

    def test_specific_dictionary_scope_overrides_shared_case_variant(self):
        self.store.save_term('sunstone','日石','shared')
        self.store.save_term('SUNSTONE','曜石','equipment')
        engine,calls=self.engine()
        self.assertEqual(engine.request('sunstone',Mode.EQUIPMENT,Cancellation()).target,'曜石')
        self.assertEqual(engine.request('sunstone',Mode.DIALOG,Cancellation()).target,'日石')
        self.assertFalse(calls)

    def test_idle_unload_releases_only_idle_local_backend(self):
        from babelander.engine import Pending
        engine,_=self.engine();closed=[]
        engine.local=SimpleNamespace(process=object(),close=lambda:closed.append(True))
        engine.last_local_request=100;engine.settings.idle_unload_seconds=300
        self.assertFalse(engine.maybe_unload(399));self.assertFalse(closed)
        token=Cancellation();engine.pending['local']=Pending({token},provider='local')
        self.assertFalse(engine.maybe_unload(500));self.assertFalse(closed)
        engine.pending.clear();engine.pending['cloud']=Pending(provider='azure')
        self.assertTrue(engine.maybe_unload(500));self.assertEqual(closed,[True])
        self.assertIn('cloud',engine.pending);self.assertIsNone(engine.local.process)

    def test_idle_unload_disabled_and_invalid_settings(self):
        engine,_=self.engine();engine.local.process=object();engine.settings.idle_unload_seconds=0
        self.assertFalse(engine.maybe_unload(100000))
        for invalid in (-1,3601,True):
            with self.assertRaises(ValueError):replace(Settings(),idle_unload_seconds=invalid).validate()

    def test_simplified_output_normalized_but_explicit_glossary_preserved(self):
        engine,_=self.engine('将在 10 秒后返回。')
        result=engine.request('We will return in 10 seconds.',Mode.DIALOG,Cancellation())
        self.assertEqual(result.target,'將在 10 秒後返回。')
        self.store.save_term('Player_007','将军','shared')
        engine.local.translate=lambda system,text:'[GL0] 将在 10 秒后返回。'
        result=engine.request('Player_007 will return in 10 seconds.',Mode.DIALOG,Cancellation())
        self.assertEqual(result.target,'将军 將在 10 秒後返回。')
        engine.settings.providers['dialog']='azure'
        engine.cloud=SimpleNamespace(translate=lambda *args:'将军 将在 10 秒后返回。')
        result=engine.request('Player_007 will return in 10 seconds.',Mode.DIALOG,Cancellation())
        self.assertEqual(result.target,'将军 將在 10 秒後返回。')

    def test_not_yet_entry_rule_preserves_command_and_refuses_partial_match(self):
        from babelander.semantic_rules import dialog_rule
        for source,target in (('Do not enter the dungeon yet.','暫時不要進入地牢。'),('Do not leave the area yet.','暫時不要離開區域。')):
            self.assertEqual(dialog_rule(source,Dictionary()),target)
        custom=Dictionary([Entry('dungeon','地下城')])
        self.assertEqual(dialog_rule('Do not enter the dungeon yet.',custom),'暫時不要進入地下城。')
        for source in ('Do not enter the dungeon yet unless we are ready.','Do not enter the dungeon yet. Otherwise, leave the area.'):
            self.assertIsNone(dialog_rule(source,Dictionary()))
    def test_reconfigure_does_not_attach_new_request_to_obsolete_pending_job(self):
        started,release=threading.Event(),threading.Event();self.addCleanup(release.set)
        def answer(system,text):
            started.set();release.wait(2);return '舊譯文。'
        engine,_=self.engine(answer);oldtoken=Cancellation()
        pool=ThreadPoolExecutor(2)
        old=pool.submit(engine.request,'A complete sentence.',Mode.SCREEN,oldtoken)
        try:
            self.assertTrue(started.wait(2))
            engine.reconfigure(replace(engine.settings,font_size=30))
            engine.local=SimpleNamespace(translate=lambda *args:'新譯文。',close=lambda:None)
            new=pool.submit(engine.request,'A complete sentence.',Mode.SCREEN,Cancellation())
            release.set()
            with self.assertRaises(Cancelled):old.result(2)
            self.assertEqual(new.result(2).target,'新譯文。')
            self.assertEqual(engine.request('A complete sentence.',Mode.SCREEN,Cancellation()).target,'新譯文。')
        finally:release.set();pool.shutdown()

    def test_dictionary_repeated_ids_explicit_override_and_token_collision(self):
        source = 'Meet Player_007. Tell Player_007 to wait. [GL0]'
        protected,mapping = Dictionary([Entry('Player_007','七號玩家')]).protect(source)
        self.assertNotIn('[GL0]',mapping)
        self.assertEqual(restore_terms(protected,mapping),source.replace('Player_007','七號玩家'))
        with self.assertRaises(ValueError):
            restore_terms(protected.replace('[GL1]',''),mapping)

    def test_user_term_cannot_replace_generated_gl_token(self):
        protected,mapping = Dictionary([Entry('long term','專名'),Entry('GL0','錯誤')]).protect('long term')
        self.assertEqual(restore_terms(protected,mapping),'專名')

    def test_stat_and_semantic_rules_do_not_use_model(self):
        engine,calls = self.engine()
        for mode,text,expected in (
            (Mode.EQUIPMENT,'Gain +50% Fire Resistance for 10 seconds.','獲得 +50% 火焰抗性，持續 10 秒。'),
            (Mode.DIALOG,'Meet Ranger_42 near Gate_9 at X:-89 Y:12.','請在 X:-89 Y:12（Gate_9 附近）與 Ranger_42 會合。'),
            (Mode.DIALOG,'Do not follow MAGE_09 unless MAGE_09 asks for help.','不要跟隨 MAGE_09，除非 MAGE_09 請求協助。'),
            (Mode.EQUIPMENT,'If health is below 30%, gain +12% movement speed for 10 seconds. Otherwise, gain +5% armor.',
             '若生命值低於 30%，獲得 +12% 移動速度，持續 10 秒；否則獲得 +5% 護甲。'),
        ):
            self.assertEqual(engine.request(text,mode,Cancellation()).target,expected)
        self.assertFalse(calls)

    def test_partial_conditions_do_not_hit_rule(self):
        from babelander.equipment_fast_rules import timed_bonus
        from babelander.semantic_rules import dialog_rule
        self.assertIsNone(timed_bonus('Gain +50% Fire Resistance for 10 seconds if injured.',Dictionary()))
        self.assertIsNone(dialog_rule('Meet Ranger_42 at X:12 Y:34. Do not attack.',Dictionary()))

    def test_numeric_only_and_missing_markers_hide_target_without_cache(self):
        engine,calls = self.engine('30%, +12%, 10')
        text = 'When health is below 30%, gain +12% speed for 10 seconds.'
        result = engine.request(text,Mode.EQUIPMENT,Cancellation())
        self.assertEqual(result.target,'');self.assertEqual(result.source,text)
        self.assertTrue(result.warning)
        engine.request(text,Mode.EQUIPMENT,Cancellation())
        self.assertEqual(len(calls),2)

    def test_identifier_restoration_rejects_missing_repetitions(self):
        engine,calls = self.engine('請 [GL0] 等待。')
        source = 'Ask Player_007 to wait. Do not leave Player_007 behind.'
        result = engine.request(source,Mode.DIALOG,Cancellation())
        self.assertEqual(result.target,'');self.assertEqual(result.source,source)
        self.assertTrue(result.warning)

    def test_persistent_cache_avoids_second_inference(self):
        engine,calls = self.engine()
        first = engine.request('Leave before sunset.',Mode.DIALOG,Cancellation())
        second = engine.request('Leave before sunset.',Mode.DIALOG,Cancellation())
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(len(calls),1)

    def test_chat_and_reply_never_persist_text_in_cache_or_history(self):
        engine,calls = self.engine(lambda system,text:'I will return.' if 'natural English' in system else '請稍候。')
        for mode,text in ((Mode.CHAT,'Wait for me.'),(Mode.REPLY,'等我回來。')):
            result = engine.request(text,mode,Cancellation())
            self.store.record(mode,result,1)
            self.assertTrue(engine.request(text,mode,Cancellation()).cache_hit)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM cache').fetchone()[0],0)
        self.assertFalse(self.store.history())

    def test_glossary_change_invalidates_cached_translation(self):
        engine,calls = self.engine(lambda system,text:'請 '+text.split()[0]+' 等待。')
        self.store.save_term('Player_007','七號玩家','dialog')
        result = engine.request('Player_007 wait.',Mode.DIALOG,Cancellation())
        self.assertIn('七號玩家',result.target)
        self.store.save_term('Player_007','自訂玩家','dialog')
        self.assertIn('自訂玩家',engine.request('Player_007 wait.',Mode.DIALOG,Cancellation()).target)
        self.assertEqual(len(calls),2)

    def test_concurrent_same_text_coalesces_once(self):
        started,release = threading.Event(),threading.Event()
        def output(system,text):
            started.set()
            self.assertTrue(release.wait(3))
            return '完整中文譯文'
        engine,calls = self.engine(output)
        self.addCleanup(release.set)
        with ThreadPoolExecutor(2) as pool:
            first = pool.submit(engine.request,'Wait for the guard.',Mode.DIALOG,Cancellation())
            self.assertTrue(started.wait(2))
            second = pool.submit(engine.request,'Wait for the guard.',Mode.DIALOG,Cancellation())
            deadline = time.monotonic()+2
            while time.monotonic()<deadline:
                with engine.lock:
                    count = len(next(iter(engine.pending.values())).clients)
                if count==2:
                    break
                time.sleep(.005)
            self.assertEqual(count,2)
            release.set()
            self.assertEqual(first.result(3).target,second.result(3).target)
        self.assertEqual(len(calls),1)

    def test_one_cancelled_subscriber_does_not_cancel_other(self):
        started,release = threading.Event(),threading.Event()
        def output(system,text):
            started.set();release.wait(3)
            return '完整中文譯文'
        engine,calls = self.engine(output)
        self.addCleanup(release.set)
        token = Cancellation()
        with ThreadPoolExecutor(2) as pool:
            first = pool.submit(engine.request,'Wait for the guard.',Mode.DIALOG,token)
            self.assertTrue(started.wait(2))
            second = pool.submit(engine.request,'Wait for the guard.',Mode.DIALOG,Cancellation())
            deadline = time.monotonic()+2
            while time.monotonic()<deadline:
                with engine.lock:
                    count = len(next(iter(engine.pending.values())).clients)
                if count==2:break
                time.sleep(.005)
            self.assertEqual(count,2)
            token.cancel()
            with self.assertRaises(Cancelled):first.result(1)
            release.set()
            self.assertEqual(second.result(3).target,'完整中文譯文')
        self.assertEqual(len(calls),1)

    def test_cache_is_bounded(self):
        translation = Translation('source','target','local','model')
        for index in range(1003):self.store.put(str(index),translation)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM cache').fetchone()[0],1000)
        self.assertIsNone(self.store.get('0'))

    def test_cache_lru_survives_equal_clock_backward_clock_and_restart(self):
        translation = Translation('source','target','local','model')
        with patch('babelander.storage.time.time',return_value=1):
            for index in range(1000):self.store.put(str(index),translation)
            self.assertIsNotNone(self.store.get('0'))
        self.store.close(); self.store = Store(self.root)
        with patch('babelander.storage.time.time',return_value=-100):
            self.store.put('new',translation)
        self.assertIsNone(self.store.get('1'))
        self.assertIsNotNone(self.store.get('0'))
        self.assertIsNotNone(self.store.get('new'))

    def test_cache_access_order_is_atomic_across_connections(self):
        translation = Translation('source','target','local','model')
        second = Store(self.root)
        try:
            self.store.put('first',translation); second.put('second',translation)
            self.store.get('first'); second.put('third',translation)
            self.assertEqual([row[0] for row in self.store.db.execute('SELECT key FROM cache ORDER BY touched')],['second','first','third'])
        finally:second.close()

    def test_history_clear_does_not_delete_terms(self):
        self.store.save_term('moonstone','月石','shared')
        self.store.record(Mode.QUEST,Translation('source','target','local','model'),1)
        self.store.clear_history()
        self.assertFalse(self.store.history())
        self.assertEqual(len(self.store.terms()),1)

    def test_dpapi_roundtrip_corruption_and_provider_binding(self):
        vault = KeyVault(self.root)
        vault.put('google','synthetic-test-key')
        self.assertEqual(vault.get('google'),'synthetic-test-key')
        self.assertNotIn(b'synthetic-test-key',vault.path('google').read_bytes())
        vault.path('azure').write_bytes(vault.path('google').read_bytes())
        with self.assertRaises(ValueError):vault.get('azure')
        vault.path('google').write_bytes(b'broken')
        with self.assertRaises(ValueError):vault.get('google')
        vault.delete('google')
        self.assertFalse(vault.has('google'))

    def test_key_path_rejects_escape(self):
        with self.assertRaises(ValueError):KeyVault(self.root).path('../secret')

    def test_malformed_cloud_payload_counts_attempt_only_and_never_retries(self):
        cloud=CloudBackend(Settings(),SimpleNamespace(get=lambda provider:'synthetic-key'),self.store)
        for provider,payload in (('google',{'data':{'translations':[]}}),('azure',[]),('deepl',{'translations':[{'text':None}]})):
            with self.subTest(provider=provider),patch('babelander.backends.requests.post',return_value=SimpleNamespace(status_code=200,json=lambda:payload)) as post:
                with self.assertRaises(BackendError):cloud.translate(provider,'Wait for me.')
                self.assertEqual(post.call_count,1)
        self.assertEqual(sorted(self.store.usage()),[('azure',12,0),('deepl',12,0),('google',12,0)])

    def test_literals_coordinates_fullwidth_and_chinese_adjacency(self):
        validate('Collect 3/10 stones before 01:30.','01：30前收集3/10顆石頭。')
        for target in ('01:30前收集10/3顆石頭。','1:30前收集3/10顆石頭。'):
            with self.assertRaises(ValueError):validate('Collect 3/10 stones before 01:30.',target)
        with self.assertRaises(ValueError):validate('Meet at X:12 Y:34.','請在 X:34 Y:12 會合。')
        with self.assertRaises(ValueError):validate('Gain +50%.','獲得50%。')

    def test_chat_repeated_messages_and_scrolling(self):
        self.assertEqual(new_chat_lines(['A'],['A','A']),['A'])
        self.assertEqual(new_chat_lines(['A','B'],['B','C']),['C'])
        self.assertEqual(new_chat_lines(['A','B'],['A','B']),[])
        self.assertEqual(new_chat_lines(['A','B'],['C','D']),['C','D'])

    def test_paragraph_split_does_not_drop_content(self):
        source = 'First sentence.\nSecond sentence.\n\nNext paragraph.'
        self.assertEqual(chunks(source),['First sentence. Second sentence.','Next paragraph.'])

    def test_region_rejects_empty_and_keeps_negative_monitor_coordinates(self):
        with self.assertRaises(ValueError):Region(0,0,0,30)
        self.assertEqual(Region(-800,-100,80,40).x,-800)

    def test_cloud_usage_limit_blocks_before_network(self):
        vault = SimpleNamespace(get=lambda provider:'synthetic-key')
        cloud = CloudBackend(Settings(monthly_limit=5),vault,self.store)
        with patch('babelander.backends.requests.post') as post:
            with self.assertRaises(ValueError):cloud.translate('google','long input')
            post.assert_not_called()

    def test_cloud_timeout_counts_attempt_once_and_does_not_retry(self):
        import requests
        cloud = CloudBackend(Settings(),SimpleNamespace(get=lambda p:'synthetic-key'),self.store)
        with patch('babelander.backends.requests.post',side_effect=requests.Timeout) as post:
            with self.assertRaises(BackendError):cloud.translate('azure','input')
            self.assertEqual(post.call_count,1)
        self.assertEqual(self.store.usage(),[('azure',5,0)])

    def test_cloud_adapters_direction_and_single_send(self):
        cloud = CloudBackend(Settings(),SimpleNamespace(get=lambda p:'synthetic-key'),self.store)
        responses = {'google':{'data':{'translations':[{'translatedText':'I will return.'}]}},
                     'azure':[{'translations':[{'text':'I will return.'}]}],
                     'deepl':{'translations':[{'text':'I will return.'}]}}
        for provider in responses:
            with patch('babelander.backends.requests.post',return_value=SimpleNamespace(status_code=200,json=lambda:responses[provider])) as post:
                self.assertEqual(cloud.translate(provider,'我回來。',True),'I will return.')
                post.assert_called_once()
                self.assertFalse(post.call_args.kwargs['allow_redirects'])
        self.assertEqual(len(self.store.usage()),3)

    def test_legacy_application_import_blocked(self):
        with self.assertRaises(ImportError):__import__('gamelens.translator')
        self.assertFalse(any(n=='gamelens' or n.startswith('gamelens.') for n in sys.modules))


class SchedulerTests(unittest.TestCase):
    def queue(self,capacity=128):
        queue = Scheduler(capacity)
        self.addCleanup(lambda:(queue.close(),queue.join()))
        return queue

    def test_subtitle_priority_and_same_priority_fifo(self):
        queue = self.queue()
        started,release = threading.Event(),threading.Event()
        self.addCleanup(release.set)
        first = queue.submit(Mode.EQUIPMENT,lambda:(started.set(),release.wait(3)))
        self.assertTrue(started.wait(2))
        order = []
        jobs = [queue.submit(mode,lambda name=name:order.append(name)) for mode,name in ((Mode.EQUIPMENT,'card'),(Mode.DIALOG,'subtitle'),(Mode.CHAT,'chat1'),(Mode.CHAT,'chat2'))]
        release.set();first.result(3)
        for job in jobs:job.result(3)
        self.assertEqual(order,['subtitle','chat1','chat2','card'])

    def test_cancel_predicate_exception_finishes_future_and_worker_survives(self):
        queue = self.queue()
        def broken():raise ValueError('disposed callback')
        bad = queue.submit(Mode.DIALOG,lambda:None,broken)
        with self.assertRaises(ValueError):bad.result(2)
        self.assertEqual(queue.submit(Mode.DIALOG,lambda:42).result(2),42)

    def test_queue_capacity_and_shutdown_cancel_pending(self):
        queue = self.queue(1)
        started,release = threading.Event(),threading.Event()
        self.addCleanup(release.set)
        active = queue.submit(Mode.DIALOG,lambda:(started.set(),release.wait(3)))
        self.assertTrue(started.wait(2))
        pending = queue.submit(Mode.EQUIPMENT,lambda:None)
        with self.assertRaises(RuntimeError):queue.submit(Mode.CHAT,lambda:None)
        queue.close()
        self.assertTrue(pending.cancelled())
        release.set();active.result(3)
        with self.assertRaises(RuntimeError):queue.submit(Mode.DIALOG,lambda:None)

    def test_concurrent_producers_complete_500_jobs(self):
        queue = self.queue(1024)
        with ThreadPoolExecutor(5) as pool:
            batches = list(pool.map(lambda start:[queue.submit(Mode.CHAT,lambda v=v:v) for v in range(start,start+100)],range(0,500,100)))
        self.assertEqual(sorted(f.result(3) for batch in batches for f in batch),list(range(500)))


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    report = {'passed':result.wasSuccessful(),'tests_run':result.testsRun,'failures':[s for t,s in result.failures],
              'errors':[s for t,s in result.errors],'network':'Synthetic transport; zero API requests'}
    (ROOT/'test-results').mkdir(exist_ok=True)
    (ROOT/'test-results/unit-tests.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    raise SystemExit(not report['passed'])
