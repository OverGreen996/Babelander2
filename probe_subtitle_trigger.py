"""Offline fixed-glyph/moving-shape stress test; no OCR/model/desktop capture."""
import json,time,statistics
from pathlib import Path
import cv2
from probe_replay_threads import render,text_parts,holdouts,ROOT
from background_corpus_100 import CORPUS
from babelander.subtitle_trigger import dim_signature,StableDimSignature

durations=[];rows=[]
for row in CORPUS:
    gate=StableDimSignature();commits=0;last=None
    for step in range(16):
        image=render(text_parts(row['text']),step)
        started=time.perf_counter();signature=dim_signature(image)
        durations.append((time.perf_counter()-started)*1000)
        current=gate.observe(signature,step*.1)
        if step and current!=last:commits+=1
        last=current
    rows.append({'cue_id':row['id'],'structure_changes':commits})
tests=holdouts();mixed=[]
for index,name in ((0,'inline'),(3,'new_line')):
    gate=StableDimSignature();gate.observe(dim_signature(render(tests[index]['parts'],0)),0)
    changed_at=None
    for step in range(1,17):
        result=gate.observe(dim_signature(render(tests[index+1]['parts'],step)),step*.1)
        if result is not None and changed_at is None:changed_at=step*.1
    mixed.append({'case':name,'observed_change_ms':None if changed_at is None else changed_at*1000})
gate=StableDimSignature();gate.observe(None,0);moving=0;last=None
for step in range(100):
    frame=render(text_parts('Open the quiet gate.'),step%16)
    cv2.putText(frame,'#####',(700+(step%40)*3,150),cv2.FONT_HERSHEY_SIMPLEX,1.4,(155,155,155),3)
    result=gate.observe(dim_signature(frame),(step+1)*.1)
    if result!=last:moving+=1
    last=result
report={'scope':'Offline feature extraction only. Fixed authored glyphs over 16 changing backgrounds; moving glyph-shaped particles. Not OCR recall, model latency or real-game compatibility.',
    'white_cues':100,'frames':1600,'rows':rows,'white_cue_false_structure_changes':sum(r['structure_changes'] for r in rows),
    'mixed_changes':mixed,'moving_glyph_shaped_particle_commits':moving,
    'extraction_mean_ms':round(statistics.mean(durations),3),'extraction_p95_ms':round(sorted(durations)[int(len(durations)*.95)],3),
    'stationary_nontext_shapes_can_trigger_ocr':True,'unsupported_low_contrast_uses_existing_watchdog':True}
out=ROOT/'test-results/subtitle-trigger-stress-a13.json';out.write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
