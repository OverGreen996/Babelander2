"""Line-hint safety contracts; synthetic engines, no desktop/model/API."""
from pathlib import Path
from types import SimpleNamespace
import json
import time
import unittest
import numpy as np
from babelander.ocr import OCR
from babelander.subtitle_layout import SubtitleLayout
from babelander.settings import Settings
from babelander.types import OCRLine,Cancellation,Cancelled

BOX=((10,18),(230,18),(230,52),(10,52))

def frame(width=320):
    image=np.zeros((100,width,3),dtype=np.uint8)
    for x in range(20,200,12):image[24:46,x:x+6]=255
    return image

class LayoutTests(unittest.TestCase):
    def learned(self,image=None,lines=None):
        image=frame() if image is None else image
        layout=SubtitleLayout()
        layout.learn(image,lines if lines is not None else [OCRLine('HP 10',BOX,.99)],now=time.perf_counter())
        return layout

    def test_new_width_is_taken_from_current_frame(self):
        image=frame();layout=self.learned(image)
        image[24:46,260:272]=255
        boxes=layout.propose(image)
        self.assertIsNotNone(boxes)
        self.assertGreaterEqual(boxes[0][2],272)

    def test_new_line_or_move_forces_full_detection(self):
        for image in (np.roll(frame(),35,axis=0),frame()):
            image[75:90,30:180]=255
            self.assertIsNone(self.learned().propose(image))

    def test_blank_or_missing_line_forces_full_detection(self):
        image=frame();image[:]=0
        self.assertIsNone(self.learned().propose(image))
        layout=self.learned(lines=[OCRLine('First',BOX,.99),OCRLine('Second',((10,70),(230,70),(230,95),(10,95)),.99)])
        self.assertIsNone(layout.propose(frame()))

    def test_colored_foreground_uses_full_detection(self):
        image=frame();image[24:46,210:255]=(30,30,255)
        self.assertIsNone(self.learned().propose(image))

    def test_shape_periodic_and_reuse_budget_force_full_detection(self):
        layout=self.learned()
        self.assertIsNone(layout.propose(frame(330)))
        self.assertIsNone(layout.propose(frame(),now=layout.learned_at+2))
        layout.reuses=3
        self.assertIsNone(layout.propose(frame()))

    def test_low_confidence_or_rotated_seed_is_not_reused(self):
        for line in (OCRLine('Text',BOX,.89),OCRLine('Text',((10,18),(230,30),(230,55),(10,43)),.99)):
            self.assertFalse(self.learned(lines=[line]).rows)

    def test_layout_has_no_source_text_or_frame_history(self):
        layout=self.learned()
        self.assertFalse(any(isinstance(v,np.ndarray) for v in vars(layout).values()))
        self.assertNotIn('HP 10',repr(vars(layout)))

    def test_close_rows_keep_glyphs_and_split_padding(self):
        image=np.zeros((150,320,3),dtype=np.uint8)
        for x in range(20,200,12):
            image[24:63,x:x+6]=255;image[74:113,x:x+6]=255
        lines=[OCRLine('First',((10,20),(230,20),(230,67),(10,67)),.99),
               OCRLine('Second',((10,70),(230,70),(230,117),(10,117)),.99)]
        layout=self.learned(image,lines)
        self.assertEqual(len(layout.rows),2)
        self.assertLessEqual(layout.rows[0][1],layout.rows[1][0])
        self.assertEqual(len(layout.propose(image)),2)

    def fake_ocr(self,score=.99,text='HP 18, not 10!'):
        class Engine:
            def __init__(self):self.full=0;self.rec=0
            def recognize_txt(self,crops):
                self.rec+=1
                return SimpleNamespace(txts=(text,),scores=(score,))
            def __call__(self,image):
                self.full+=1
                return SimpleNamespace(txts=('Fallback full text.',),scores=(.98,),boxes=(BOX,))
        ocr=OCR();ocr.engine=Engine();ocr.engine_threads=2
        return ocr

    def test_only_recognition_is_called_and_text_stays_exact(self):
        ocr=self.fake_ocr();layout=self.learned()
        lines=ocr.recognize(frame(),Cancellation(),layout=layout)
        self.assertEqual(lines[0].text,'HP 18, not 10!')
        self.assertEqual((ocr.engine.full,ocr.engine.rec),(0,1))
        self.assertEqual(layout.last_path,'line_reuse')

    def test_recognition_low_confidence_falls_back_in_same_call(self):
        ocr=self.fake_ocr(score=.85);layout=self.learned()
        self.assertEqual(ocr.recognize(frame(),Cancellation(),layout=layout)[0].text,'Fallback full text.')
        self.assertEqual((ocr.engine.full,ocr.engine.rec),(1,1))
        self.assertEqual(layout.last_path,'full')
        self.assertEqual(layout.last_reason,'recognition_low_confidence')

    def test_disabled_path_does_not_use_hints(self):
        ocr=self.fake_ocr()
        ocr.recognize(frame(),Cancellation())
        self.assertEqual((ocr.engine.full,ocr.engine.rec),(1,0))

    def test_same_episode_recheck_refreshes_full_detection(self):
        ocr=self.fake_ocr();layout=self.learned();layout.last_key=('ink',b'A')
        ocr.recognize(frame(),Cancellation(),layout=layout,layout_key=('ink',b'A'))
        self.assertEqual((ocr.engine.full,ocr.engine.rec),(1,0))
        self.assertEqual(layout.last_reason,'episode_recheck')
        self.assertEqual(layout.last_key,('ink',b'A'))

    def test_changed_episode_can_reuse_recent_layout(self):
        ocr=self.fake_ocr();layout=self.learned();layout.last_key=('ink',b'A')
        ocr.recognize(frame(),Cancellation(),layout=layout,layout_key=('ink',b'B'))
        self.assertEqual((ocr.engine.full,ocr.engine.rec),(0,1))
        self.assertEqual(layout.last_key,('ink',b'B'))

    def test_cancelled_call_never_starts_ocr(self):
        ocr=self.fake_ocr();token=Cancellation();token.cancel()
        with self.assertRaises(Cancelled):ocr.recognize(frame(),token,layout=self.learned())
        self.assertEqual((ocr.engine.full,ocr.engine.rec),(0,0))

    def test_option_is_explicit_bool_and_off_by_default(self):
        self.assertFalse(Settings().reuse_dialogue_lines)
        for value in (1,'true',None):
            with self.assertRaises(ValueError):Settings(reuse_dialogue_lines=value).validate()

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LayoutTests))
    path=Path(__file__).resolve().parent/'test-results/layout-unit.json'
    path.write_text(json.dumps({'passed':result.wasSuccessful(),'tests':result.testsRun,'failures':[s for _,s in result.failures],
                               'errors':[s for _,s in result.errors],'real_ocr':False,'scope':'Synthetic safety contracts; no mixed dim text recall assertion.'},indent=2),encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
