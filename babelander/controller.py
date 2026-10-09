"""Qt boundary: immutable results, independent OCR coordinators and generations."""
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from dataclasses import replace
import re
import threading
import time
from contextlib import contextmanager

from PySide6.QtCore import QObject, Signal

from .types import Mode, Cancellation, Cancelled, JobResult,Translation
from .layout import OCRBlock,card_blocks
from .chat import messages as chat_messages, split_message, filter_decorations
from .quest_layout import quest_blocks, numeric_lines, LITERAL as QUEST_LITERAL
from .equipment_layout import equipment_blocks,capture_layout
from .ocr import OCR, capture, signature
from .capture import CaptureUnavailable
from .evidence import evidence
from .pipeline import LiveDispatcher, LiveEvent, Telemetry
from .monitor import DialogueFrameGate,DialogueCapture,bright_signature,dialogue_text_key


def chunks(text):
    paragraphs = re.split(r'\n\s*\n',text.strip())
    output = []
    for paragraph in paragraphs:
        current = ''
        for sentence in re.split(r'(?<=[.!?。！？])\s+',paragraph.replace('\n',' ')):
            if current and len(current)+len(sentence)>450:
                output.append(current)
                current = ''
            current += (' ' if current else '')+sentence
        if current:
            output.append(current)
    return output


def new_chat_lines(previous, current):
    from .chat import message_key,anchored_overlap
    old_keys,new_keys=[message_key(text) for text in previous],[message_key(text) for text in current]
    if new_keys == old_keys:
        return []
    for size in range(min(len(previous),len(current)),0,-1):
        if old_keys[-size:] == new_keys[:size] or anchored_overlap(old_keys[-size:],new_keys[:size]):
            return current[size:]
    return list(current)


