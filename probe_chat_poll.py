"""Independent fixed-cadence chat playback; isolated 800/100/100/800 A/B.

One preloaded model per process. Switching fixtures never unloads the model.
No game/window capture, hotkeys, foreground control or saved setting changes.
"""
import argparse,os,json,subprocess,sys,time,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--child',action='store_true');parser.add_argument('--scan-ms',type=int,default=100)
parser.add_argument('--ocr-threads',type=int,choices=(1,2,3,4),default=2)
parser.add_argument('--round',type=int,default=0);parser.add_argument('--period-ms',type=int,default=900)
parser.add_argument('--out',default='chat-poll-fixed-a22')
parser.add_argument('--experimental-gate',action='store_true')
parser.add_argument('--legacy-chat',action='store_true')
parser.add_argument('--baseline-ref',help='Immutable git ref for the original OCR and recognition cache (child only).')
parser.add_argument('--animated-chat',action='store_true');args=parser.parse_args()
if not args.child and (args.experimental_gate or args.animated_chat or args.legacy_chat or args.baseline_ref):
    parser.error('Experimental animation flags require --child; use probe_chat_gate_suite.py for candidate/control comparison.')
out=ROOT/'test-results'/args.out;out.mkdir(parents=True,exist_ok=True)

def source():return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')

