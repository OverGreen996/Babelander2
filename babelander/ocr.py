"""One lazy CPU OCR engine, deterministic reading order and confidence metadata."""
import hashlib
import threading
import numpy as np

from .types import OCRLine


class OCR:
    def __init__(self, settings=None):
        self.lock = threading.Lock()
        self.engine = None
        self.settings = settings
        self.engine_threads = None
        self.engine_scope = None

    def recognize(self, image, token, layout=None, layout_key=None, chat_cache=None):
        token.check()
        with self.lock:
            token.check()
            threads=self.settings().ocr_threads if self.settings is not None else 2
            if self.engine is None or self.engine_threads!=threads:
                from rapidocr import RapidOCR
                class SessionOCR(RapidOCR):
                    chat_context = None

                    def detect_and_crop(engine, image, record):
                        crops,result = super().detect_and_crop(image,record)
                        if engine.chat_context is not None and not record.get('padding_1',{}).get('top',0):
                            engine.chat_context[0].prepare_regions(image,result.boxes)
                        return crops,result

                    def recognize_txt(engine, images):
                        context = engine.chat_context
                        if context is None:
                            return super().recognize_txt(images)
                        cache, current_token, scope = context
                        def padded(images, width_ratio):
                            from .ocr_cpu import recognize_padded
                            return recognize_padded(engine.text_rec,super(SessionOCR,engine).recognize_txt,
                                                    images,width_ratio)
                        return cache.recognize(images, super().recognize_txt, engine.text_rec,
                                               current_token, scope, engine.return_word_box, padded=padded)
                self.engine=None
                self.engine = SessionOCR(params={'Global.log_level':'error','Global.use_cls':False,'Global.text_score':.35,
                                               # Avoid upscaling a narrow subtitle's shortest side to 736px.
                                               'Det.limit_type':'max',
                                               'EngineConfig.onnxruntime.use_cuda':False,
                                               'EngineConfig.onnxruntime.use_dml':False,
                                               'EngineConfig.onnxruntime.intra_op_num_threads':threads,
                                               'EngineConfig.onnxruntime.inter_op_num_threads':1,
                                               'EngineConfig.onnxruntime.enable_cpu_mem_arena':False})
                from .ocr_cpu import install_detector_preprocess
                install_detector_preprocess(self.engine.text_det)
                self.engine_threads=threads
                self.engine_scope=object()
            full_reason=None
            if layout is not None:
                boxes=layout.propose(image,key=layout_key)
                if boxes is not None:
                    crops=[image[y0:y1,x0:x1] for x0,y0,x1,y1 in boxes]
                    output=self.engine.recognize_txt(crops)
                    token.check()
                    if (output.txts is not None and output.scores is not None and
                        len(output.txts)==len(boxes)==len(output.scores) and
                        all(text.strip() and np.isfinite(score) and score>=.90 for text,score in zip(output.txts,output.scores))):
                        layout.accepted(key=layout_key)
                        return [OCRLine(text.strip(),((x0,y0),(x1,y0),(x1,y1),(x0,y1)),float(score))
                                for text,score,(x0,y0,x1,y1) in zip(output.txts,output.scores,boxes)]
                    layout.last_reason='recognition_low_confidence'
                full_reason=layout.last_reason
            # Under the existing engine lock, with no private session retained
            # by the shared engine after success, failure or cancellation.
            self.engine.chat_context = (chat_cache,token,self.engine_scope) if chat_cache is not None else None
            if chat_cache is not None:chat_cache.last = {}
            try:
                output = self.engine(image)
            finally:
                if chat_cache is not None:chat_cache.release_frame()
                self.engine.chat_context = None
        token.check()
        if not output.txts:
            if layout is not None:layout.reset('full_detection_empty')
            return []
        lines = [OCRLine(text.strip(),tuple(tuple(float(v) for v in point) for point in box),float(score))
                 for text,box,score in zip(output.txts,output.boxes,output.scores) if text.strip()]
        lines=sorted(lines,key=lambda line:(round(min(p[1] for p in line.box)/12),min(p[0] for p in line.box)))
        if layout is not None:
            layout.last_path='full'
            layout.learn(image,lines,key=layout_key)
            layout.last_reason=full_reason
        return lines

    def recover_equipment(self, image, lines, token, on_retry=None, on_reserved=None):
        """Two bounded CPU recognition batches; no recapture or new engine."""
        from .equipment_recovery import proposals,crops,accept
        import cv2
        token.check()
        candidates=proposals(image,lines)
        token.check()
        if not candidates:return lines
        patches=crops(image,candidates)
        with self.lock:
            token.check()
            if self.engine is None:raise RuntimeError('裝備補辨識需先完成整張 OCR。')
            first=self.engine.recognize_txt(patches)
            token.check()
            enlarged=[cv2.resize(patch,None,fx=2,fy=2,interpolation=cv2.INTER_CUBIC) for patch in patches]
            second=self.engine.recognize_txt(enlarged)
            token.check()
        recovered,accepted=accept(lines,candidates,first,second)
        if on_reserved:
            from .layout import bounds
            on_reserved(tuple(candidate.box for candidate in candidates if candidate.replace_index is None
                              and not any(bounds(line)==candidate.box and line.confidence>=.98 for line in recovered)))
        if on_retry:on_retry(len(candidates),accepted)
        return recovered


def capture(region):
    from .capture import capture as native_capture
    return native_capture(region)


def signature(image):
    # Downsample and quantize: tiny animation/noise changes need not trigger OCR.
    gray = image[::3,::3].mean(axis=2).astype(np.uint8)//16
    return hashlib.sha256(gray.tobytes()).digest()
