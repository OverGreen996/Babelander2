"""Critical intent preservation and conservative fallback regression corpus."""
from bootstrap import prepare
prepare()
import unittest,json
from pathlib import Path
from babelander import __version__
from babelander.glossary import Dictionary,Entry
from babelander.chat import CHAT_TERMS,complete_rule
from babelander.semantic_rules import dialog_rule
from babelander.validation import validate
class Regressions(unittest.TestCase):
    def dictionary(self,*entries):
        overrides={e.source.casefold() for e in entries}
        return Dictionary([*entries,*[Entry(k,v,'chat') for k,v in CHAT_TERMS.items() if k not in overrides]])
    def test_prohibitions_preserved(self):
        for text in ('Do not cross the bridge yet.','Do not leave the room yet.','Do not open the chest yet.','Do not close the door yet.','Do not start the fight yet.'):
            with self.subTest(text=text):
                target=dialog_rule(text,Dictionary());self.assertIn('不要',target);validate(text,target)
    def test_prohibition_unknown_or_conditional_falls_back(self):
        for text in ('Do not open the river yet.','Do not start the door yet.','Do not cross the river yet unless I say so.','Do not cross the river yet. Wait for me.','Never open the gate.'):
            with self.subTest(text=text):self.assertIsNone(dialog_rule(text,Dictionary()))
    def test_prohibition_glossary(self):
        self.assertIn('水道',dialog_rule('Do not cross the river yet.',Dictionary([Entry('river','水道')])))
        self.assertIsNone(dialog_rule('Do not cross the river yet.',Dictionary([Entry('yet','現在')])) )
    def test_reservation_quantities(self):
        for quantity in ('1','5','6','100','one','two','six'):
            with self.subTest(quantity=quantity):
                source=f'Save {quantity} potions for us.';target=complete_rule(source,self.dictionary());self.assertIn('留',target);self.assertIn('我們',target);validate(source,target,chat=True)
    def test_reservation_fallback(self):
        for text in ('Do not save 6 potions for me.','Save 6 potions for me unless we wipe.','Save one unfamiliaritem for me.','Save all potions for me.','Save one potion for me and sell the others.'):
            with self.subTest(text=text):self.assertIsNone(complete_rule(text,self.dictionary()))
    def test_reservation_explicit_verb_override_falls_back(self):
        self.assertIsNone(complete_rule('Save one potion for me.',self.dictionary(Entry('save','儲存'))))
    def test_priority_role_override(self):
        self.assertEqual(complete_rule('Target the tank first!',self.dictionary(Entry('tank','重裝玩家'))),'優先集火重裝玩家。')
    def test_priority_never_eats_conditions_or_glossary(self):
        for text in ('Focus the healer first if the boss is alive.','Do not focus the healer first.','Focus the healer.'):
            with self.subTest(text=text):self.assertIsNone(complete_rule(text,self.dictionary()))
        self.assertIsNone(complete_rule('Focus the healer first.',self.dictionary(Entry('first','第一階段'))))
    def test_pause_numbers_and_units(self):
        for text,target in [('Can we pause for 6 minutes?','我們可以暫停6分鐘嗎？'),('Could you wait for 1.5 seconds?','你可以等1.5秒嗎？'),('Can we wait for 100 secs?','我們可以等100秒嗎？')]:
            with self.subTest(text=text):self.assertEqual(complete_rule(text,self.dictionary()),target);validate(text,target,chat=True)
    def test_pause_conditions_not_guessed(self):
        for text in ('Can we pause for 2 minutes unless they attack?','Can we not pause for 2 minutes?'):
            with self.subTest(text=text):self.assertIsNone(complete_rule(text,self.dictionary()))
    def test_party_status_and_override(self):
        self.assertEqual(complete_rule('Is the party ready?',self.dictionary()),'隊伍準備好了嗎？')
        self.assertEqual(complete_rule('Party full?',self.dictionary(Entry('party','小隊'))),'小隊滿了嗎？')
        self.assertIsNone(complete_rule('Party full? Invite me.',self.dictionary()))
    def test_valid_deferred_start(self):
        for source,target in [('請等我6分鐘，不要開始。','Please wait 6 minutes before starting.'),('請稍等，別開始。','Wait before you start.')]:
            with self.subTest(target=target):validate(source,target,reply=True)
    def test_deferred_start_must_keep_quantity_unit_and_action(self):
        source='請等我6分鐘，不要開始。'
        for target in ('Please wait 5 minutes before starting.','Please wait 6 seconds before starting.','Please wait 6 minutes before leaving.','Please wait 6 minutes and start now.'):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):validate(source,target,reply=True)
    def test_other_prohibitions_not_relaxed(self):
        for source,target in [('請等我6分鐘，不要離開。','Please wait 6 minutes before starting.'),('請等我6分鐘，不要開始，也不要離開。','Please wait 6 minutes before starting.'),('我6分鐘後回來，不要開始，除非我說好。','Wait 6 minutes before starting.')]:
            with self.subTest(source=source):
                with self.assertRaises(ValueError):validate(source,target,reply=True)
    def test_prohibitions_are_not_past_experience(self):
        for source in ('Do not cross the river yet.','Never open the gate.'):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):validate(source,'尚未穿越河流。')
    def test_quantity_format_and_corruption(self):
        for n in (5,6,7,99,100):
            for source in (f'I need potions X{n}.',f'I need potions {n}x.',f'I need potions × {n}.'):
                with self.subTest(source=source):
                    validate(source,f'我需要{n}瓶藥水。',chat=True)
                    with self.assertRaises(ValueError):validate(source,f'我需要{n+1}瓶藥水。',chat=True)
                    with self.assertRaises(ValueError):validate(source,'我需要藥水。',chat=True)
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Regressions))
    dest=Path('test-results/supertest-a'+__version__.split('a')[-1]);dest.mkdir(parents=True,exist_ok=True)
    (dest/'critical-regressions.json').write_text(json.dumps({'version':__version__,'tests_run':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors)},indent=2),encoding='utf8')
    raise SystemExit(not result.wasSuccessful())
