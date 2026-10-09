"""Cheap dialogue foreground checks with a bounded full-OCR fallback."""
import hashlib
import re
import numpy as np
from dataclasses import dataclass
import threading
import time

from .types import Cancelled
from .capture import CaptureUnavailable


def dialogue_text_key(text):
    """Deduplicate OCR-only terminal period noise within the same epoch.

    Keep numerical punctuation, negation, internal punctuation, question marks
    and exclamation marks. Raw OCR text still goes to translation/review.
    """
    return re.sub(r'(?<=[A-Za-z])\.$','', ' '.join(text.split()))


def bright_signature(image):
    """Track bright glyphs without retaining a frame or running another model.

    This is a fast path, not a universal text detector. A periodic raw-image
    fallback checks dim text and mixed colors even when bright pixels stay put.
    """
    if not isinstance(image,np.ndarray) or image.ndim!=3 or image.shape[2]<3:
        return None
    brightest=np.maximum(np.maximum(image[:,:,0],image[:,:,1]),image[:,:,2])
    mask=brightest>=220
    coverage=np.count_nonzero(mask)/mask.size
    if not .001<=coverage<=.65:
        return None
    return hashlib.sha256(np.packbits(mask).tobytes()).digest()


class DialogueFrameGate:
    def __init__(self, fallback_ms=800, background_ms=1200, adaptive=False):
        self.fallback_seconds=max(.1,fallback_ms/1000)
        self.background_seconds=max(self.fallback_seconds,background_ms/1000)
        self.raw=None
        self.ink=None
        self.observed_at=float('-inf')
        self.base_background_seconds=self.background_seconds
        self.adaptive=adaptive
        self.last_text=None
        self.repeat_count=0

    def due(self, raw, ink, now):
        if self.raw is None:return True
        if raw==self.raw:return False
        if ink!=self.ink and (ink is not None or self.ink is not None):return True
        interval=self.background_seconds if ink is not None else self.fallback_seconds
        return now-self.observed_at>=interval

    def observed(self, raw, ink, now):
        if ink!=self.ink:
            self.background_seconds=self.base_background_seconds
            self.repeat_count=0
        self.raw,self.ink,self.observed_at=raw,ink,now

    def recognized(self, text, reliable):
        # Experimental bright-text budget. Never delay an ink change or the
        # dim-text fallback. Mixed bright/dim short cues still need real recall
        # testing before this option can become a default.
        if not self.adaptive:return
        text=dialogue_text_key(text)
        if text and reliable and self.ink is not None and text==self.last_text:
            self.repeat_count=min(2,self.repeat_count+1)
            self.background_seconds=max(self.base_background_seconds,(2,3)[self.repeat_count-1])
        else:
            self.repeat_count=0
            self.background_seconds=self.base_background_seconds
        self.last_text=text if reliable else None


@dataclass(frozen=True)
class FrameSample:
    seq: int
    epoch: int
    captured_at: float
    capture_ms: float
    filter_ms: float
    raw: object
    ink: object
    structure: object = None

    @property
    def key(self):
        if self.structure is not None:
            return ('outlined',self.ink,self.structure)
        return ('ink',self.ink) if self.ink is not None else ('raw',self.raw)


@dataclass(frozen=True)
class FrameCandidate:
    sample: FrameSample
    image: object