if not args.child:
    frozen=source();runs=[];env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
    for i,scan in enumerate((800,100,100,800)):
        print(f'START round={i} chat_scan_ms={scan}',flush=True)
        subprocess.run([sys.executable,__file__,'--child','--scan-ms',str(scan),'--round',str(i),
                        '--period-ms',str(args.period_ms),'--ocr-threads',str(args.ocr_threads),'--out',args.out],cwd=ROOT,env=env,
                       timeout=240,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
        runs.append(json.loads((out/f'{i}-{scan}.json').read_text(encoding='utf8')))
    import numpy as np
    grouped={}
    for scan in (800,100):
        group=[r for r in runs if r['chat_scan_ms']==scan]
        values=[v['shown_to_qt_ms'] for r in group for v in r['results']]
        grouped[str(scan)]={'n':len(values),'mean_ms':float(np.mean(values)),'p50_ms':float(np.median(values)),
                            'p95_ms':float(np.percentile(values,95)),'max_ms':max(values),
                            'within_700ms':sum(v<=700 for v in values),
                            'cpu_core_seconds':sum(r['cpu_core_seconds'] for r in group),
                            'captures':sum(r['captures'] for r in group),'ocr_calls':sum(len(r['ocr']) for r in group),
                            'private_max_mib':max(r['private_max_mib'] for r in group),
                            'working_max_mib':max(r['working_max_mib'] for r in group)}
    sequence=[[v['source'] for v in r['results']] for r in runs]
    report={'scope':f'100 messages at independent {args.period_ms}ms cadence, five styles, pre-rendered images, real CPU OCR/CUDA/Qt, four isolated ABBA processes. Warm model retained across fixture changes. No game FPS claim.',
            'runs':runs,'summary':grouped,'all_new_sources_equal':all(v==sequence[0] for v in sequence),
            'frame_hashes_equal':all(r['frame_hashes']==runs[0]['frame_hashes'] for r in runs),
            'source_sha256':frozen,'source_unchanged':source()==frozen}
    report['functional_passed']=all(r['passed'] for r in runs) and report['all_new_sources_equal'] and report['frame_hashes_equal'] and report['source_unchanged']
    save(out/'report.json',report)
    print(json.dumps({'functional_passed':report['functional_passed'],'summary':grouped}),flush=True)
    raise SystemExit(not report['functional_passed'])

os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import tempfile,threading,re
from collections import Counter
from dataclasses import asdict
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from babelander import __version__
from babelander.settings import Settings
from babelander.types import Cancellation,Mode,Region
from babelander.ocr import signature as real_signature
from babelander.chat import filter_decorations
from contextlib import nullcontext,ExitStack
from babelander.controller import Controller
from babelander.engine import Engine
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.window import MainWindow
baseline_sources={}
if args.baseline_ref:
    import types
    baseline_commit=subprocess.check_output(['git','rev-parse',args.baseline_ref],cwd=ROOT,text=True).strip()
    for name in ('chat_ocr','ocr'):
        code=subprocess.check_output(['git','show',baseline_commit+':babelander/'+name+'.py'],cwd=ROOT).decode('utf8')
        module=types.ModuleType('babelander.'+name);module.__package__='babelander'
        exec(compile(code,'<baseline '+baseline_commit+' '+name+'>','exec'),module.__dict__)
        sys.modules['babelander.'+name]=module
        baseline_sources[name]=hashlib.sha256(code.encode()).hexdigest()
    import babelander.controller as controller_module
    controller_module.OCR=sys.modules['babelander.ocr'].OCR
from chat_fixtures import chat_frame
from replay_resources import process
app=QApplication(['Offscreen fixed-cadence chat'])
app.setStyle('Fusion');app.setStyleSheet((ROOT/'babelander/theme.qss').read_text(encoding='utf8'))
for font in ('arial.ttf','msjh.ttc'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
frames=[chat_frame(list(range(max(i//20*20,i-3),i+1)))[1] for i in range(100)]
animated=None;adapter=None
if args.animated_chat:
    from chat_gate_fixtures import variants
    animated=[variants(frame,i) for i,frame in enumerate(frames)]
if args.experimental_gate:
    from chat_gate_experiment import SignatureAdapter
    adapter=SignatureAdapter(real_signature)
report={'version':__version__,'chat_scan_ms':args.scan_ms,'ocr_threads':args.ocr_threads,'round':args.round,'period_ms':args.period_ms,
        'baseline_ref':args.baseline_ref,'baseline_sources':baseline_sources,
        'source_sha256':source(),'results':[],'ocr':[],'errors':[],'changes':[],
        'frame_hashes':[hashlib.sha256(f.tobytes()).hexdigest() for f in frames],
        'real_desktop_capture':False,'foreground_control_calls':0,'qt_platform':app.platformName()}
if animated is not None:report['animation_hashes']=[[hashlib.sha256(f.tobytes()).hexdigest() for f in phase] for phase in animated]
report['experimental_gate']=args.experimental_gate
if adapter is not None:report['candidate_sha256']=hashlib.sha256((ROOT/'chat_gate_experiment.py').read_bytes()).hexdigest()
legacy_context=ExitStack()
if args.legacy_chat:
    import zipfile,types
    archive=ROOT/'dist/Babelander2-2.0.0a22-source.zip'
    with zipfile.ZipFile(archive) as backup:code=backup.read('Babelander2/babelander/chat.py').decode('utf8')
    old=types.ModuleType('babelander._legacy_chat');old.__package__='babelander'
    exec(compile(code,'<archived a22 chat>','exec'),old.__dict__)
    def legacy_lines(previous,current):
        a,b=[old.message_key(t) for t in previous],[old.message_key(t) for t in current]
        if a==b:return []
        for size in range(min(len(a),len(b)),0,-1):
            if a[-size:]==b[:size] or old.anchored_overlap(a[-size:],b[:size]):return current[size:]
        return list(current)
    legacy_context=ExitStack()
    legacy_context.enter_context(patch('babelander.controller.new_chat_lines',side_effect=legacy_lines))
    legacy_context.enter_context(patch('babelander.controller.filter_decorations',side_effect=lambda lines:(lines,0)))
    report['legacy_chat_sha256']=hashlib.sha256(code.encode('utf8')).hexdigest()
report['legacy_chat']=args.legacy_chat
state={};shown={};local=threading.local();caches=[];memory=[]
def until(predicate,timeout=10):
    deadline=time.perf_counter()+timeout
    while not predicate() and time.perf_counter()<deadline:app.processEvents();time.sleep(.002)
    app.processEvents();return bool(predicate())
with tempfile.TemporaryDirectory(prefix='Babelander-poll-') as directory:
    root=Path(directory);assets=ROOT.parent/'recovery/test-assets'
    settings=Settings(hotkeys={},chat_scan_ms=args.scan_ms,ocr_threads=args.ocr_threads,
        model_path=str(next((assets/'models').glob('*.gguf'))),server_path=str(assets/'runtime/llama-server.exe'))
    store=Store(root);vault=KeyVault(root);engine=Engine(settings,store,vault,root)
    controller=Controller(engine,store,settings);window=MainWindow(controller,store,settings,vault,root)
    real_ocr=controller.ocr.recognize;backend=None
    real_status=controller._status
    def status(*args):
        real_status(*args)
        if len(args)>1 and args[1]=='持續監測中 · 等待新文字' and getattr(local,'frozen',False):
            state['frozen_cycles']=state.get('frozen_cycles',0)+1
    controller._status=status
    def capture(region):
        index,image=state['current'];local.index=index
        local.frozen=state.get('frozen',False)
        state['captures']=state.get('captures',0)+1
        if animated is not None:
            phase=0 if local.frozen else int((time.perf_counter()-shown[index])*10)%2
            image=animated[index][phase]
        return image.copy()
    def recognize(image,token,*a,**kw):
        index=local.index;at=time.perf_counter();result=real_ocr(image,token,*a,**kw)
        if adapter is not None:adapter.observed(image,result)
        cache=kw.get('chat_cache')
        if cache is not None and not any(cache is old for old in caches):caches.append(cache)
        report['ocr'].append({'index':index,'ms':(time.perf_counter()-at)*1000,'reuse':dict(cache.last) if cache is not None else {},
                             'decorations':filter_decorations(result)[1],'raw':[asdict(l) for l in result]})
        return result
    def receive(mode):
        result=controller.take_result(mode)
        if result is None:return
        window.receive(result);now=time.perf_counter()
        for translation in result.translations:
            match=re.search(r'P([0O1]\d{2})',translation.source)
            index=int(match[1].replace('O','0'))-1 if match else None
            report['results'].append({**asdict(translation),'index':index,'observed_ms':result.total_ms,
                'shown_to_qt_ms':(now-shown[index])*1000 if index in shown else None,'stages':dict(result.stages)})
    controller.delivery.disconnect(window.receive);controller.delivery.connect(receive)
    controller.failed.connect(lambda *error:report['errors'].append(list(error)))
    try:
        engine.prepare_local(Cancellation()).result(timeout=65);backend=engine.local.process
        engine.request('We should leave the camp before sunset.',Mode.CHAT,Cancellation());engine.volatile.clear()
        real_ocr(frames[0],Cancellation());controller.ocr.recognize=recognize
        cpu_start=time.process_time();at_start=time.perf_counter()
        with patch('babelander.controller.capture',side_effect=capture), (patch('babelander.controller.signature',side_effect=adapter) if adapter is not None else nullcontext()):
            for block in range(5):
                if block:
                    window.stop(Mode.CHAT,release_model=False)
                    assert until(lambda:not controller.live),'old monitor did not stop'
                    if adapter is not None:adapter.gate.clear();adapter.output=None
                base=time.perf_counter()
                state.update(frozen=False,frozen_cycles=0)
                for index in range(block*20,(block+1)*20):
                    deadline=base+(index-block*20)*args.period_ms/1000
                    assert until(lambda:time.perf_counter()>=deadline,3)
                    now=time.perf_counter();shown[index]=now;state['current']=(index,frames[index])
                    report['changes'].append({'index':index,'producer_late_ms':(now-deadline)*1000})
                    if index%20==0:
                        window.regions[Mode.CHAT]=Region(0,0,frames[index].shape[1],frames[index].shape[0])
                        window.toggle_monitor(Mode.CHAT)
                    memory.append(process())
                # Observe the full last exposure; symbol noise or failures
                # cannot masquerade as the required number of real messages.
                assert until(lambda:time.perf_counter()>=shown[index]+args.period_ms/1000,3)
                state['frozen']=True
                def drained():
                    snapshots=[d.snapshot() for d in controller.live.values()]
                    return (state.get('frozen_cycles',0)>0 and bool(snapshots)
                            and all(not s['pending'] and not s['in_flight'] for s in snapshots)
                            and not controller.ui_pending)
                assert until(drained,20),'actual OCR/translation/UI work did not drain'
                report.setdefault('drains',[]).append({'block':block,'frozen_cycles':state['frozen_cycles'],
                    'received':len(report['results']),'dispatcher_empty':True,'ui_empty':True})
                print(json.dumps({'round':args.round,'scan_ms':args.scan_ms,'delivered':len(report['results'])}),flush=True)
            window.stop(Mode.CHAT,release_model=False);assert until(lambda:not controller.live)
        report['metrics']=controller.metrics.snapshot()
        report['cpu_core_seconds']=time.process_time()-cpu_start
        report['duration_seconds']=time.perf_counter()-at_start
        report['captures']=state['captures']
        if adapter is not None:report['gate_counts']=adapter.counts
        report['private_max_mib']=max(m['private_mib'] for m in memory)
        report['working_max_mib']=max(m['working_mib'] for m in memory)
        report['sqlite_rows']={table:store.db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('cache','history','usage')}
        report['model_stayed_warm']=engine.local.process is backend and all(r['backend_state']!='cold' for r in report['results'])
        report['producer_late_max_ms']=max(v['producer_late_ms'] for v in report['changes'])
    except Exception as error:report['fatal_error']={'type':type(error).__name__,'message':str(error)}
    finally:
        window.close();controller.close();controller.join();store.close();app.processEvents();legacy_context.close()
        report['owned_model_stopped']=backend is None or backend.poll() is not None
        report['workers_stopped']=all(not t.is_alive() for queue in engine.queues.values() for t in queue.threads)
        report['sessions_cleared']=all(not c.entries and not c.regions and c.current_regions is None and c.scope is None for c in caches)
        report['shared_ocr_context_cleared']=controller.ocr.engine is None or controller.ocr.engine.chat_context is None
        if adapter is not None:adapter.gate.clear();report['gate_cleared']=adapter.gate.reference is None and adapter.gate.pending is None
matched=Counter(r['index'] for r in report['results'])
report['missing']=[i for i in range(100) if not matched[i]]
report['duplicates']={i:n for i,n in matched.items() if n>1}
report['source_unchanged']=report['source_sha256']==source()
report['passed']=(not report.get('fatal_error') and not report['errors'] and len(report['results'])==100
    and not report['missing'] and not report['duplicates'] and matched.get(None,0)==0
    and all(r['target'] and not r['warning'] for r in report['results'])
    and report['sqlite_rows']=={'cache':0,'history':0,'usage':0} and report['model_stayed_warm']
    and report['owned_model_stopped'] and report['workers_stopped'] and report['sessions_cleared']
    and report['shared_ocr_context_cleared'] and report['source_unchanged'])
save(out/f'{args.round}-{args.scan_ms}.json',report)
print(json.dumps({'passed':report['passed'],'results':len(report['results']),'errors':report['errors'],'fatal_error':report.get('fatal_error')}),flush=True)
raise SystemExit(not report['passed'])
