"""Opt-in outlined dim-glyph hint; bounded signatures, no OCR or frame history."""
import hashlib
import cv2
import numpy as np


def dim_signature(image):
    if not isinstance(image,np.ndarray) or image.ndim!=3 or image.shape[2]!=3:return None
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    gradient=cv2.morphologyEx(gray,cv2.MORPH_GRADIENT,np.ones((3,3),np.uint8))
    mask=((gradient>=60)&(gray>=130)&(gray<220)).astype(np.uint8)
    count,labels,components,_=cv2.connectedComponentsWithStats(mask,8)
    boxes=[]
    for x,y,w,h,area in components[1:]:
        if not (6<=w<=600 and 9<=h<=70 and area>=20):continue
        if np.any(gray[y:y+h,x:x+w]>=220):continue
        boxes.append((int(x)//3,int(y)//3,int(w)//3,int(h)//3,int(area)//16))
        if len(boxes)>256:return None
    # A couple of shapes are too weak a hint; raw-frame watchdog still runs.
    if len(boxes)<3:return None
    boxes.sort()
    return hashlib.sha256(repr(boxes).encode()).digest()


class StableDimSignature:
    """Changes must agree across two real observations at least 70 ms apart.

    Moving shapes generally disagree; stationary shapes can still trigger OCR.
    This is a hint, not a universal detector or a replacement for the watchdog.
    """
    def __init__(self):
        self.initialized=False
        self.current=self.candidate=None
        self.since=0.

    def observe(self,signature,now):
        if not self.initialized:
            self.initialized=True;self.current=self.candidate=signature;self.since=now
        elif signature==self.current:
            self.candidate=signature;self.since=now
        elif signature!=self.candidate:
            self.candidate=signature;self.since=now
        elif now-self.since>=.07:
            self.current=signature
        return self.current