class DialogueCapture:
    """One active ROI + one latest pending ROI; capture never waits for OCR.

    The producer also owns one transient capture. Native GDI has additional
    temporary allocations; counters describe owned ndarray bytes, not RSS.
    Samples contain hashes/timestamps only and retain no image history.
    """
    def __init__(self, capture, raw_hash, ink_hash, settings, token, metrics, mode, status):
        self.capture,self.raw_hash,self.ink_hash=capture,raw_hash,ink_hash
        self.settings,self.token,self.metrics,self.mode,self.status=settings,token,metrics,mode,status
        self.condition=threading.Condition()
        self.gate=DialogueFrameGate(settings.scan_ms,adaptive=settings.adaptive_ocr_recheck)
        self.dim_probe=None
        if settings.mixed_text_trigger:
            from .subtitle_trigger import StableDimSignature
            self.dim_probe=StableDimSignature()
        self.pending=self.active=self.latest=None
        self.epoch=0
        self.recognized_epoch=0
        self.peak_roi_bytes=0
        self.closed=False
        self.error=None
        self.wake_at=float('inf')
        self.thread=threading.Thread(target=self.run,name='Babelander2-dialog-capture',daemon=True)

    def start(self):self.thread.start()

    def snapshot(self):
        with self.condition:
            return {'pending':int(self.pending is not None),'in_flight':int(self.active is not None),
                    'pending_limit':1,'epoch':self.epoch,
                    'owned_roi_bytes':sum(getattr(p.image,'nbytes',0) for p in (self.pending,self.active) if p is not None),
                    'owned_roi_peak_bytes':self.peak_roi_bytes}

    def request_sample(self, at):
        with self.condition:
            self.wake_at=min(self.wake_at,at)
            self.condition.notify_all()

    def sequence(self):
        with self.condition:
            return self.latest.seq if self.latest is not None else 0

    def take(self, timeout=.05, after_seq=None):
        with self.condition:
            # A notification is ephemeral; a newer sequence persists even if
            # capture completed before the consumer began waiting. Spurious
            # notifications alone must not finish the wait.
            self.condition.wait_for(lambda:self.pending is not None or self.closed or self.token.cancelled() or
                                    (after_seq is not None and self.latest is not None and self.latest.seq>after_seq),timeout)
            self.token.check()
            if self.error:raise self.error
            if self.pending is None:return None
            self.active,self.pending=self.pending,None
            return self.active

    def observed(self, candidate, text='', reliable=False):
        with self.condition:
            sample=candidate.sample
            self.gate.observed(sample.raw,sample.ink,time.perf_counter())
            self.recognized_epoch=sample.epoch
            if self.epoch==sample.epoch:self.gate.recognized(text,reliable)
            self.active=None
            self.condition.notify_all()

    def confirmation(self, sample, after):
        with self.condition:
            latest=self.latest
            return latest if latest is not None and latest.seq>sample.seq and latest.captured_at>=after and latest.key==sample.key and latest.epoch==sample.epoch else None

    def current(self, sample):
        with self.condition:
            return self.epoch==sample.epoch

    def run(self):
        failures=0
        try:
            while not self.token.cancelled():
                with self.condition:
                    if self.closed:return
                    self.wake_at=float('inf')
                started=time.perf_counter()
                try:
                    image=self.capture()
                except CaptureUnavailable as error:
                    failures+=1
                    if failures>=3:raise CaptureUnavailable(str(error)+' 連續三次擷取失敗，監測已停止。') from None
                    self.status(f'畫面暫時無法擷取 · 重試 {failures}/2')
                    self.token.event.wait(failures)
                    continue
                failures=0
                capture_ms=(time.perf_counter()-started)*1000
                at=time.perf_counter()
                raw,ink=self.raw_hash(image),self.ink_hash(image)
                structure=None
                if self.dim_probe is not None:
                    from .subtitle_trigger import dim_signature
                    structure=self.dim_probe.observe(dim_signature(image),started)
                filter_ms=(time.perf_counter()-at)*1000
                self.token.check()
                if isinstance(image,np.ndarray):image.setflags(write=False)
                with self.condition:
                    if self.closed:return
                    previous=self.latest
                    self.peak_roi_bytes=max(self.peak_roi_bytes,getattr(image,'nbytes',0)+self.snapshot()['owned_roi_bytes'])
                    if previous is None or ink!=previous.ink or structure!=previous.structure:
                        self.epoch+=1
                        if previous is not None and structure!=previous.structure:
                            self.metrics.add('dim_structure_changed',self.mode)
                    sample=FrameSample(1 if previous is None else previous.seq+1,self.epoch,started,capture_ms,filter_ms,raw,ink,structure)
                    self.latest=sample
                    self.condition.notify_all()
                    self.metrics.add('capture',self.mode,capture_ms=capture_ms,change_detection_ms=filter_ms,
                                     capture_deadline_miss_ms=max(0,(started-self.next_due)*1000) if hasattr(self,'next_due') else 0,
                                     frame_seq=sample.seq,capture_epoch=sample.epoch,
                                     producer_transient_roi_bytes=getattr(image,'nbytes',0))
                    # Returning to the active glyphs also supersedes a queued
                    # different frame; that pending frame must not run later.
                    if self.active is not None and self.active.sample.key==sample.key and self.active.sample.epoch==sample.epoch:
                        if self.pending is not None and self.pending.sample.key!=sample.key:
                            self.pending=None;self.metrics.add('ocr_candidate_superseded',self.mode)
                    elif self.pending is not None and self.pending.sample.key==sample.key and self.pending.sample.epoch==sample.epoch:
                        pass  # Preserve its first observed time and immutable ROI.
                    elif self.gate.due(raw,ink,started) or sample.epoch!=self.recognized_epoch:
                        if self.pending is not None:self.metrics.add('ocr_candidate_superseded',self.mode)
                        self.pending=FrameCandidate(sample,image)
                        self.metrics.add('ocr_candidate_created',self.mode,**self.snapshot())
                        self.condition.notify_all()
                    else:self.metrics.add('background_filtered' if previous is not None and raw!=previous.raw else 'frame_unchanged',self.mode)
                    # A short stability window gets a real confirmation frame
                    # even when the configured normal observation is slower.
                    due=started+self.settings.dialog_scan_ms/1000
                    if previous is None or previous.key!=sample.key:
                        if self.settings.stable_ms>0:due=min(due,started+self.settings.stable_ms/1000)
                del image
                with self.condition:
                    self.next_due=due
                    while not self.closed and not self.token.cancelled():
                        deadline=min(due,self.wake_at)
                        delay=deadline-time.perf_counter()
                        if delay<=0:break
                        self.condition.wait(min(delay,.05))
        except Cancelled:
            pass
        except Exception as error:
            with self.condition:self.error=error;self.condition.notify_all()
        finally:
            with self.condition:self.closed=True;self.condition.notify_all()

    def close(self):
        with self.condition:
            self.closed=True
            if self.pending is not None:
                self.pending=None;self.metrics.add('ocr_candidate_cancelled',self.mode)
            self.condition.notify_all()
        self.thread.join()
        with self.condition:self.active=None
