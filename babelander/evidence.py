"""Bounded, immutable capture previews; never persisted to history or disk."""
import math
import cv2
from .types import CaptureEvidence


def evidence(mode, generation, frame, lines):
    height, width = frame.shape[:2]
    # Preview only. Full-resolution pixels remain the OCR input.
    scale = min(1, 640/width, 400/height)
    size = (max(1, round(width*scale)), max(1, round(height*scale)))
    preview = cv2.resize(frame, size, interpolation=cv2.INTER_AREA) if scale < 1 else frame
    # OCR adapters can return mutable box arrays. Freeze the entire payload.
    from .types import OCRLine
    frozen = tuple(OCRLine(line.text, tuple(tuple(float(v) for v in p) for p in line.box),
                           confidence(line.confidence)) for line in lines)
    return CaptureEvidence(mode, generation, width, height, *size, preview.tobytes(), frozen)


def confidence(value):
    value = float(value)
    return min(1, max(0, value)) if math.isfinite(value) else 0
