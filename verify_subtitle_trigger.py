"""Outlined dim-trigger invariance and settings; no desktop, model or API."""
import unittest,json
from pathlib import Path
from dataclasses import replace
import cv2,numpy as np
from babelander.subtitle_trigger import dim_signature,StableDimSignature
from babelander.settings import Settings

def glyphs(text,color=155):
    image=np.full((110,680,3),45,dtype=np.uint8)
    cv2.putText(image,text,(20,65),cv2.FONT_HERSHEY_SIMPLEX,1.3,(0,0,0),6)
    cv2.putText(image,text,(20,65),cv2.FONT_HERSHEY_SIMPLEX,1.3,(color,color,color),2)
    return image

class TriggerTests(unittest.TestCase):
    def test_default_disabled_and_boolean_validation(self):
        self.assertFalse(Settings().mixed_text_trigger)
        replace(Settings(),mixed_text_trigger=True).validate()
        with self.assertRaises(ValueError):replace(Settings(),mixed_text_trigger=1).validate()
    def test_initial_sample_does_not_wait_or_create_a_second_epoch(self):
        gate=StableDimSignature();self.assertEqual(gate.observe(b'a',0),b'a')
        self.assertEqual(gate.observe(b'a',.2),b'a')
    def test_short_lived_shapes_do_not_commit(self):
        gate=StableDimSignature();gate.observe(None,0)
        for i in range(1,30):self.assertIsNone(gate.observe(str(i).encode(),i*.1))
    def test_change_needs_two_observations_and_time(self):
        gate=StableDimSignature();gate.observe(None,0)
        self.assertIsNone(gate.observe(b'a',.1));self.assertIsNone(gate.observe(b'a',.15))
        self.assertEqual(gate.observe(b'a',.18),b'a')
    def test_removed_structure_also_requires_confirmation(self):
        gate=StableDimSignature();gate.observe(b'a',0)
        self.assertEqual(gate.observe(None,.1),b'a');self.assertIsNone(gate.observe(None,.2))
    def test_return_to_current_resets_candidate(self):
        gate=StableDimSignature();gate.observe(b'a',0)
        gate.observe(b'b',.1);gate.observe(b'a',.2)
        self.assertEqual(gate.observe(b'b',.3),b'a')
        self.assertEqual(gate.observe(b'b',.4),b'b')
    def test_state_does_not_retain_images_or_text(self):
        gate=StableDimSignature();gate.observe(b'a',0)
        self.assertEqual(set(vars(gate)),{'initialized','current','candidate','since'})
    def test_sessions_do_not_share_state(self):
        first=StableDimSignature();first.observe(b'a',0);first.observe(b'b',.1)
        self.assertEqual(StableDimSignature().observe(b'c',.2),b'c')
    def test_dim_outlined_glyphs_are_detected(self):
        self.assertIsNotNone(dim_signature(glyphs('before midnight')))
    def test_bright_glyphs_blank_and_unsupported_are_not_dim_hints(self):
        self.assertIsNone(dim_signature(glyphs('before midnight',255)))
        self.assertIsNone(dim_signature(np.zeros((110,680,3),dtype=np.uint8)))
        self.assertIsNone(dim_signature(None))
    def test_new_dim_word_changes_signature(self):
        self.assertNotEqual(dim_signature(glyphs('before midnight')),dim_signature(glyphs('after midnight')))

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TriggerTests))
    report={'passed':result.wasSuccessful(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'real_desktop_capture':False}
    out=Path('test-results/subtitle-trigger-unit.json');out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report,indent=2),encoding='utf8');raise SystemExit(not result.wasSuccessful())
