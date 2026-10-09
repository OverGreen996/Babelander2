"""Numeric retry boundaries, disagreement and cancellation; no model/windows."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import cv2
import numpy as np
from babelander.equipment_recovery import proposals,crops,accept,NumericCandidate,MAX_CANDIDATES
from babelander.ocr import OCR
from babelander.types import OCRLine,Cancellation,Cancelled

def line(text,box=(12,24,100,51),confidence=.99):
    x0,y0,x1,y1=box
    return OCRLine(text,((x0,y0),(x1,y0),(x1,y1),(x0,y1)),confidence)

def scene(value='7',color=(235,235,235),background=(30,30,30),label='Health'):
    image=np.full((90,300,3),background,np.uint8)
    cv2.putText(image,label,(12,45),cv2.FONT_HERSHEY_SIMPLEX,.7,color,1,cv2.LINE_AA)
    cv2.putText(image,value,(150,48),cv2.FONT_HERSHEY_SIMPLEX,.9,color,2,cv2.LINE_AA)
    return image,[line(label)]

def recognized(text='7',score=.999):return SimpleNamespace(txts=[text],scores=[score])

class RecoveryTests(unittest.TestCase):
    def test_missing_glyph_proposal_has_geometry_no_value(self):
        image,lines=scene();candidate=proposals(image,lines)
        self.assertEqual(len(candidate),1);self.assertIsNone(candidate[0].replace_index)
        self.assertEqual(set(vars(candidate[0])),{'box','replace_index'})
    def test_existing_number_never_duplicated(self):
        image,lines=scene();candidate=proposals(image,lines)[0]
        self.assertFalse(proposals(image,lines+[line('7',candidate.box)]))
    def test_unknown_field_never_scanned(self):
        image,lines=scene(label='Artwork');self.assertFalse(proposals(image,lines))
    def test_low_confidence_label_not_anchor(self):
        image,_=scene();self.assertFalse(proposals(image,[line('Health',confidence=.7)]))
    def test_color_and_bright_background(self):
        for color,bg in (((240,175,80),(20,30,40)),((30,40,50),(235,235,235))):
            image,lines=scene(color=color,background=bg)
            self.assertEqual(len(proposals(image,lines)),1)
    def test_solid_shapes_rejected(self):
        image,lines=scene(value='')
        cv2.rectangle(image,(150,26),(168,48),(235,235,235),-1)
        self.assertFalse(proposals(image,lines))
    def test_low_confidence_retry_requires_adjacent_numeric_field(self):
        image,lines=scene();box=proposals(image,lines)[0].box
        digit=line('1',box,.6)
        self.assertFalse(proposals(image,[digit]))
        self.assertEqual(proposals(image,lines+[digit]),[NumericCandidate(box,1)])
    def test_invalid_coordinates_are_not_cropped(self):
        image,_=scene()
        self.assertFalse(proposals(image,[line('7',(-2,20,12,40),.6),line('Health',(1,1,30,90))]))
    def test_candidates_and_crops_bounded(self):
        image=np.full((600,300,3),30,np.uint8);lines=[]
        for i in range(10):
            y=i*55
            sample,ls=scene();image[y:y+55]=sample[:55];lines.append(line('Health',(12,y+24,100,y+51)))
        candidates=proposals(image,lines)
        self.assertEqual(len(candidates),MAX_CANDIDATES)
        self.assertTrue(all(p.shape[0]*p.shape[1]<=16384 for p in crops(image,candidates)))
    def test_same_high_confidence_digits_accepted(self):
        image,lines=scene();cs=proposals(image,lines)
        output,count=accept(lines,cs,recognized('18'),recognized('18'))
        self.assertEqual(count,1);self.assertEqual({l.text for l in output},{'Health','18'})
        self.assertEqual(output[-1].box[0],cs[0].box[:2])
    def test_disagreement_preserves_input(self):
        image,lines=scene();output,count=accept(lines,proposals(image,lines),recognized('7'),recognized('1'))
        self.assertEqual((output,count),(lines,0))
    def test_low_nan_and_letters_rejected(self):
        image,lines=scene();cs=proposals(image,lines)
        for text,score in (('O',.999),('7',.97),('7',float('nan')),('Health 7',.999),('-7',.999),('12345',.999)):
            output,count=accept(lines,cs,recognized(text,score),recognized(text,score))
            self.assertEqual((output,count),(lines,0))
    def test_truncated_batch_rejected(self):
        image,lines=scene();cs=proposals(image,lines)
        for broken in (SimpleNamespace(txts=None,scores=None),SimpleNamespace(txts=[],scores=[])):
            self.assertEqual(accept(lines,cs,recognized(),broken),(lines,0))
    def test_low_confidence_number_replaced_not_appended(self):
        image,lines=scene();box=proposals(image,lines)[0].box
        lines.append(line('1',box,.6));cs=proposals(image,lines)
        output,count=accept(lines,cs,recognized(),recognized())
        self.assertEqual(count,1);self.assertEqual(len(output),2);self.assertEqual(output[-1].text,'7')
    def test_cancel_between_batches_prevents_second_request(self):
        image,lines=scene();token=Cancellation();calls=[];ocr=OCR()
        def call(patches):calls.append(len(patches));token.cancel();return recognized()
        ocr.engine=SimpleNamespace(recognize_txt=call)
        with self.assertRaises(Cancelled):ocr.recover_equipment(image,lines,token)
        self.assertEqual(calls,[1])
    def test_no_candidate_no_engine_request(self):
        image,lines=scene(label='Artwork');ocr=OCR()
        self.assertEqual(ocr.recover_equipment(image,lines,Cancellation()),lines)
        self.assertIsNone(ocr.engine)
    def test_two_batched_requests_and_numeric_telemetry(self):
        image,lines=scene();calls=[];events=[];ocr=OCR()
        def call(patches):calls.append([p.shape for p in patches]);return recognized()
        ocr.engine=SimpleNamespace(recognize_txt=call)
        output=ocr.recover_equipment(image,lines,Cancellation(),lambda *event:events.append(event))
        self.assertEqual(len(calls),2);self.assertEqual(events,[(1,1)]);self.assertEqual(output[-1].text,'7')
        self.assertEqual(calls[1][0][0],calls[0][0][0]*2)
    def test_rejected_geometry_reserved_without_guessing_a_value(self):
        image,lines=scene();ocr=OCR();calls=[];reserved=[]
        def call(patches):
            calls.append(1);return recognized('7' if len(calls)==1 else '1')
        ocr.engine=SimpleNamespace(recognize_txt=call)
        output=ocr.recover_equipment(image,lines,Cancellation(),on_reserved=reserved.extend)
        self.assertEqual(output,lines);self.assertEqual(reserved,[proposals(image,lines)[0].box])
    def test_reserved_region_preserves_pixels_and_limits_translation_width(self):
        from babelander.equipment_layout import capture_layout
        from babelander.layout import OCRBlock
        from babelander.types import Region
        image,lines=scene();candidate=proposals(image,lines)[0]
        layout=capture_layout(Region(0,0,300,90),image,[OCRBlock(tuple(lines))],reserved_boxes=[candidate.box])
        self.assertLessEqual(layout.slots[0].bounds[2],candidate.box[0]-2)
        original=np.frombuffer(layout.pixels,np.uint8).reshape(image.shape)
        x0,y0,x1,y1=candidate.box
        self.assertTrue(np.array_equal(original[y0:y1,x0:x1],image[y0:y1,x0:x1]))

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RecoveryTests))
    report={'passed':result.wasSuccessful(),'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)}
    path=Path('test-results/equipment-recovery-unit.json');path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report,indent=2),encoding='utf8')
    raise SystemExit(not result.wasSuccessful())
