"""Recognition reuse must preserve digits, batch width, order and cancellation."""
from bootstrap import prepare
prepare()
from dataclasses import dataclass
from types import SimpleNamespace
import unittest
import numpy as np
from babelander.chat_ocr import ChatRecognitionCache
from babelander.types import Cancellation, Cancelled


@dataclass
class Output:
    imgs: object = None
    txts: object = None
    scores: object = None
    word_results: object = None
    elapse: object = None
    viser: object = None


def crop(value, width=80):
    return np.full((10, width, 3), value, np.uint8)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.cache = ChatRecognitionCache()
        self.token = Cancellation()
        self.scope = object()
        self.rec = SimpleNamespace(rec_batch_num=6, rec_image_shape=(3,48,320))
        self.calls = []
        self.confidence = .99

    def original(self, images):
        # Simulate a recognizer whose output depends on shared batch width;
        # this catches an adapter that simply recognizes arbitrary misses.
        ratios = [im.shape[1]/im.shape[0] for im in images]
        order = np.argsort(ratios)
        texts = [None]*len(images)
        for start in range(0,len(images),self.rec.rec_batch_num):
            batch = order[start:start+self.rec.rec_batch_num]
            width = int(48*max(320/48,*(ratios[i] for i in batch)))
            for i in batch:
                texts[i] = f'X{images[i][0,0,0]} width={width}'
        self.calls.append([int(im[0,0,0]) for im in images])
        return Output(images,tuple(texts),tuple(self.confidence for _ in images),tuple(None for _ in images))

    def run_cache(self, images, **kwargs):
        return self.cache.recognize(images,self.original,self.rec,self.token,self.scope,**kwargs)

    def test_unchanged_pixels_reuse_without_inference(self):
        first=self.run_cache([crop(5),crop(6)])
        second=self.run_cache([crop(5).copy(),crop(6).copy()])
        self.assertEqual(first.txts,second.txts)
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.cache.last['reused'],2)

    def test_changed_digit_is_recognized(self):
        self.run_cache([crop(5),crop(9)])
        result=self.run_cache([crop(6),crop(9)])
        self.assertTrue(result.txts[0].startswith('X6 '))
        self.assertEqual(self.calls[-1],[6])

    def test_scroll_reorder_keeps_current_order(self):
        self.run_cache([crop(1),crop(2),crop(3)])
        result=self.run_cache([crop(2),crop(3),crop(4)])
        self.assertEqual([t.split()[0] for t in result.txts],['X2','X3','X4'])
        self.assertEqual(self.cache.last['reused'],2)

    def test_repeated_identical_messages_keep_both_occurrences(self):
        self.run_cache([crop(1)])
        result=self.run_cache([crop(1),crop(1)])
        self.assertEqual(len(result.txts),2)
        self.assertEqual(result.txts[0],result.txts[1])

    def test_widest_cached_neighbor_preserves_normalization(self):
        self.run_cache([crop(1),crop(2,300)])
        result=self.run_cache([crop(3),crop(2,300)])
        self.assertEqual(result.txts,self.original([crop(3),crop(2,300)]).txts)
        self.assertEqual(self.calls[-2],[3,2])
        self.assertEqual(self.cache.last['context_crops'],1)

    def test_longer_new_neighbor_invalidates_old_batch_width(self):
        self.run_cache([crop(1),crop(2,100)])
        result=self.run_cache([crop(1),crop(3,300)])
        self.assertIn('width=1440',result.txts[0])
        self.assertEqual(self.cache.last['reused'],0)

    def test_explicit_padding_does_not_infer_cached_widest_row(self):
        self.run_cache([crop(1),crop(2,300)])
        calls=[]
        def padded(images,ratio):
            calls.append(([int(im[0,0,0]) for im in images],ratio))
            return Output(images,tuple(f'X{im[0,0,0]} width={int(48*ratio)}' for im in images),tuple(.99 for _ in images))
        result=self.run_cache([crop(3),crop(2,300)],padded=padded)
        self.assertEqual(result.txts,self.original([crop(3),crop(2,300)]).txts)
        self.assertEqual(calls,[([3],30)])
        self.assertEqual(self.cache.last['inferred'],1)
        self.assertEqual(self.cache.last['context_crops'],0)

    def test_multiple_width_sorted_batches_equal_full(self):
        old=[crop(i,i*50) for i in range(1,15)]
        self.run_cache(old)
        new=[im.copy() for im in old]
        new[1]=crop(22,100);new[8]=crop(29,450)
        self.assertEqual(self.run_cache(new).txts,self.original(new).txts)

    def test_low_confidence_is_rechecked(self):
        self.confidence=.80
        self.run_cache([crop(1)])
        self.run_cache([crop(1)])
        self.assertEqual(len(self.calls),2)
        self.assertEqual(len(self.cache.entries),0)

    def test_new_engine_scope_cannot_reuse_old_text(self):
        self.run_cache([crop(1)])
        self.scope=object()
        self.run_cache([crop(1)])
        self.assertEqual(len(self.calls),2)

    def test_clear_drops_private_text_and_identity(self):
        self.run_cache([crop(1)])
        self.cache.clear()
        self.assertEqual(len(self.cache.entries),0)
        self.assertIsNone(self.cache.scope)
        self.assertEqual(self.cache.last,{})

    def test_storage_is_bounded_and_contains_no_images(self):
        for i in range(100):self.run_cache([crop(i)])
        self.assertEqual(len(self.cache.entries),64)
        self.assertTrue(all(isinstance(text,str) and isinstance(score,float) for text,score in self.cache.entries.values()))
        self.assertFalse(any(isinstance(part,np.ndarray) for key in self.cache.entries for part in key))

    def test_cancel_during_miss_never_commits_partial_result(self):
        self.run_cache([crop(1)])
        def cancel(images):
            result=self.original(images);self.token.cancel();return result
        before=dict(self.cache.entries)
        with self.assertRaises(Cancelled):
            self.cache.recognize([crop(1),crop(2)],cancel,self.rec,self.token,self.scope)
        self.assertEqual(dict(self.cache.entries),before)

    def test_word_boxes_use_full_recognizer(self):
        self.run_cache([crop(1)])
        self.run_cache([crop(1)],word_boxes=True)
        self.assertEqual(len(self.calls),2)
        self.assertEqual(self.cache.last['fallback'],1)

    def test_malformed_subset_falls_back_to_full(self):
        self.run_cache([crop(1)])
        def incomplete(images):
            if len(images)==1:return Output(txts=(),scores=())
            return self.original(images)
        result=self.cache.recognize([crop(1),crop(2)],incomplete,self.rec,self.token,self.scope)
        self.assertEqual(len(result.txts),2)
        self.assertEqual(self.cache.last['fallback'],1)
        self.assertEqual(len(self.cache.entries),0)

    def test_pixel_change_in_background_is_a_miss(self):
        image=crop(1);self.run_cache([image])
        changed=image.copy();changed[-1,-1,0]+=1
        self.run_cache([changed])
        self.assertEqual(len(self.calls),2)

    def seed_region(self):
        image=np.zeros((80,160,3),np.uint8)
        image[25:35,25:85]=50
        box=np.array([[20,20],[90,20],[90,40],[20,40]],dtype=float)
        self.cache.prepare_regions(image,np.array([box]))
        self.run_cache([crop(5)])
        self.cache.release_frame()
        return image,box

    def test_detector_wobble_reuses_only_verified_source_region(self):
        image,box=self.seed_region()
        self.cache.prepare_regions(image.copy(),np.array([box+(1,0)]))
        result=self.run_cache([crop(55)])
        self.assertTrue(result.txts[0].startswith('X5 '))
        self.assertEqual(self.cache.last['region_reused'],1)
        self.assertEqual(len(self.calls),1)

    def test_scrolled_verified_region_reuses_with_current_detection(self):
        image,box=self.seed_region()
        moved=np.zeros_like(image);moved[10:]=image[:-10]
        self.cache.prepare_regions(moved,np.array([box+(0,10)]))
        self.run_cache([crop(55)])
        self.assertEqual(self.cache.last['region_reused'],1)

    def test_one_changed_pixel_in_guard_forces_recognition(self):
        image,box=self.seed_region()
        image[15,40,0]=1
        self.cache.prepare_regions(image,np.array([box]))
        result=self.run_cache([crop(6)])
        self.assertTrue(result.txts[0].startswith('X6 '))
        self.assertEqual(self.cache.last['region_reused'],0)

    def test_larger_new_glyph_outside_old_region_is_not_reused(self):
        image,box=self.seed_region()
        image[25:35,95:115]=50
        box[[1,2],0]=120
        self.cache.prepare_regions(image,np.array([box]))
        self.run_cache([crop(6,110)])
        self.assertEqual(self.cache.last['region_reused'],0)

    def test_region_storage_and_frame_reference_are_cleared(self):
        self.seed_region()
        self.assertIsNone(self.cache.current_regions)
        self.assertEqual(len(self.cache.regions),1)
        self.cache.clear()
        self.assertEqual(self.cache.regions,[])

    def test_below_reuse_confidence_is_rechecked_even_when_pixels_match(self):
        self.confidence=.979
        image,box=self.seed_region()
        self.cache.prepare_regions(image,np.array([box]))
        self.run_cache([crop(6)])
        self.assertEqual(len(self.calls),2)
        self.assertEqual(self.cache.last['reused'],0)

    def test_oversized_region_is_not_retained(self):
        image=np.zeros((400,400,3),np.uint8)
        box=np.array([[20,20],[380,20],[380,380],[20,380]],dtype=float)
        self.cache.prepare_regions(image,np.array([box]))
        self.run_cache([crop(1)])
        self.assertEqual(self.cache.regions,[])

    def test_disabled_cache_performs_full_recognition(self):
        self.cache=ChatRecognitionCache(capacity=0)
        self.run_cache([crop(1)])
        self.run_cache([crop(1)])
        self.assertEqual(len(self.calls),2)
        self.assertFalse(self.cache.entries)


if __name__=='__main__':unittest.main(verbosity=2)
