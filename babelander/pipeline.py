"""Bounded live translation and text-free telemetry; workers never own frames."""
from collections import Counter, deque
from collections import OrderedDict
import hashlib
from dataclasses import dataclass
import threading
import time

from .types import Cancelled, Cancellation, Mode, JobResult


class Telemetry:
    def __init__(self):
        self.lock = threading.RLock()
        self.counts = Counter()
        self.recent = deque(maxlen=128)

    def add(self, reason, mode=None, **values):
        # Callers supply fixed reason/stage names and numbers, never user text.
        with self.lock:
            self.counts[reason] += 1
            self.recent.append({'reason':reason,'mode':str(mode or ''),
                                **{k:round(v,3) for k,v in values.items() if isinstance(v,(float,int))}})

    def snapshot(self):
        with self.lock:
            recent = list(self.recent)
            samples = {}
            for row in recent:
                for key,value in row.items():
                    if key.endswith('_ms') and isinstance(value,(float,int)):
                        samples.setdefault(key,[]).append(value)
            summaries = {}
            for key,values in samples.items():
                values.sort()
                summaries[key] = {'samples':len(values),'p50':values[int((len(values)-1)*.5)],
                                  'p95':values[int((len(values)-1)*.95)],'max':values[-1]}
            return {'counts':dict(self.counts),'recent':recent,'record_limit':128,'timings':summaries,
                    'ttft_ms':None,'prefill_ms':None,'decode_ms':None,
                    'text_or_images_retained':False}


@dataclass(frozen=True)
class LiveEvent:
    revision: int
    lines: tuple
    started: float
    ocr_ms: float
    stages: tuple = ()
    prefix: str = ''
    source: str = ''
    offered: float = 0
    capture_epoch: int = 0


class LiveDispatcher:
    """One client in-flight; dialogue latest-only, chat FIFO <= 8 events."""
    def __init__(self, controller, mode, generation, token):
        self.controller,self.mode,self.generation,self.token = controller,mode,generation,token
        self.condition = threading.Condition()
        self.pending = deque()
        self.closed = False
        self.active = False
        self.rejected = OrderedDict()
        self.worker = threading.Thread(target=self.run,name='Babelander2-live-'+mode.value,daemon=True)
        self.worker.start()

    def offer(self, event):
        with self.condition:
            self.controller.metrics.add('events_created',self.mode)
            if self.closed or self.token.cancelled():
                self.controller.metrics.add('cancelled',self.mode)
                return
            if self.mode == Mode.DIALOG:
                while self.pending:
                    self.pending.popleft()
                    self.controller.metrics.add('skipped_superseded',self.mode)
            elif len(self.pending) >= 8:
                self.pending.popleft()
                self.controller.metrics.add('skipped_capacity',self.mode)
            self.pending.append(event)
            self.condition.notify()

    def discard_pending(self):
        with self.condition:
            while self.pending:
                self.pending.popleft()
                self.controller.metrics.add('skipped_superseded',self.mode)

    def snapshot(self):
        with self.condition:
            return {'pending':len(self.pending),'in_flight':int(self.active),
                    'pending_limit':1 if self.mode == Mode.DIALOG else 8}

    def run(self):
        from dataclasses import replace
        from .layout import OCRBlock,card_blocks
        while True:
            with self.condition:
                self.condition.wait_for(lambda:self.pending or self.closed)
                if not self.pending:
                    return
                event = self.pending.popleft()
                self.active = True
            try:
                self.token.check()
                submitted = time.perf_counter()
                settings = self.controller.settings
                text = '\n'.join(line.text for line in event.lines)
                key = hashlib.sha256(repr((text,self.mode.value,settings.provider(self.mode),
                    settings.model_path,settings.server_path,settings.profile,settings.azure_region,
                    settings.deepl_free,self.controller.engine.configuration_revision,self.controller.store.terms(),'v2-prompt-6')).encode()).hexdigest()
                if key in self.rejected:
                    result = replace(self.rejected[key],model_ms=0,queue_ms=0,postprocess_ms=0,backend_state='suppressed')
                    self.controller.metrics.add('negative_suppressed',self.mode)
                else:
                    result = self.controller._translate_blocks(self.mode,self.token,[OCRBlock(event.lines)])[0]
                    if result.warning and result.backend_state in ('cold','warm','cloud'):
                        self.rejected[key] = result
                        while len(self.rejected)>128:self.rejected.popitem(last=False)
                if event.prefix:
                    result = replace(result,source=event.source,target=(event.prefix+' '+result.target) if result.target else '')
                stages = event.stages+(('dispatch_wait_ms',max(0,(submitted-(event.offered or event.started))*1000)),)
                self.controller._emit(self.mode,self.generation,self.token,(result,),event.ocr_ms,
                                      event.started,event_id=event.revision,stages=stages,capture_epoch=event.capture_epoch)
                self.controller.metrics.add('success',self.mode)
                if result.cache_hit:self.controller.metrics.add('cache_hit',self.mode)
                if result.warning:self.controller.metrics.add('rejected',self.mode)
            except Cancelled:
                self.controller.metrics.add('cancelled',self.mode)
            except Exception as error:
                self.controller.metrics.add('error',self.mode)
                if self.controller.current(self.mode,self.generation):
                    self.controller.failed.emit(self.mode.value,str(error),self.generation)
                self.token.cancel()
            finally:
                with self.condition:self.active = False

    def close(self):
        with self.condition:
            self.closed = True
            while self.pending:
                self.pending.popleft()
                self.controller.metrics.add('cancelled',self.mode)
            self.condition.notify_all()
        self.worker.join()
