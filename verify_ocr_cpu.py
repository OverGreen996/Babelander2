"""Validate exact network tensors, geometry, and non-uint8 fallback."""
import unittest
from types import SimpleNamespace
import numpy as np
from rapidocr.ch_ppocr_det.utils import DetPreProcess
from babelander.ocr_cpu import LookupDetPreProcess, install_detector_preprocess, recognize_padded


class DetectorPreprocessTests(unittest.TestCase):
    def test_all_pixel_values_and_nondefault_channel_statistics_are_exact(self):
        image = np.arange(256,dtype=np.uint8)[None,:,None].repeat(3,axis=2)
        for mean,std in ((None,None),([.485,.456,.406],[.229,.224,.225])):
            baseline = DetPreProcess(1500,'max',mean,std)
            candidate = LookupDetPreProcess(1500,'max',mean,std)
            np.testing.assert_array_equal(candidate.normalize(image),baseline.normalize(image).astype(np.float32))

    def test_entire_tensor_preserves_resize_padding_and_strided_input(self):
        rng=np.random.default_rng(27)
        for height,width in ((240,780),(600,1080),(32,2000),(71,117),(13,29)):
            image=rng.integers(0,256,(height,width*2,3),dtype=np.uint8)[:,::2]
            for kind in ('min','max'):
                np.testing.assert_array_equal(LookupDetPreProcess(736,kind)(image),DetPreProcess(736,kind)(image))

    def test_float_input_falls_back_without_quantization(self):
        image=np.random.default_rng(28).random((32,64,3)).astype(np.float32)*255
        np.testing.assert_array_equal(LookupDetPreProcess(736,'max')(image),DetPreProcess(736,'max')(image))

    def test_dynamic_policy_is_preserved_and_cached(self):
        detector=SimpleNamespace(get_preprocess=lambda size:DetPreProcess(960 if size<960 else 1500 if size<1500 else 2000,'max'))
        install_detector_preprocess(detector)
        for size,limit in ((710,960),(1080,1500),(1700,2000)):
            op=detector.get_preprocess(size)
            self.assertEqual(op.limit_side_len,limit)
            self.assertIs(op,detector.get_preprocess(size))

    def test_cached_anchor_removal_preserves_exact_recognition_tensor(self):
        from rapidocr.ch_ppocr_rec.main import TextRecognizer
        rec=TextRecognizer.__new__(TextRecognizer)
        rec.rec_image_shape=(3,48,320)
        rng=np.random.default_rng(29)
        short=rng.integers(0,256,(25,73,3),dtype=np.uint8)
        long=rng.integers(0,256,(25,701,3),dtype=np.uint8)
        ratio=long.shape[1]/long.shape[0]
        expected=rec.resize_norm_img(short,ratio)
        original=rec.resize_norm_img
        def recognize(images):
            width=max(320/48,*(im.shape[1]/im.shape[0] for im in images))
            return [rec.resize_norm_img(im,width) for im in images]
        actual=recognize_padded(rec,recognize,[short],ratio)
        self.assertEqual(len(actual),1)
        np.testing.assert_array_equal(actual[0],expected)
        self.assertEqual(rec.resize_norm_img,original)

    def test_padding_adapter_restores_after_error(self):
        original=lambda image,ratio:image
        rec=SimpleNamespace(resize_norm_img=original)
        def fail(images):raise RuntimeError('inference interrupted')
        with self.assertRaises(RuntimeError):recognize_padded(rec,fail,[],30)
        self.assertIs(rec.resize_norm_img,original)


if __name__=='__main__':unittest.main(verbosity=2)
