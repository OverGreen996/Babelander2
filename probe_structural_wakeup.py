"""Exploratory secondary signature, never installed into production defaults.

This feature only considers outlined mid-luminance components; it is not OCR
or a universal text detector. Reject it if unchanged animated text jitters.
"""
import hashlib
import json
from pathlib import Path
import time
import cv2
import numpy as np


def dim_structure(image):
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    gradient=cv2.morphologyEx(gray,cv2.MORPH_GRADIENT,np.ones((3,3),np.uint8))
    candidate=((gradient>=60)&(gray>=130)&(gray<220)).astype(np.uint8)
    count,labels,components,_=cv2.connectedComponentsWithStats(candidate,8)
    boxes=[]
    for x,y,w,h,area in components[1:]:
        if not (6<=w<=600 and 9<=h<=70 and area>=20):continue
        # Exclude outer shadows/antialiasing that surround known white letters.
        if np.any(gray[y:y+h,x:x+w]>=220):continue
        boxes.append((int(x)//3,int(y)//3,int(w)//3,int(h)//3,int(area)//16))
    boxes.sort()
    return hashlib.sha256(repr(boxes).encode()).digest(),boxes


def run():
    # Import only when explicitly running this offscreen fixture analysis.
    from probe_replay_threads import render,text_parts,holdouts,ROOT
    from babelander.monitor import bright_signature
    from background_corpus_100 import CORPUS
    tests=holdouts();rows=[];durations=[]
    for category,i in [('mixed_inline',0),('mixed_new_line',3)]:
        base=[];changed=[];boxes=[]
        for step in range(16):
            a=render(tests[i]['parts'],step);b=render(tests[i+1]['parts'],step)
            t=time.perf_counter();sig_a,box_a=dim_structure(a);sig_b,box_b=dim_structure(b)
            durations.append((time.perf_counter()-t)*500)
            base.append(sig_a);changed.append(sig_b);boxes.append({'base':box_a,'changed':box_b})
        rows.append({'category':category,'bright_equal':all(bright_signature(render(tests[i]['parts'],s))==bright_signature(render(tests[i+1]['parts'],s)) for s in range(16)),
                     'changed_detected_frames':sum(a!=b for a,b in zip(base,changed)),
                     'base_signature_variants':len(set(base)),'changed_signature_variants':len(set(changed)),
                     'boxes':boxes})
    invariance=[]
    # Same 100 real glyph layouts; background alone changes 16 times.
    for row in CORPUS:
        signatures=[]
        for step in range(16):
            frame=render(text_parts(row['text']),step)
            at=time.perf_counter();sig,boxes=dim_structure(frame)
            durations.append((time.perf_counter()-at)*1000);signatures.append(sig)
        invariance.append({'cue_id':row['id'],'variants':len(set(signatures)),
                           'false_changes':sum(a!=b for a,b in zip(signatures,signatures[1:]))})
    blank=[]
    for step in range(16):blank.append(dim_structure(render([],step))[0])
    # Negative cases add moving high-contrast shapes, separate from dark noise.
    particles=[]
    for step in range(16):
        frame=render(text_parts('Open the quiet gate.'),step)
        cv2.putText(frame,'##',(700+step*3,150),cv2.FONT_HERSHEY_SIMPLEX,1.4,(155,155,155),3)
        particles.append(dim_structure(frame)[0])
    result={'scope':'Offline signature only; no OCR/Qwen, no production change. CPU timing includes feature extraction, not scene rendering. Not recall or latency acceptance.',
            'mixed':rows,'same_text_invariance':invariance,'blank_signature_variants':len(set(blank)),
            'moving_mid_luminance_shape_variants':len(set(particles)),
            'timing_ms_mean':sum(durations)/len(durations),
            'accepted_for_runtime_trial':all(r['changed_detected_frames']==16 and r['base_signature_variants']==1 and r['changed_signature_variants']==1 for r in rows)
                and all(r['variants']==1 for r in invariance) and len(set(blank))==1 and len(set(particles))==1}
    out=ROOT/'test-results/structural-wakeup-a8.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('mixed','same_text_invariance')}),flush=True)


if __name__=='__main__':run()
