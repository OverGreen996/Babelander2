"""Small CPU-only comparison on saved identical subtitle frames."""
from bootstrap import prepare
prepare()
from pathlib import Path
import ctypes
from ctypes import wintypes
import gc
import json
import statistics
import time
import cv2
from rapidocr import RapidOCR

ROOT=Path(__file__).resolve().parent
images=[cv2.imread(str(ROOT/f'test-results/moving-background-100/moving_noise-case-{n}.png')) for n in (1,50,100)]
assert all(im is not None for im in images)
K=ctypes.windll.kernel32
K.GetCurrentProcess.restype=wintypes.HANDLE
K.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
handle=K.GetCurrentProcess()
def cpu():
    stamps=[wintypes.FILETIME() for _ in range(4)]
    assert K.GetProcessTimes(handle,*[ctypes.byref(t) for t in stamps])
    return sum((t.dwHighDateTime<<32)+t.dwLowDateTime for t in stamps[2:])/10000000
rows=[]
for threads in (2,3,4):
    ocr=RapidOCR(params={'Global.log_level':'error','Global.use_cls':False,'Global.text_score':.35,
        'Det.limit_type':'max','EngineConfig.onnxruntime.use_cuda':False,'EngineConfig.onnxruntime.use_dml':False,
        'EngineConfig.onnxruntime.intra_op_num_threads':threads,'EngineConfig.onnxruntime.inter_op_num_threads':1,
        'EngineConfig.onnxruntime.enable_cpu_mem_arena':False})
    for im in images:ocr(im)
    samples=[];before=cpu()
    for repeat in range(3):
        for index,im in enumerate(images):
            start=time.perf_counter();output=ocr(im)
            samples.append({'case':(1,50,100)[index],'repeat':repeat,'ms':(time.perf_counter()-start)*1000,
                            'text':' '.join(output.txts or [])})
    rows.append({'threads':threads,'cpu_seconds':cpu()-before,'samples':samples,
                 'mean_ms':statistics.mean(r['ms'] for r in samples),
                 'by_case':{str(n):statistics.mean(r['ms'] for r in samples if r['case']==n) for n in (1,50,100)}})
    del ocr;gc.collect()
report={'scope':'CPU-only, three identical saved frames, three warm repetitions each. No game CPU contention, no VRAM or RAM assertion.',
        'rows':rows,'outputs_identical':len({tuple(r['text'] for r in row['samples']) for row in rows})==1}
(ROOT/'test-results/ocr-threads-a5.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({**report,'rows':[{k:v for k,v in row.items() if k!='samples'} for row in rows]},ensure_ascii=False))