class Controller(QObject):
    preparation_done = Signal(int,object)
    captured = Signal(object)
    result = Signal(object)
    delivery = Signal(object)
    status = Signal(str,str,int)
    status_delivery = Signal(object)
    failed = Signal(str,str,int)
    started = Signal(str,int)
    finished = Signal(str,int)

    def __init__(self, engine, store, settings):
        super().__init__()
        self.engine,self.store,self.settings = engine,store,settings
        self.ocr = OCR(lambda:self.settings)
        self.executor = ThreadPoolExecutor(4,thread_name_prefix='Babelander2-coordinator')
        self.lock = threading.RLock()
        self.generations = {mode:0 for mode in Mode}
        self.tokens = {}
        self.closed = False
        self.preparation_id=0
        self.preparation_token=None
        self.preparation_future=None
        self.metrics = Telemetry()
        self.revisions = {mode:0 for mode in Mode}
        self.latest_snapshot = None
        self.capture_notice_pending = False
        self.ui_results = {}
        self.ui_pending = set()
        self.latest_status = {}
        self.status_pending = set()
        self.live = {}
        self.capture_streams = {}
        self.work_slots = threading.BoundedSemaphore(8)
        self.work_by_mode = {mode:0 for mode in Mode}
        self.image_condition = threading.Condition()
        self.image_waiters = deque()
        self.image_active = 0
        self.image_pixel_limit = 8_388_608

    def cancel(self, mode, release_model=True):
        with self.lock:
            token = self.tokens.get(mode)
            if token:
                token.cancel()
            self.generations[mode] += 1
            generation = self.generations[mode]
            self.ui_results.pop(mode,None)
            if self.latest_snapshot and self.latest_snapshot.mode == mode:self.latest_snapshot = None
            if token and release_model:self.engine.request_release()
        self._status(mode.value,'已停止／取消',generation)

    def _status(self, identifier, message, generation):
        with self.lock:
            if not self.current(Mode(identifier),generation):return
            self.latest_status[identifier] = (identifier,message,generation)
            if identifier not in self.status_pending:
                self.status_pending.add(identifier)
                self.status_delivery.emit(identifier)
        self.status.emit(identifier,message,generation)

    def take_status(self, identifier):
        with self.lock:
            self.status_pending.discard(identifier)
            return self.latest_status.pop(identifier,None)

    def current(self, mode, generation):
        with self.lock:
            return not self.closed and self.generations[mode] == generation

    def displayable(self, result):
        with self.lock:
            if not self.current(result.mode,result.generation):return False
            guard=getattr(self.tokens.get(result.mode),'focus_guard',None)
            if guard is not None and not guard():
                self.tokens[result.mode].cancel()
                return False
            if result.mode == Mode.DIALOG:
                if result.event_id and self.revisions[result.mode]!=result.event_id:return False
                if result.capture_epoch:
                    stream=self.capture_streams.get((result.mode,result.generation))
                    if stream is None or stream.snapshot()['epoch']!=result.capture_epoch:return False
            return True

    def take_result(self, mode):
        with self.lock:
            self.ui_pending.discard(mode)
            return self.ui_results.pop(mode,None)

    def take_capture(self):
        with self.lock:
            self.capture_notice_pending = False
            return self.latest_snapshot

    def _publish(self, result, notify_result=True):
        with self.lock:
            if not self.displayable(result):
                self.metrics.add('ui_suppressed_generation',result.mode)
                return
            previous = self.ui_results.get(result.mode)
            if previous and previous.translations:
                if result.mode == Mode.CHAT:
                    merged = previous.translations+result.translations
                    if len(merged)>100:self.metrics.add('chat_ui_capacity',result.mode)
                    result = replace(result,translations=merged[-100:])
                else:self.metrics.add('ui_coalesced',result.mode)
            self.ui_results[result.mode] = result
            if result.mode not in self.ui_pending:
                self.ui_pending.add(result.mode)
                self.delivery.emit(result.mode)
        # Compatibility/diagnostic signal is not used by production widgets.
        if notify_result:self.result.emit(result)

    def _revision(self, mode, generation=None):
        with self.lock:
            if generation is not None and not self.current(mode,generation):raise Cancelled('舊監測已停止')
            self.revisions[mode] += 1
            return self.revisions[mode]

    def _submit(self, mode, generation, token, function, *args):
        if not self.work_slots.acquire(blocking=False):
            token.cancel()
            self.metrics.add('coordinator_capacity',mode)
            self.failed.emit(mode.value,'工作已滿，請稍後再試。',generation)
            self.finished.emit(mode.value,generation)
            return
        with self.lock:self.work_by_mode[mode]+=1
        def release_slot(_=None):
            with self.lock:self.work_by_mode[mode]-=1
            self.work_slots.release()
        def run():
            lease = (mode,generation)
            try:
                with self.lock:
                    token.check()
                    if self.settings.provider(mode)=='local':self.engine.acquire_client(lease)
                function(mode,generation,token,*args)
            except Cancelled:
                self.finished.emit(mode.value,generation)
            finally:
                self.engine.release_client(lease)
        try:
            future = self.executor.submit(run)
            future.add_done_callback(release_slot)
        except BaseException:
            release_slot()
            raise

    def working(self, mode):
        with self.lock:return self.work_by_mode[mode]>0

    def prepare_local(self):
        if self.preparation_future is not None and not self.preparation_future.done():return self.preparation_id
        self.preparation_id+=1
        identifier=self.preparation_id
        token=self.preparation_token=Cancellation()
        future=self.engine.prepare_local(token)
        self.preparation_future=future
        def completed(done):
            try:report=done.result()
            except Exception as error:
                report={'ready':False,'cancelled':token.cancelled(),'error':str(error)}
            self.preparation_done.emit(identifier,report)
        future.add_done_callback(completed)
        return identifier

    def cancel_preparation(self, release_model=True):
        if self.preparation_token is not None:self.preparation_token.cancel()
        self.preparation_id+=1
        self.preparation_token=None
        self.preparation_future=None
        if release_model:self.engine.request_release()

    @contextmanager
    def _image(self, region, token):
        if region.width*region.height > self.image_pixel_limit:
            self.metrics.add('image_rejected_size')
            raise ValueError('框選超過 838 萬像素，請縮小範圍；辨識解析度不會自動降低。')
        at = time.perf_counter()
        ticket = object()
        admitted = False
        try:
            with self.image_condition:
                self.image_waiters.append(ticket)
                while True:
                    token.check()
                    if not self.image_active and self.image_waiters[0] is ticket:
                        self.image_waiters.popleft()
                        self.image_active = 1
                        admitted = True
                        break
                    self.image_condition.wait(.05)
            yield (time.perf_counter()-at)*1000
        finally:
            with self.image_condition:
                if admitted:self.image_active = 0
                elif ticket in self.image_waiters:self.image_waiters.remove(ticket)
                self.image_condition.notify_all()

    def _begin(self, mode, focus_guard=None):
        # A replacement job immediately needs the same model. Explicit Stop
        # releases it; replacing a generation must not race a model unload.
        self.cancel(mode,release_model=False)
        with self.lock:
            if self.closed:
                raise Cancelled('程式已關閉')
            if focus_guard is None:token=Cancellation()
            else:
                from .window_focus import FocusCancellation
                token=FocusCancellation(focus_guard)
            self.tokens[mode] = token
            generation = self.generations[mode]
        self.started.emit(mode.value,generation)
        return generation,token

    def submit_text(self, mode, text):
        generation,token = self._begin(mode)
        self._submit(mode,generation,token,self._job,text,None)

    def submit_region(self, mode, region, focus_guard=None):
        generation,token = self._begin(mode,focus_guard)
        self._submit(mode,generation,token,self._job,None,region)

    def _capture(self, region, token):
        token.check()
        frame=capture(region)
        token.check()
        return frame

    def _translate(self, mode, token, source):
        translated = []
        for paragraph in source:
            token.check()
            translated.append(self.engine.request(paragraph,mode,token))
        return tuple(translated)

    def _translate_blocks(self, mode, token, blocks):
        translated = []
        for block in blocks:
            token.check()
            warning = block.warning
            if block.confidence < self.settings.ocr_review_threshold and not (mode==Mode.QUEST and QUEST_LITERAL.fullmatch(block.text.strip())):
                warning = f'辨識信心 {block.confidence:.0%}，請核對原文後重新翻譯；監測中請先停止。'
            elif len(block.inference_text)>600:
                warning = '條件段落超過 600 字；請確認原文並分段，不會截斷條件。'
            if warning:
                result = Translation(block.text,'',self.settings.provider(mode),'未取得可靠譯文',warning=warning,ocr_confidence=block.confidence)
            else:
                result = self.engine.request(block.inference_text,mode,token)
                result = replace(result,source=block.text,ocr_confidence=block.confidence)
            translated.append(result)
        return tuple(translated)

    def _job(self, mode, generation, token, text, region):
        started = time.perf_counter()
        ocr_ms = 0
        blocks = None
        equipment_layout = None
        reserved_numeric = []
        try:
            if region:
                self._status(mode.value,'正在辨識框選文字…',generation)
                with self._image(region,token) as image_wait:
                    at = time.perf_counter()
                    frame = self._capture(region,token)
                    capture_ms = (time.perf_counter()-at)*1000
                    at = time.perf_counter()
                    lines = self.ocr.recognize(frame,token)
                    if mode==Mode.EQUIPMENT and lines:
                        lines=self.ocr.recover_equipment(frame,lines,token,
                            lambda proposed,accepted:self.metrics.add('equipment_numeric_retry',mode,candidates=proposed,accepted=accepted,rejected=proposed-accepted),
                            reserved_numeric.extend)
                    ocr_ms = (time.perf_counter()-at)*1000
                    self._capture_evidence(mode,generation,token,frame,lines)
                    if mode==Mode.EQUIPMENT and lines:
                        blocks=equipment_blocks(frame,lines,lambda line:self.metrics.add('equipment_decoration_filtered',mode,confidence=line.confidence))
                        equipment_layout=capture_layout(region,frame,blocks,reserved_boxes=reserved_numeric)
                    if mode==Mode.QUEST and lines:
                        lines=numeric_lines(frame,lines)
                        blocks=quest_blocks(frame,lines)
                        equipment_layout=capture_layout(region,frame,blocks,literal_pattern=QUEST_LITERAL)
                    del frame
                stages = (('image_queue_wait_ms',image_wait),('capture_ms',capture_ms),('ocr_ms',ocr_ms))
                if not lines:
                    raise ValueError('沒有辨識到文字，請重新框選或提高文字清晰度。')
                # Paragraph boundaries preserve wrapped conditions. Each block
                # still yields the model to queued subtitles after inference.
                if mode in (Mode.EQUIPMENT,Mode.QUEST):
                    pass  # Original positions/colors were captured before releasing the frame.
                elif mode==Mode.SCREEN:
                    from .types import OCRLine
                    confidence = min(l.confidence for l in lines)
                    blocks = [OCRBlock((OCRLine(text,(),confidence),)) for text in chunks('\n'.join(l.text for l in lines))]
                else:
                    blocks = [OCRBlock(tuple(lines))]
                source = None
            else:
                stages = ()
                source = [text.strip()] if mode in (Mode.REPLY,Mode.DIALOG) else chunks(text)
                if not source or not source[0]:
                    raise ValueError('請輸入或框選要翻譯的文字。')
            self._status(mode.value,'正在翻譯…',generation)
            translations = self._translate_blocks(mode,token,blocks) if blocks is not None else self._translate(mode,token,source)
            self._emit(mode,generation,token,translations,ocr_ms,started,stages=stages,equipment_layout=equipment_layout)
        except Cancelled:
            pass
        except Exception as error:
            if self.current(mode,generation):
                # Backend errors are sanitized by the transport; no traceback
                # containing request URLs/keys is sent to the UI or history.
                self.failed.emit(mode.value,str(error),generation)
        finally:
            self.finished.emit(mode.value,generation)

    def _emit(self, mode, generation, token, translations, ocr_ms, started, event_id=0, stages=(), capture_epoch=0, equipment_layout=None):
        with self.lock:
            token.check()
            if not self.current(mode,generation):
                return
            total_ms = (time.perf_counter()-started)*1000
            for translation in translations:
                self.store.record(mode,translation,total_ms)
            timing = stages+(('translation_queue_ms',sum(t.queue_ms for t in translations)),
                             ('translation_request_ms',sum(t.model_ms for t in translations)),
                             ('postprocess_ms',sum(t.postprocess_ms for t in translations)))
            self.metrics.add('pipeline_completed',mode,**dict(timing),observed_worker_ms=total_ms)
            result = JobResult(mode,generation,translations,ocr_ms,total_ms,event_id=event_id,
                               stages=timing,emitted_at=time.perf_counter(),capture_epoch=capture_epoch,equipment_layout=equipment_layout)
            if not self.displayable(result):
                self.metrics.add('ui_suppressed_stale',mode)
                return
            self._publish(result)
            warnings = sum(bool(t.warning) for t in translations)
            self._status(mode.value,f'完成 · {total_ms:.0f} ms'+(f' · {warnings} 段未取得可靠譯文' if warnings else ''),generation)

    def monitor(self, mode, region, focus_guard=None):
        if mode in (Mode.EQUIPMENT,Mode.QUEST):raise ValueError('裝備卡與任務卡只支援單次框選。')
        generation,token = self._begin(mode,focus_guard)
        self._submit(mode,generation,token,self._monitor,region)

    def _capture_evidence(self, mode, generation, token, frame, lines):
        snapshot = evidence(mode,generation,frame,lines)
        with self.lock:
            token.check()
            if self.current(mode,generation):
                self.latest_snapshot = snapshot
                if not self.capture_notice_pending:
                    self.capture_notice_pending = True
                    self.captured.emit(None)

    def _monitor(self, mode, generation, token, region):
        if mode==Mode.DIALOG:
            return self._monitor_dialog(mode,generation,token,region)
        last_signature = None
        pending_text,last_sent = None,None
        pending_quality = None
        pending_started,pending_ocr_ms = 0,0
        pending_lines = []
        pending_stages = ()
        pending_ocr_end = 0
        pending_revision = 0
        pending_confirmed = False
        gate = DialogueFrameGate(self.settings.scan_ms)
        since = 0
        previous_chat = []
        from .chat_ocr import ChatRecognitionCache
        chat_cache = ChatRecognitionCache() if mode == Mode.CHAT else None
        capture_failures = 0
        dispatcher = LiveDispatcher(self,mode,generation,token)
        with self.lock:self.live[(mode,generation)] = dispatcher
        try:
            while not token.cancelled():
                started = time.perf_counter()
                try:
                    with self._image(region,token) as image_wait:
                        token.check()
                        captured_at = time.perf_counter()
                        frame = self._capture(region,token)
                        capture_ms = (time.perf_counter()-captured_at)*1000
                        self.metrics.add('capture',mode,capture_ms=capture_ms)
                        filter_at = time.perf_counter()
                        fingerprint = signature(frame)
                        foreground = bright_signature(frame) if mode == Mode.DIALOG else None
                        filter_ms = (time.perf_counter()-filter_at)*1000
                        changed = gate.due(fingerprint,foreground,time.monotonic()) if mode == Mode.DIALOG else fingerprint != last_signature
                        if changed:
                            ocr_started = time.perf_counter()
                            lines = self.ocr.recognize(frame,token,chat_cache=chat_cache) if chat_cache is not None else self.ocr.recognize(frame,token)
                            ocr_ms = (time.perf_counter()-ocr_started)*1000
                            self.metrics.add('ocr',mode,ocr_ms=ocr_ms)
                            if chat_cache is not None:
                                self.metrics.add('chat_recognition',mode,**chat_cache.last)
                            self._capture_evidence(mode,generation,token,frame,lines)
                            gate.observed(fingerprint,foreground,time.monotonic())
                        else:self.metrics.add('background_filtered' if fingerprint!=last_signature else 'frame_unchanged',mode)
                        del frame
                except CaptureUnavailable as error:
                    capture_failures += 1
                    if capture_failures >= 3:
                        raise CaptureUnavailable(str(error)+' 連續三次擷取失敗，監測已停止。') from None
                    self._status(mode.value,f'畫面暫時無法擷取 · 重試 {capture_failures}/2',generation)
                    token.event.wait(capture_failures)
                    continue
                capture_failures = 0
                if changed:
                    last_signature = fingerprint
                    text = '\n'.join(l.text for l in lines)
                    stages = (('capture_ms',capture_ms),('change_detection_ms',filter_ms),
                              ('image_queue_wait_ms',image_wait),('ocr_ms',ocr_ms))
                    if mode == Mode.CHAT:
                        lines,decorations=filter_decorations(lines)
                        if decorations:self.metrics.add('chat_decorations_filtered',mode,count=decorations)
                        lines=chat_messages(lines)
                        current_chat = [l.text for l in lines]
                        new_lines = new_chat_lines(previous_chat,current_chat)
                        previous_chat = current_chat
                        if new_lines:
                            for index,line in enumerate(new_lines):
                                prefix,message = split_message(line)
                                observed = lines[len(lines)-len(new_lines)+index]
                                revision = self._revision(mode,generation)
                                dispatcher.offer(LiveEvent(revision,(replace(observed,text=message),),started,ocr_ms,
                                    stages,prefix,line,time.perf_counter()))
                    elif (text,min((l.confidence for l in lines),default=0)>=self.settings.ocr_review_threshold) != (pending_text,pending_quality):
                        pending_text,since = text,captured_at
                        pending_confirmed = False
                        pending_quality = min((l.confidence for l in lines),default=0)>=self.settings.ocr_review_threshold
                        pending_started,pending_ocr_ms = started,ocr_ms
                        pending_stages = stages
                        pending_ocr_end = time.perf_counter()
                        pending_lines = lines
                        # Invalidate as soon as OCR sees a new candidate, before
                        # its stability timer expires. Late previous results
                        # cannot displace a newly observed subtitle.
                        pending_revision = self._revision(mode,generation)
                        dispatcher.discard_pending()
                        if self.current(mode,generation):
                            self._publish(JobResult(mode,generation,(),event_id=pending_revision),notify_result=False)
                        if not text:
                            last_sent = None
                            self._publish(JobResult(mode,generation,(),event_id=pending_revision))
                    elif mode==Mode.DIALOG:
                        pending_confirmed = True
                elif mode==Mode.DIALOG and pending_text and (fingerprint==last_signature or (foreground is not None and foreground==gate.ink)):
                    pending_confirmed = True
                if mode == Mode.DIALOG and pending_text and (pending_text,pending_quality) != last_sent and (pending_confirmed or self.settings.stable_ms==0) and (time.perf_counter()-since)*1000 >= self.settings.stable_ms:
                    stages = pending_stages+(('stability_wait_ms',(time.perf_counter()-pending_ocr_end)*1000),)
                    dispatcher.offer(LiveEvent(pending_revision,tuple(pending_lines),pending_started,pending_ocr_ms,
                                               stages,offered=time.perf_counter()))
                    last_sent = (pending_text,pending_quality)
                self._status(mode.value,'持續監測中 · 等待新文字',generation)
                interval=(self.settings.chat_scan_ms if mode==Mode.CHAT else self.settings.scan_ms)/1000
                due=started+interval
                if mode==Mode.DIALOG and pending_text and (pending_text,pending_quality)!=last_sent:
                    due=min(due,since+self.settings.stable_ms/1000)
                # Sleep to a deadline, not for an additional full interval
                # after OCR. The next actual capture confirms stability.
                token.event.wait(max(0,due-time.perf_counter()))
        except Cancelled:
            pass
        except Exception as error:
            if self.current(mode,generation):
                self.failed.emit(mode.value,str(error),generation)
        finally:
            token.cancel()
            if chat_cache is not None:chat_cache.clear()
            dispatcher.close()
            with self.lock:self.live.pop((mode,generation),None)
            self.finished.emit(mode.value,generation)

    def _monitor_dialog(self, mode, generation, token, region):
        dispatcher=LiveDispatcher(self,mode,generation,token)
        stream=DialogueCapture(lambda:self._capture(region,token),signature,bright_signature,self.settings,token,self.metrics,mode,
                               lambda message:self._status(mode.value,message,generation))
        with self.lock:
            self.live[(mode,generation)]=dispatcher
            self.capture_streams[(mode,generation)]=stream
        from .subtitle_layout import SubtitleLayout
        layout=SubtitleLayout() if self.settings.reuse_dialogue_lines else None
        pending=None
        last_sent=None
        last_text=None
        seen_seq=0
        try:
            if region.width*region.height>self.image_pixel_limit:
                self.metrics.add('image_rejected_size')
                raise ValueError('框選超過 838 萬像素，請縮小範圍；辨識解析度不會自動降低。')
            stream.start()
            while not token.cancelled():
                candidate=stream.take(after_seq=seen_seq)
                seen_seq=stream.sequence()
                if candidate is not None:
                    sample=candidate.sample
                    with self._image(region,token) as image_wait:
                        ocr_started=time.perf_counter()
                        lines=self.ocr.recognize(candidate.image,token,layout=layout,layout_key=sample.key) if layout is not None else self.ocr.recognize(candidate.image,token)
                        ocr_end=time.perf_counter()
                        ocr_ms=(ocr_end-ocr_started)*1000
                        if layout is not None:self.metrics.add('ocr_'+layout.last_path,mode)
                        self.metrics.add('ocr',mode,ocr_ms=ocr_ms,
                                         ocr_queue_wait_ms=(ocr_started-sample.captured_at)*1000-sample.capture_ms-sample.filter_ms,
                                         frame_seq=sample.seq,capture_epoch=sample.epoch)
                        if stream.current(sample):self._capture_evidence(mode,generation,token,candidate.image,lines)
                    text='\n'.join(line.text for line in lines)
                    quality=min((line.confidence for line in lines),default=0)>=self.settings.ocr_review_threshold
                    stream.observed(candidate,text,quality)
                    del candidate
                    if not stream.current(sample):
                        self.metrics.add('ocr_result_superseded',mode)
                        pending=None
                        continue
                    identity=(dialogue_text_key(text),quality,sample.epoch)
                    if identity!=last_text:
                        revision=self._revision(mode,generation)
                        dispatcher.discard_pending()
                        if not text:
                            last_sent=None
                            self._publish(JobResult(mode,generation,(),event_id=revision,capture_epoch=sample.epoch))
                        last_text=identity
                    else:revision=self.revisions[mode]
                    stages=(('capture_ms',sample.capture_ms),('change_detection_ms',sample.filter_ms),
                            ('image_queue_wait_ms',image_wait),('ocr_queue_wait_ms',max(0,(ocr_started-sample.captured_at)*1000-sample.capture_ms-sample.filter_ms)),
                            ('ocr_ms',ocr_ms),('capture_observed_at',sample.captured_at),('ocr_started_at',ocr_started),
                            ('ocr_completed_at',ocr_end),('frame_seq',sample.seq),('capture_epoch',sample.epoch))
                    pending=(sample,identity,revision,tuple(lines),ocr_ms,ocr_end,stages)
                    if text and identity!=last_sent and self.settings.stable_ms>0:
                        stream.request_sample(max(ocr_end,sample.captured_at+self.settings.stable_ms/1000))
                if pending is not None:
                    sample,identity,revision,lines,ocr_ms,ocr_end,stages=pending
                    if not stream.current(sample):pending=None;continue
                    deadline=max(ocr_end,sample.captured_at+self.settings.stable_ms/1000)
                    confirmed=stream.confirmation(sample,deadline)
                    if identity[0] and identity!=last_sent and (self.settings.stable_ms==0 or confirmed is not None):
                        timing=stages+(('stability_wait_ms',max(0,(time.perf_counter()-ocr_end)*1000)),)
                        if confirmed is not None:timing+=(('confirmation_captured_at',confirmed.captured_at),)
                        dispatcher.offer(LiveEvent(revision,lines,sample.captured_at,ocr_ms,timing,
                                                   offered=time.perf_counter(),capture_epoch=sample.epoch))
                        last_sent=identity
                        pending=None
                self._status(mode.value,'持續監測中 · 等待新文字',generation)
        except Cancelled:
            pass
        except Exception as error:
            if self.current(mode,generation):self.failed.emit(mode.value,str(error),generation)
        finally:
            token.cancel()
            if stream.thread.ident is not None:stream.close()
            dispatcher.close()
            with self.lock:
                self.live.pop((mode,generation),None)
                self.capture_streams.pop((mode,generation),None)
            self.finished.emit(mode.value,generation)

    def close(self):
        self.closed = True
        self.cancel_preparation(release_model=False)
        for mode in Mode:
            self.cancel(mode)
        self.engine.close()
        self.executor.shutdown(wait=False,cancel_futures=True)
        with self.lock:
            self.latest_snapshot = None
            self.ui_results.clear()

    def join(self):
        self.executor.shutdown(wait=True,cancel_futures=True)
        self.engine.join()
