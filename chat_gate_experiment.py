"""Candidate only: bounded RGB spatial-band change gate, evaluated offscreen."""
import numpy as np
from PIL import Image,ImageFilter


class ChatNoiseGate:
    def __init__(self, refresh_ms=400):
        self.refresh=refresh_ms/1000
        self.clear()

    def clear(self):
        self.reference=None;self.focus=None;self.pending=None
        self.raw=None;self.observed_at=float('-inf');self.armed=False
        self.reason='first';self.last={}

    def features(self,image):
        # Bound both retained state and per-capture processing. Large/unknown
        # formats use the existing full-OCR path, never silently downscale OCR.
        if (not isinstance(image,np.ndarray) or image.dtype!=np.uint8 or
            image.ndim!=3 or image.shape[2]!=3 or min(image.shape[:2])<8 or
            image.shape[0]*image.shape[1]>1_048_576):return None
        # Pillow's separable box filters run on the coordinator; do not change
        # global OpenCV threading or add a background image-processing pool.
        small=Image.fromarray(image).reduce(2)
        fine=np.asarray(small.filter(ImageFilter.BoxBlur(1)),dtype=np.int16)
        coarse=np.asarray(small.filter(ImageFilter.BoxBlur(7)),dtype=np.int16)
        return fine-coarse

    def due(self,image,raw,now):
        self.pending=None
        if raw==self.raw:self.reason='identical';return False
        self.pending=self.features(image)
        if self.pending is None:self.reason='unsupported';return True
        if self.reference is None or self.reference.shape!=self.pending.shape:
            self.reason='first';return True
        if not self.armed:self.reason='unconfirmed';return True
        if now-self.observed_at>=self.refresh:self.reason='refresh';return True
        delta=np.max(np.abs(self.pending-self.reference),axis=2)
        changed=(delta>8)|((delta>6)&self.focus)
        # Several neighbouring changed samples, including outside old boxes,
        # detect new rows and longer replacements. No fuzzy OCR text matching.
        sums=np.pad(changed.astype(np.int32),((2,2),(2,2))).cumsum(0,dtype=np.int32).cumsum(1,dtype=np.int32)
        counts=sums[4:,4:]-sums[:-4,4:]-sums[4:,:-4]+sums[:-4,:-4]
        self.last={'max_local_changes':int(counts.max()),'changed_samples':int(np.count_nonzero(changed))}
        due=bool(np.any(counts>=4))
        self.reason='structure' if due else 'noise'
        return due

    def observed(self,image,raw,lines,started):
        self.reference=self.pending
        if self.reference is None:self.reference=self.features(image)
        self.pending=None;self.raw=raw;self.observed_at=started
        self.armed=False;self.focus=None
        if self.reference is None:return
        h,w=self.reference.shape[:2];self.focus=np.zeros((h,w),dtype=bool)
        for line in lines:
            if not line.text or line.confidence<.9:continue
            box=np.asarray(line.box)
            if box.shape!=(4,2) or not np.all(np.isfinite(box)):continue
            lo=np.floor(box.min(axis=0)/2).astype(int)-3
            hi=np.ceil(box.max(axis=0)/2).astype(int)+4
            x0,y0=np.maximum(lo,0);x1,y1=np.minimum(hi,(w,h))
            if x1>x0 and y1>y0:self.focus[y0:y1,x0:x1]=True;self.armed=True


class SignatureAdapter:
    """Use the unmodified production loop for candidate A/B experiments."""
    def __init__(self,signature):
        self.signature=signature;self.gate=ChatNoiseGate();self.output=None
        self.raw=None;self.started=0;self.counts={}

    def __call__(self,image):
        import time
        self.raw=self.signature(image);self.started=time.monotonic()
        if self.gate.due(image,self.raw,self.started):self.output=self.raw
        key=self.gate.reason;self.counts[key]=self.counts.get(key,0)+1
        return self.output

    def observed(self,image,lines):
        self.gate.observed(image,self.raw,lines,self.started)
