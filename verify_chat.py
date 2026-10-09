"""Chat-only shorthand, quantity, privacy and wrapping regressions."""
from bootstrap import prepare
prepare()
import json,unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from babelander import __version__
from babelander.chat import messages,split_message,only_shorthand,filter_decorations
from babelander.engine import Engine
from babelander.storage import Store
from babelander.settings import Settings
from babelander.security import KeyVault
from babelander.types import Mode,Cancellation,OCRLine
from babelander.validation import validate
from babelander.controller import new_chat_lines

class ChatTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.store=Store(self.root);self.engine=Engine(Settings(hotkeys={}),self.store,KeyVault(self.root),self.root)
        self.calls=[];self.output='完整中文譯文'
        self.engine.local=SimpleNamespace(translate=self.translate,close=lambda:None)
    def translate(self,system,text):self.calls.append((system,text));return self.output
    def tearDown(self):self.engine.close();self.engine.join();self.store.close();self.temp.cleanup()
    def ask(self,text):return self.engine.request(text,Mode.CHAT,Cancellation())
    @staticmethod
    def line(text,y=0,x=15,h=25):return OCRLine(text,((x,y),(x+300,y),(x+300,y+h),(x,y+h)),.99)
    def test_shorthand_stays_english_without_model(self):
        for word in ('GG','gg wp','TY','BRB','LFG','OOM','GLHF'):
            with self.subTest(word=word):
                result=self.ask(word);self.assertEqual(result.target,word.upper());self.assertFalse(result.warning)
        self.assertFalse(self.calls)

    def test_tiny_particle_does_not_break_chat_overlap(self):
        old=[self.line('Jo: GG',0),self.line('Kai: TY',40)]
        dot=OCRLine('■',((550,10),(558,10),(558,18),(550,18)),.99)
        current,count=filter_decorations([old[0],dot,old[1],self.line('Rin: Need x6',80)])
        self.assertEqual(count,1)
        self.assertEqual(new_chat_lines([l.text for l in old],[l.text for l in current]),['Rin: Need x6'])

    def test_regular_shapes_and_speaker_symbols_remain(self):
        anchor=self.line('Jo: GG',0)
        shapes=[self.line('■',40),self.line('Rin: ■',80,h=8)]
        kept,count=filter_decorations([anchor,*shapes]);self.assertEqual(count,0);self.assertEqual(kept,[anchor,*shapes])

    def test_tiny_quantities_punctuation_and_emoji_remain(self):
        lines=[self.line('Jo: GG')]+[self.line(t,40,h=7) for t in ('X5','X6','5','??','!','...','🙂',':)')]
        self.assertEqual(filter_decorations(lines),(lines,0))

    def test_symbol_only_and_unknown_geometry_fail_open(self):
        tiny=OCRLine('■',((0,0),(8,0),(8,8),(0,8)),.99)
        unknown=OCRLine('■',(),.99)
        self.assertEqual(filter_decorations([tiny,unknown]),([tiny,unknown],0))
        self.assertEqual(filter_decorations([self.line('Jo: GG'),unknown])[1],0)

    def test_dark_text_is_not_filtered_by_shape_rule(self):
        line=self.line('Rin: Need keys x5.',40,h=8)
        self.assertIn(line,filter_decorations([self.line('Jo: GG'),line])[0])

    def test_cross_script_separator_wobble_requires_two_anchors(self):
        old=['Rin: ty，救到我了','Jo: GG','Kai: TY']
        self.assertEqual(new_chat_lines(old,['Rin: ty·救到我了',*old[1:],'Me: BRB']),['Me: BRB'])
        self.assertEqual(new_chat_lines(old[:1],['Rin: ty·救到我了']),['Rin: ty·救到我了'])

    def test_cross_script_separator_preserves_quantities_negation_and_questions(self):
        old=['Rin: ty，先別賣掉X5','Jo: GG','Kai: TY']
        for current in ('Rin: ty·先別賣掉X6','Rin: ty·先賣掉X5','Rin: ty·先別賣掉X5?'):
            self.assertEqual(new_chat_lines(old,[current,*old[1:]]),[current,*old[1:]])
    def test_multiple_orthographic_wobbles_keep_anchored_scroll(self):
        old=['Rin: 我需要3個人','Jo: HP10%·快救我','Kai: brb2min，我去拿水']
        new=['Rin: 我需要3个人','Jo: HP10%，快救我','Kai: brb2min·我去拿水','Me: GG']
        self.assertEqual(new_chat_lines(old,new),['Me: GG'])
        self.assertEqual(new_chat_lines(old[:1],new[:1]),new[:1])

    def test_orthographic_anchors_do_not_hide_meaningful_changes(self):
        old=['Rin: 我需要3個人','Jo: HP10%·快救我','Kai: brb2min，我去拿水']
        for changed in ('Rin: 我需要4个人','Rin: 我不需要3个人','Rin: 我需要3个人?'):
            new=[changed,'Jo: HP10%，快救我','Kai: brb2min·我去拿水']
            self.assertEqual(new_chat_lines(old,new),new)

    def test_stray_cross_script_quote_needs_surrounding_anchors(self):
        old=['Jo: GG','Kai: TY','Rin: DPS集火右邊']
        new=['Jo: GG','Kai: TY','Rin: DPS"集火右边']
        self.assertEqual(new_chat_lines(old,new),[])
        self.assertEqual(new_chat_lines(old[2:],new[2:]),new[2:])
        changed=[*new[:2],'Rin: DPS"不要集火右边']
        self.assertEqual(new_chat_lines(old,changed),changed)

    def test_shorthand_punctuation(self):
        self.assertEqual(self.ask('GG!').target,'GG!');self.assertFalse(self.calls)
    def test_timed_shorthand(self):
        self.assertEqual(self.ask('brb 2 min').target,'BRB 2 分鐘');self.assertFalse(self.calls)
    def test_mixed_chinese_keeps_shorthand(self):
        self.assertEqual(self.ask('GG 大家辛苦了').target,'GG 大家辛苦了');self.assertFalse(self.calls)
    def test_mixed_known_item_uses_complete_rule(self):
        self.assertEqual(self.ask('我需要 potion x4').target,'我需要 藥水 x4');self.assertFalse(self.calls)
    def test_unknown_english_needs_model(self):
        self.ask('Please escort the courier.');self.assertEqual(len(self.calls),1)
    def test_unknown_mixed_english_needs_model(self):
        self.ask('先不要 approach，等隊友');self.assertEqual(len(self.calls),1)
    def test_existing_chinese_quantity_is_unchanged(self):
        self.assertEqual(self.ask('我需要道具X4').target,'我需要道具X4');self.assertFalse(self.calls)
    def test_explicit_glossary_overrides_shorthand(self):
        self.store.save_term('GG','太棒了','chat');self.assertEqual(self.ask('GG').target,'太棒了')
    def test_explicit_glossary_exact_simplified_target(self):
        self.store.save_term('GG','管理员','chat');self.assertEqual(self.ask('GG').target,'管理员')
    def test_changed_glossary_invalidates_volatile_cache(self):
        self.assertEqual(self.ask('GG').target,'GG');self.store.save_term('GG','打得好','shared')
        result=self.ask('GG');self.assertEqual(result.target,'打得好');self.assertFalse(result.cache_hit)
    def test_chat_never_writes_sqlite_history_or_cache(self):
        result=self.ask('GG');self.store.record(Mode.CHAT,result,0)
        self.ask('Please escort the courier.')
        for table in ('cache','history','usage'):self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
    def test_chat_memory_cache_is_bounded(self):
        for i in range(140):self.ask(f'中文 {i}')
        self.assertEqual(len(self.engine.volatile),128)
    def test_unknown_echo_is_not_accepted(self):
        self.output='May I reorganize our formation?';self.assertTrue(self.ask(self.output).warning)
    def test_quantity_x4_to_chinese4(self):validate('I need potions x4.','我需要 4 瓶藥水。',chat=True)
    def test_quantity_4x_to_chinese4(self):validate('I need 4x potions.','我需要 4 瓶藥水。',chat=True)
    def test_quantity_x4_to_wrong3_rejected(self):
        with self.assertRaisesRegex(ValueError,'數值'):validate('I need potions x4.','我需要 3 瓶藥水。',chat=True)
    def test_quantity_x4_missing_rejected(self):
        with self.assertRaisesRegex(ValueError,'數值'):validate('I need potions x4.','我需要藥水。',chat=True)
    def test_other_mode_quantity_guard_unchanged(self):
        with self.assertRaisesRegex(ValueError,'數值'):validate('potions x4.','4 瓶藥水。')
    def test_shorthand_does_not_weaken_other_mode_guard(self):
        with self.assertRaisesRegex(ValueError,'中文'):validate('GG','GG')
    def test_shorthand_does_not_ignore_negation(self):
        with self.assertRaisesRegex(ValueError,'否定'):validate('Do not GG','GG',chat=True)
    def test_shorthand_does_not_ignore_quantity(self):
        with self.assertRaisesRegex(ValueError,'數值'):validate('GG 4','GG 3',chat=True)
    def test_code_identifier_protected(self):
        self.assertEqual(self.ask('不要賣 Item_X4').target,'不要賣 Item_X4')
    def test_shorthand_recognizer_rejects_unknown_words(self):
        self.assertFalse(only_shorthand('GG steal everything'));self.assertFalse(only_shorthand('GG everyone'))
    def test_two_wrapped_lines_are_one_speaker(self):
        rows=messages([self.line('[Party] Rin: Please wait'),self.line('until the fight ends.',34,48)])
        self.assertEqual(len(rows),1);self.assertEqual(rows[0].text,'[Party] Rin: Please wait until the fight ends.')
    def test_new_speaker_never_merged(self):
        rows=messages([self.line('[Party] Rin: GG'),self.line('[Party] Kai: TY',34,48)])
        self.assertEqual(len(rows),2)
    def test_unindented_unprefixed_line_independent(self):
        rows=messages([self.line('Rin: GG'),self.line('Unknown text',34)])
        self.assertEqual(len(rows),2)
    def test_wrap_limit_is_eight_lines(self):
        rows=messages([self.line('Rin: Hello')]+[self.line('continued',i*34,48) for i in range(1,10)])
        self.assertEqual(len(rows),3)
    def test_channel_speaker_split(self):self.assertEqual(split_message('[Party] Rin: GG'),('[Party] Rin:','GG'))
    def test_fullwidth_speaker_colon(self):self.assertEqual(split_message('小明：GG'),('小明：','GG'))
    def test_appended_identical_message_not_lost(self):self.assertEqual(new_chat_lines(['Rin: GG'],['Rin: GG','Rin: GG']),['Rin: GG'])
    def test_scroll_and_burst_preserve_order(self):
        self.assertEqual(new_chat_lines(['A','B','C'],['B','C','D','E']),['D','E'])
    def test_unchanged_frame_no_new_messages(self):self.assertEqual(new_chat_lines(['A','B'],['A','B']),[])
    def test_ocr_whitespace_and_width_jitter_no_duplicate(self):
        self.assertEqual(new_chat_lines(['Rin: GG', 'Kai: 我需要 4 個道具。'],['Rin：GG','Kai:我需要4個道具.','Jo: TY']),['Jo: TY'])
    def test_quantity_change_is_new_message(self):self.assertEqual(new_chat_lines(['Rin: x4'],['Rin: x3']),['Rin: x3'])
    def test_case_change_is_not_silently_erased(self):self.assertEqual(new_chat_lines(['Rin: GG'],['Rin: gg']),['Rin: gg'])
    def test_one_ocr_cjk_wobble_with_two_anchors(self):
        previous=['Kai: TY','Rin:我 OOM 了，等一下','Jo: GG','Me: BRB']
        current=['Rin:我 OOM 了，等—下','Jo: GG','Me: BRB','Q: TY']
        self.assertEqual(new_chat_lines(previous,current),['Q: TY'])
    def test_name_wobble_with_exact_body_and_two_anchors(self):
        self.assertEqual(new_chat_lines(['P077: 我回來了','Rin: GG','Jo: TY'],['PO77: 我回來了','Rin: GG','Jo: TY','Q: BRB']),['Q: BRB'])
    def test_anchors_do_not_hide_number_changes(self):
        self.assertEqual(new_chat_lines(['Rin: x4','Jo: GG','Q: TY'],['Rin: x3','Jo: GG','Q: TY']),['Rin: x3','Jo: GG','Q: TY'])
    def test_anchors_do_not_hide_negation_changes(self):
        a=['Rin: 現在不要進去，等所有人都到齊','Jo: GG','Q: TY'];b=['Rin: 現在可以進去，等所有人都到齊','Jo: GG','Q: TY']
        self.assertEqual(new_chat_lines(a,b),b)

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ChatTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    Path('test-results').mkdir(exist_ok=True)
    Path('test-results/chat-unit-a'+__version__.split('a')[-1]+'.json').write_text(json.dumps({'version':__version__,'tests_run':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors)},indent=2),encoding='utf8')
    raise SystemExit(not result.wasSuccessful())
