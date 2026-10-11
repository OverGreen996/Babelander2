"""Bit-identical detector normalization without full-frame float64 arrays."""
import cv2
import numpy as np
from rapidocr.ch_ppocr_det.utils import DetPreProcess


def recognize_padded(recognizer, original, images, width_ratio):
    """Use the original group's normalization width for uncached rows only.

    The owning OCR lock must be held, and word-box mode must be disabled.
    Upstream decoding and language handling stay in ``original``.
    """
    normalize = recognizer.resize_norm_img
    recognizer.resize_norm_img = lambda image, _: normalize(image,width_ratio)
    try:
        return original(images)
    finally:
        recognizer.resize_norm_img = normalize


class LookupDetPreProcess(DetPreProcess):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep upstream operation order and rounding, including the initial
        # float32 multiplication. Only the final network tensor is float32.
        values = np.arange(256, dtype=np.float32)[:, None]
        self.lookup = ((values*self.scale-self.mean)/self.std).astype(np.float32).reshape(1,256,3)

    def normalize(self, image):
        if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
            return super().normalize(image)
        return cv2.LUT(image, self.lookup)


def install_detector_preprocess(detector):
    """Preserve RapidOCR's dynamic resolution policy and cache three operators."""
    original = detector.get_preprocess
    operators = {}

    def get_preprocess(max_wh):
        # Ask upstream for its policy; never substitute a smaller resolution.
        configured = original(max_wh)
        key = (configured.limit_side_len, configured.limit_type,
               tuple(configured.mean), tuple(configured.std), configured.scale)
        if key not in operators:
            operator = LookupDetPreProcess(configured.limit_side_len, configured.limit_type,
                                           configured.mean, configured.std)
            if configured.scale != operator.scale:
                return configured
            # A future upstream policy must not grow this cache indefinitely.
            if len(operators) >= 3:
                operators.clear()
            operators[key] = operator
        return operators[key]

    detector.get_preprocess = get_preprocess
