"""Session-local horizontal line hints for an opt-in bright-subtitle fast path.

No images/text retained. This is not a detector for dim or mixed-color text;
full detection is required periodically and whenever visible geometry differs.
"""
import math
import time
import numpy as np


class SubtitleLayout:
    def __init__(self):
        self.shape=None
        self.rows=()
        self.learned_at=0
        self.reuses=0
        self.last_path='full'
        self.last_reason='initial'
        self.last_key=None

    def reset(self, reason):
        self.shape=None
        self.rows=()
        self.reuses=0
        self.last_reason=reason
        self.last_key=None

    def learn(self, image, lines, now=None, key=None):
        self.reset('unreliable_layout')
        if not isinstance(image,np.ndarray) or image.ndim!=3 or not 1<=len(lines)<=4:return
        height,width=image.shape[:2]
        rows=[]
        for line in lines:
            if not math.isfinite(line.confidence) or line.confidence<.90 or len(line.box)!=4:return
            points=np.asarray(line.box,dtype=float)
            if points.shape!=(4,2) or not np.isfinite(points).all():return
            x0,y0=points.min(axis=0);x1,y1=points.max(axis=0)
            if x0<0 or y0<0 or x1>width or y1>height or x1-x0<20 or not 14<=y1-y0<=100:return
            if abs(points[0,1]-points[1,1])>4 or abs(points[2,1]-points[3,1])>4:return
            rows.append((int(y0),math.ceil(y1)))
        rows.sort()
        if any(b[0]<a[1] for a,b in zip(rows,rows[1:])):return
        # Padding must not make neighboring subtitle lines overlap. Split the
        # gap at its midpoint while retaining every detected glyph pixel.
        rows=[(max(0,top-6,(rows[i-1][1]+top)//2 if i else 0),
               min(height,bottom+6,(bottom+rows[i+1][0])//2 if i+1<len(rows) else height))
              for i,(top,bottom) in enumerate(rows)]
        self.shape=image.shape
        self.rows=tuple(rows)
        self.learned_at=time.perf_counter() if now is None else now
        self.last_key=key
        self.last_reason='learned'

    def propose(self, image, now=None, key=None):
        self.last_path='full'
        now=time.perf_counter() if now is None else now
        if not self.rows or not isinstance(image,np.ndarray) or image.shape!=self.shape:
            self.last_reason='shape_or_initial';return None
        # A watchdog reread of the same glyph episode refreshes full detection;
        # do not spend the entire hint lifetime only on repeated old subtitles.
        if key is not None and key==self.last_key:
            self.last_reason='episode_recheck';return None
        if now-self.learned_at>=2 or self.reuses>=3:
            self.last_reason='periodic_detection';return None
        # Require isolated near-white glyphs. Bright colored/dim transitions
        # deliberately use full detection. Low-luminance mixed text remains an
        # unsupported case, so this option must not silently become a default.
        low=image.min(axis=2);high=image.max(axis=2)
        mask=low>=220
        ink=int(mask.sum())
        if ink<40 or ink/image.shape[0]/image.shape[1]>.20:
            self.last_reason='no_isolated_ink';return None
        if np.any((high>=190)&~mask):
            # Antialiased neutral gray is allowed; saturated foreground isn't.
            colored=(high.astype(np.int16)-low.astype(np.int16)>35)&(high>=190)
            if np.any(colored):self.last_reason='colored_foreground';return None
        covered=np.zeros(image.shape[0],dtype=bool)
        for top,bottom in self.rows:covered[top:bottom]=True
        if np.any(mask[~covered]):
            self.last_reason='new_or_moved_line';return None
        boxes=[]
        for top,bottom in self.rows:
            yy,xx=np.nonzero(mask[top:bottom])
            if len(xx)<40 or yy.max()-yy.min()<10:
                self.last_reason='missing_or_small_line';return None
            y0=int(yy.min())+top;y1=int(yy.max())+top+1
            padding=max(4,math.ceil((y1-y0)*.15))
            x0=max(0,int(xx.min())-padding);x1=min(image.shape[1],int(xx.max())+1+padding)
            y0=max(top,y0-padding);y1=min(bottom,y1+padding)
            if x1-x0<20 or x1-x0<y1-y0:
                self.last_reason='non_horizontal';return None
            boxes.append((x0,y0,x1,y1))
        self.last_reason='candidate'
        return boxes

    def accepted(self, key=None):
        self.reuses+=1
        self.last_path='line_reuse'
        self.last_reason='accepted'
        self.last_key=key
