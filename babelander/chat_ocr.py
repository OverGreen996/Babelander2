"""Session-local recognition reuse. Detection still examines the entire chat ROI.

Reuse identical normalized-context crops, or verify unchanged source pixels
around the entire line despite detector wobble. At most 64 previous patches,
4 MiB total, live only for this session; never write private text or pixels.
"""
from collections import OrderedDict
from dataclasses import replace
import hashlib
import time

import numpy as np


class ChatRecognitionCache:
    def __init__(self, capacity=64):
        self.capacity = max(0, min(64, capacity))
        self.entries = OrderedDict()
        self.scope = None
        self.last = {}
        self.regions = []
        self.current_regions = None

    def clear(self):
        self.entries.clear()
        self.scope = None
        self.last = {}
        self.regions.clear()
        self.current_regions = None

    def prepare_regions(self, image, boxes):
        self.current_regions = (image, boxes)

    def release_frame(self):
        self.current_regions = None

    def _region_hit(self, index):
        if self.current_regions is None:
            return None
        image, boxes = self.current_regions
        box = boxes[index]
        lo, hi = np.min(box,axis=0), np.max(box,axis=0)
        for old_box, patch, origin, text, score in self.regions:
            old_lo, old_hi = np.min(old_box,axis=0), np.max(old_box,axis=0)
            if np.max(np.abs((hi-lo)-(old_hi-old_lo))) > 4:
                continue
            center_shift = np.rint((lo+hi-old_lo-old_hi)/2).astype(int)
            # Detection can wobble; content is verified with an exact original
            # pixel comparison including an eight-pixel guard on every side.
            for dy in (0,-1,1,-2,2):
                for dx in (0,-1,1,-2,2):
                    shift = center_shift + (dx,dy)
                    if np.max(np.abs(box-shift-old_box)) > 4:
                        continue
                    x,y = origin + shift
                    h,w = patch.shape[:2]
                    if x < 0 or y < 0 or x+w > image.shape[1] or y+h > image.shape[0]:
                        continue
                    if not (lo[0] >= x+4 and lo[1] >= y+4 and hi[0] <= x+w-4 and hi[1] <= y+h-4):
                        continue
                    if np.array_equal(patch,image[y:y+h,x:x+w]):
                        return text,score
        return None

    def _save_regions(self, texts, scores):
        self.regions.clear()
        if self.current_regions is None or not self.capacity:
            return
        image, boxes = self.current_regions
        stored = 0
        for box,text,score in zip(boxes,texts,scores):
            if not text or len(text)>2048 or not np.isfinite(score) or score<.98:
                continue
            lo=np.floor(np.min(box,axis=0)).astype(int)-8
            hi=np.ceil(np.max(box,axis=0)).astype(int)+9
            x,y=lo;right,bottom=hi
            if x<0 or y<0 or right>image.shape[1] or bottom>image.shape[0]:continue
            size=(right-x)*(bottom-y)*image.shape[2]*image.itemsize
            if size>131072 or stored+size>4*1024*1024:continue
            self.regions.append((box.copy(),image[y:bottom,x:right].copy(),lo,text,float(score)))
            stored+=size
            if len(self.regions)>=self.capacity:break

    def _remember(self, key, text, score):
        if self.capacity and text and len(text) <= 2048 and np.isfinite(score) and score >= .98:
            self.entries[key] = (text, float(score))
            self.entries.move_to_end(key)
            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)

    def recognize(self, images, original, recognizer, token, scope, word_boxes=False):
        token.check()
        started = time.perf_counter()
        if scope != self.scope:
            current_regions = self.current_regions
            self.clear()
            self.scope = scope
            self.current_regions = current_regions
        self.last = {'crops': len(images), 'reused': 0, 'inferred': 0, 'context_crops': 0, 'fallback': 0, 'region_reused': 0}
        # This adapter is deliberately limited to RapidOCR's width-sorted CPU
        # recognizer with line-level results. Unsupported paths use full OCR.
        batch = getattr(recognizer, 'rec_batch_num', None)
        shape = getattr(recognizer, 'rec_image_shape', None)
        if (word_boxes or not images or not isinstance(batch, int) or batch < 1
                or shape is None or len(shape) != 3 or min(shape) <= 0
                or any(im.ndim != 3 or im.shape[0] <= 0 or im.shape[2] != shape[0] for im in images)):
            self.last['fallback'] = 1
            result = original(images)
            token.check()
            return result
        ratios = [im.shape[1] / float(im.shape[0]) for im in images]
        indices = np.argsort(np.array(ratios))
        groups, keys = [], [None] * len(images)
        for start in range(0, len(images), batch):
            group = [int(i) for i in indices[start:start + batch]]
            width_ratio = max(shape[2] / shape[1], *(ratios[i] for i in group))
            # Same integer normalization width as TextRecognizer.resize_norm_img.
            width = int(shape[1] * width_ratio)
            groups.append(group)
            for i in group:
                im = images[i]
                keys[i] = (tuple(shape), width, im.shape, im.dtype.str,
                           hashlib.sha256(im.tobytes()).digest())
        hits = [self.entries.get(key) for key in keys]
        if self.current_regions is not None and len(self.current_regions[1]) == len(images):
            for i,hit in enumerate(hits):
                if hit is None:
                    hits[i]=self._region_hit(i)
                    if hits[i] is not None:self.last['region_reused']+=1
        self.last['reused'] = sum(hit is not None for hit in hits)
        if not self.last['reused']:
            result = original(images)
            token.check()
            if not self._valid(result, len(images)):
                return result
            self.last['inferred'] = len(images)
            for key, text, score in zip(keys, result.txts, result.scores):
                self._remember(key, text, score)
            self._save_regions(result.txts,result.scores)
            return result
        results = list(hits)
        template = None
        for group in groups:
            missing = [i for i in group if hits[i] is None]
            if not missing:
                continue
            widest = max(group, key=lambda i: ratios[i])
            work = list(missing)
            if ratios[widest] > max(shape[2] / shape[1], *(ratios[i] for i in missing)):
                work.append(widest)
                self.last['context_crops'] += 1
            token.check()
            template = original([images[i] for i in work])
            token.check()
            self.last['inferred'] += len(work)
            if not self._valid(template, len(work)):
                # Never publish a partially assembled recognition result.
                self.clear()
                self.last = {'crops': len(images), 'reused': 0, 'inferred': len(images),
                             'context_crops': 0, 'fallback': 1}
                result = original(images)
                token.check()
                return result
            for offset, i in enumerate(missing):
                results[i] = (template.txts[offset], template.scores[offset])
        token.check()
        for key, (text, score) in zip(keys, results):
            self._remember(key, text, score)
        self._save_regions([r[0] for r in results],[r[1] for r in results])
        if template is None:
            from rapidocr.ch_ppocr_rec.typings import TextRecOutput
            template = TextRecOutput()
        return replace(template, imgs=images, txts=tuple(r[0] for r in results),
                       scores=tuple(float(r[1]) for r in results),
                       word_results=tuple(None for _ in images),
                       elapse=time.perf_counter() - started)

    @staticmethod
    def _valid(result, length):
        return (result.txts is not None and result.scores is not None
                and len(result.txts) == len(result.scores) == length
                and all(isinstance(t, str) and np.isfinite(s) for t, s in zip(result.txts, result.scores)))
