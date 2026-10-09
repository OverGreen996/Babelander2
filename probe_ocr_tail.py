"""ABBA isolated process OCR allocation comparison; no app edits or GPU."""
import argparse,os,subprocess,sys,json,time,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'test-results/ocr-tail-a20';OUT.mkdir(parents=True,exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--child',choices=('baseline','arena'));parser.add_argument('--round',type=int,default=0);args=parser.parse_args()
if args.child:
    from bootstrap import prepare
    prepare()
    import cv2,gc,numpy as np
    from rapidocr import RapidOCR
    from replay_resources import process
    files=[ROOT/'test-results/supertest-a20-motion'/f'moving_noise-case-{n}.png' for n in (1,50,100)]
    files+=[ROOT/'test-results/supertest-a20/chat'/f'chat-{n:03d}-original.png' for n in (20,40,60,80,100)]
    images=[cv2.imread(str(p)) for p in files];assert all(im is not None for im in images)
    params={'Global.log_level':'error','Global.use_cls':False,'Global.text_score':.35,'Det.limit_type':'max','EngineConfig.onnxruntime.use_cuda':False,'EngineConfig.onnxruntime.use_dml':False,'EngineConfig.onnxruntime.intra_op_num_threads':2,'EngineConfig.onnxruntime.inter_op_num_threads':1,'EngineConfig.onnxruntime.enable_cpu_mem_arena':args.child=='arena'}
    engine=RapidOCR(params=params)
    for image in images:engine(image)
    before=process();samples=[];mem=[];start=time.process_time()
    for repeat in range(3):
        for index in ((range(len(images))) if repeat%2==0 else reversed(range(len(images)))):
            at=time.perf_counter();output=engine(images[index]);ms=(time.perf_counter()-at)*1000
            samples.append({'file':files[index].name,'repeat':repeat,'ms':round(ms,3),'text':output.txts or [],'scores':[round(float(x),6) for x in (output.scores if output.scores is not None else [])]});mem.append(process())
    report={'config':args.child,'round':args.round,'ocr_threads':2,'cpu_core_seconds':time.process_time()-start,'latency':{'n':len(samples),'mean_ms':round(float(np.mean([s['ms'] for s in samples])),2),'p95_ms':round(float(np.percentile([s['ms'] for s in samples],95)),2),'max_ms':max(s['ms'] for s in samples)},'private_max_mib':max(s['private_mib'] for s in mem),'working_max_mib':max(s['working_mib'] for s in mem),'samples':samples,'fixture_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (OUT/f'{args.round}-{args.child}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in report.items() if k not in ('samples','fixture_sha256')}),flush=True)
else:
    frozen={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}
    env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
    for round,config in enumerate(('baseline','arena','arena','baseline')):
        print('START '+str(round)+' '+config,flush=True)
        subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child',config,'--round',str(round)],cwd=ROOT,env=env,check=True,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    rows=[json.loads((OUT/f'{i}-{c}.json').read_text(encoding='utf8')) for i,c in enumerate(('baseline','arena','arena','baseline'))]
    patterns={c:{s['file']:s['text'] for s in rows[i]['samples']} for i,c in ((0,'baseline'),(1,'arena'))}
    result={'scope':'Eight saved identical frames, 3 warm repetitions, 2 threads, isolated ABBA process order. No game FPS claim, no app/setting edits, no GPU/model. Not full pipeline latency.','runs':rows,'all_text_outputs_equal':all({s['file']:s['text'] for s in row['samples']}==patterns['baseline'] for row in rows),'application_sha256':frozen,'source_unchanged':frozen=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}}
    (OUT/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in result.items() if k not in ('runs','application_sha256')}),flush=True)
