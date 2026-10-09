"""Labelled original-position replay: real OCR/model/Qt, no desktop or hotkeys."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import argparse,hashlib,json,re,tempfile,time,unicodedata,sys,subprocess,shutil
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PySide6.QtGui import QFontDatabase,QImage,QPainter
from PySide6.QtWidgets import QApplication
ROOT=Path(__file__).resolve().parent
APPROOT=Path(os.environ.get('BABELANDER_TEST_APPLICATION',str(ROOT)))
if APPROOT!=ROOT:sys.path.insert(0,str(APPROOT))
from babelander import __version__
from babelander.controller import Controller
from babelander.engine import Engine
from babelander.settings import Settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.types import Mode,Region,Cancellation
from babelander.window import MainWindow
from babelander.validation import NUMBER
from quest_fixtures import fixtures

parser=argparse.ArgumentParser();parser.add_argument('--name',default='quest-a18-discovery');parser.add_argument('--passes',type=int,default=2)
parser.add_argument('--strict',action='store_true')
parser.add_argument('--suite',choices=('palette','game_structures'),default='game_structures')
ARGS=parser.parse_args();DEST=ROOT/'test-results'/ARGS.name;DEST.mkdir(parents=True,exist_ok=True)
config=ROOT/'test-results/quest-offscreen.json'
config.parent.mkdir(exist_ok=True)
config.write_text(json.dumps({'windowFrameMargins':False,'screens':[{'name':'card-virtual','width':1920,'height':1080,'logicalDpi':96,'logicalBaseDpi':96,'dpr':1}]}),encoding='utf8')
APP=QApplication(['Quest matrix background replay','-platform','offscreen:configfile='+'test-results/quest-offscreen.json']);APP.setStyle('Fusion')
APP.setStyleSheet((ROOT/'babelander/theme.qss').read_text(encoding='utf8'))
for name in ('arial.ttf','georgia.ttf','times.ttf','consola.ttf','trebuc.ttf','segoeui.ttf','cour.ttf','msjh.ttc'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
FIXTURES=fixtures()
def normal(text):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',text)).strip().lower()
def content(text):return re.sub(r'\s+','',normal(text))
def numbers(text):return Counter(re.sub(r'\s+','',n).replace('−','-') for n in NUMBER.findall(unicodedata.normalize('NFKC',text)))
def luminance(rgb):
    channels=np.asarray(rgb,dtype=float)/255
    return float(np.dot(np.where(channels<=.04045,channels/12.92,((channels+.055)/1.055)**2.4),[.2126,.7152,.0722]))
def contrast(a,b):
    x,y=sorted((luminance(a),luminance(b)));return (y+.05)/(x+.05)
def pixels(image):
    image=image.convertToFormat(QImage.Format.Format_BGR888)
    return np.frombuffer(image.bits(),np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*3].reshape(image.height(),image.width(),3).copy()
def difference(expected,observed):return dict(expected-observed)
report={'version':__version__,'real_ocr':True,'real_cuda_model':True,'real_desktop_capture':False,'qt_platform':APP.platformName(),
        'semantic_accuracy_scored':False,'checks':'ground-truth text and numbers, required markers, full rendering, contrast, art pixels, original-position geometry',
        'warm_engines':True,'suite':ARGS.suite,'cache_policy':'cleared once after warmup; shared fields may reuse cache; repeat pass retains cache',
        'application_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (APPROOT/'babelander').glob('*.py')},'fixtures':[],'runs':[]}
for fixture in FIXTURES:
    # Validate authored fixtures before testing the application. No oracle boxes
    # are ever given to Controller/OCR; these are solely evaluation metadata.
    w,h=fixture.image.width(),fixture.image.height()
    for row in fixture.rows:
        x0,y0,x1,y1=row['bounds']
        assert 0<=x0<x1<=w and 0<=y0<y1<=h,(fixture.identifier,row)
    for i,a in enumerate(fixture.rows):
        for b in fixture.rows[i+1:]:
            x,y=a['bounds'],b['bounds']
            assert not (min(x[2],y[2])>max(x[0],y[0]) and min(x[3],y[3])-max(x[1],y[1])>2),(fixture.identifier,a,b)
    fixture.image.save(str(DEST/(fixture.identifier+'-original.png')))
    report['fixtures'].append({'id':fixture.identifier,'theme':fixture.theme,'pattern':fixture.pattern,'size':[w,h],
        'frame_sha256':hashlib.sha256(fixture.frame.tobytes()).hexdigest(),'rows':fixture.rows,'markers':fixture.markers,
        'structural_features':getattr(fixture,'structural_features',()),'art_regions':getattr(fixture,'art_regions',(fixture.art_bounds,))})

def save():
    (DEST/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')

with tempfile.TemporaryDirectory(prefix='Babelander-equipment-matrix-') as directory:
    root=Path(directory);assets=ROOT.parent/'recovery/test-assets'
    settings=Settings(hotkeys={},model_path=str(next((assets/'models').glob('*.gguf'))),server_path=str(assets/'runtime/llama-server.exe'))
    store=Store(root);vault=KeyVault(root);engine=Engine(settings,store,vault,root)
    controller=Controller(engine,store,settings);window=MainWindow(controller,store,settings,vault,root)
    current={};backend=None
    def capture(region):
        assert region==current['region']
        current['run']['capture_calls']+=1;return current['fixture'].frame.copy()
    real_ocr=controller.ocr.recognize
    real_recovery=controller.ocr.recover_equipment
    def recognize(image,token):
        current['run']['ocr_calls']+=1
        lines=real_ocr(image,token);current['run']['ocr_lines']=[asdict(line) for line in lines];return lines
    def recover(image,lines,token,on_retry=None,on_reserved=None):
        current['run']['primary_ocr_lines']=[asdict(line) for line in lines]
        def audit(proposed,accepted):
            current['run']['numeric_retry']={'candidates':proposed,'accepted':accepted,'rejected':proposed-accepted,'recognition_batches':2}
            if on_retry:on_retry(proposed,accepted)
        at=time.perf_counter()
        recovered=real_recovery(image,lines,token,audit,on_reserved)
        current['run']['numeric_recovery_ms']=(time.perf_counter()-at)*1000
        current['run']['ocr_lines']=[asdict(line) for line in recovered]
        return recovered
    def fail(*args):current['run']['error']=[str(arg) for arg in args]
    def receive(mode):
        result=controller.take_result(mode)
        if result is None:return
        run=current['run'];fixture=current['fixture'];permitted=controller.displayable(result)
        window.receive(result);widget=window.overlay(mode)
        run.update(full_qt_latency_ms=round((time.perf_counter()-current['at'])*1000,2),ocr_ms=round(result.ocr_ms,2),
            total_ms=round(result.total_ms,2),stages=dict(result.stages),displayable=permitted,
            renderable=widget.renderable,render_warning=widget.render_warning,
            geometry=[widget.x(),widget.y(),widget.width(),widget.height()],
            translations=[asdict(t) for t in result.translations],cache_hits=sum(t.cache_hit for t in result.translations))
        expected=' '.join(row['text'] for row in fixture.rows)
        raw_observed=' '.join(line['text'] for line in run['ocr_lines'])
        observed=' '.join(t.source for t in result.translations)
        target=' '.join(t.target for t in result.translations)
        # Compare words/numbers as multisets because reading order legitimately
        # differs on two-column cards. Keep strict sequence comparisons too.
        words=lambda text:Counter(re.findall(r'[a-z]+',normal(text)))
        run.update(raw_missing_source_words=difference(words(expected),words(raw_observed)),
            raw_extra_source_words=difference(words(raw_observed),words(expected)),raw_missing_source_numbers=difference(numbers(expected),numbers(raw_observed)),
            raw_extra_source_numbers=difference(numbers(raw_observed),numbers(expected)))
        run.update(ocr_content_sequence_match=content(expected)==content(observed),
            missing_source_words=difference(words(expected),words(observed)),extra_source_words=difference(words(observed),words(expected)),
            missing_source_numbers=difference(numbers(expected),numbers(observed)),extra_source_numbers=difference(numbers(observed),numbers(expected)),
            missing_target_numbers=difference(numbers(expected),numbers(target)),extra_target_numbers=difference(numbers(target),numbers(expected)))
        marker_checks={'otherwise':'否則' in target,'negative':any(term in target for term in ('不','勿','別','禁止')),
            'level_timing':bool(re.search(r'未達|未到|前|至少|才能|直到',target))}
        run['required_markers']={marker:marker_checks[marker] for marker in fixture.markers}
        run['geometry_exact']=run['geometry']==list(current['region'].__dict__.values())
        run['contrasts']=[]
        if result.equipment_layout:
            for slot in result.equipment_layout.slots:
                if slot.literal:continue
                x0,y0,x1,y1=map(int,slot.source_bounds)
                # Use backdrop pixels: original glyphs have already been erased.
                backdrop=np.frombuffer(result.equipment_layout.pixels,np.uint8).reshape(fixture.frame.shape)
                rgb=np.median(backdrop[y0:y1,x0:x1].reshape(-1,3),axis=0)[::-1]
                run['contrasts'].append(round(contrast(slot.color,rgb),2))
            run['slots']=[asdict(slot) for slot in result.equipment_layout.slots]
            run['origin_position_valid']=all(abs(slot.bounds[1]-slot.source_bounds[1])<.1 and
                0<=slot.bounds[0]-slot.source_bounds[0]<=.6*(slot.source_bounds[3]-slot.source_bounds[1])+2
                for slot in result.equipment_layout.slots)
        run['min_contrast']=min(run['contrasts']) if run['contrasts'] else None
        if widget.renderable:
            output=widget.grab().toImage();translated=pixels(output)
            run['art_region_checks']=[]
            for ax0,ay0,ax1,ay1 in getattr(fixture,'art_regions',(fixture.art_bounds,)):
                run['art_region_checks'].append(bool(np.array_equal(translated[ay0:ay1,ax0:ax1],fixture.frame[ay0:ay1,ax0:ax1])))
            run['art_unchanged']=all(run['art_region_checks'])
            run['literal_pixels_unchanged']=True;run['ocr_literal_rectangles_unchanged']=True
            for slot in result.equipment_layout.slots:
                if slot.literal:
                    x0,y0,x1,y1=map(int,slot.source_bounds)
                    run['ocr_literal_rectangles_unchanged'] &= bool(np.array_equal(translated[y0:y1,x0:x1],fixture.frame[y0:y1,x0:x1]))
                    # An oversized OCR rectangle may include blank space of the
                    # following row. Compare the authored number's complete
                    # font rectangle instead; retain the raw-box check above.
                    matches=[r for r in fixture.rows if r['group']=='literal' and r['text']==slot.literal]
                    if matches:
                        for reference in matches:
                            x0,y0,x1,y1=reference['bounds']
                            run['literal_pixels_unchanged'] &= bool(np.array_equal(translated[y0:y1,x0:x1],fixture.frame[y0:y1,x0:x1]))
                    else:run['literal_pixels_unchanged'] &= run['ocr_literal_rectangles_unchanged']
            if run['pass']==0:
                output.save(str(DEST/(fixture.identifier+'-translated.png')))
                comparison=QImage(fixture.image.width()*2,fixture.image.height(),QImage.Format.Format_RGB32)
                painter=QPainter(comparison);painter.drawImage(0,0,fixture.image);painter.drawImage(fixture.image.width(),0,output);painter.end()
                comparison.save(str(DEST/(fixture.identifier+'-comparison.png')))
        run['source_complete']=not any(run[key] for key in ('missing_source_words','extra_source_words','missing_source_numbers','extra_source_numbers'))
        run['numbers_preserved']=not run['missing_target_numbers'] and not run['extra_target_numbers']
        run['cross_panel_blocks']=[]
        run['source_color_checks']=[]
        if result.equipment_layout and ARGS.suite=='game_structures':
            for t,slot in zip(result.translations,result.equipment_layout.slots):
                x0,y0,x1,y1=slot.source_bounds
                panels={r['panel'] for r in fixture.rows if x0<=sum(r['bounds'][::2])/2<=x1 and y0<=sum(r['bounds'][1::2])/2<=y1}
                if len(panels)>1:run['cross_panel_blocks'].append({'source':t.source,'panels':sorted(panels)})
                if not slot.literal:
                    colors={tuple(r['color']) for r in fixture.rows if x0<=sum(r['bounds'][::2])/2<=x1 and y0<=sum(r['bounds'][1::2])/2<=y1}
                    error=max((max(abs(int(a)-int(b)) for a,b in zip(slot.color,color)) for color in colors),default=0)
                    run['source_color_checks'].append({'source':t.source,'actual':slot.color,'expected':list(colors),'max_channel_error':error,'passed':bool(colors) and error<=8})
        run['source_colors_preserved']=all(c['passed'] for c in run['source_color_checks']) if ARGS.suite=='game_structures' else True
        run['usable']=bool(permitted and widget.renderable and run['source_complete'] and run['numbers_preserved'] and all(run['required_markers'].values())
            and run['geometry_exact'] and run.get('origin_position_valid') and not run['cross_panel_blocks'] and run.get('art_unchanged') and run.get('literal_pixels_unchanged') and run['source_colors_preserved'])
        run['received']=True
    controller.delivery.disconnect(window.receive);controller.delivery.connect(receive)
    controller.failed.connect(fail);controller.ocr.recognize=recognize;controller.ocr.recover_equipment=recover
    try:
        real_ocr(FIXTURES[0].frame,Cancellation())
        report['warmup_warning']=engine.request('The merchant is waiting by the east gate.',Mode.DIALOG,Cancellation()).warning
        backend=engine.local.process
        startup=(root/'model-startup.log').read_text(encoding='utf8',errors='replace')
        gpu=subprocess.run([shutil.which('nvidia-smi') or 'C:/Windows/System32/nvidia-smi.exe','--query-compute-apps=pid','--format=csv,noheader'],capture_output=True,text=True,timeout=10)
        report['cuda_offload_confirmed']=gpu.returncode==0 and str(backend.pid) in {line.strip() for line in gpu.stdout.splitlines()}
        report['virtual_screen']=[APP.primaryScreen().geometry().width(),APP.primaryScreen().geometry().height()]
        store.clear_cache()
        with patch('babelander.controller.capture',side_effect=capture):
            for repeat in range(ARGS.passes):
                for fixture in FIXTURES:
                    run={'id':fixture.identifier,'pass':repeat,'capture_calls':0,'ocr_calls':0}
                    report['runs'].append(run);current.update(fixture=fixture,run=run,at=time.perf_counter())
                    region=Region(900 if fixture.pattern=='hud_tracker' else 35,20 if fixture.pattern=='world_event_banner' else 60,fixture.image.width(),fixture.image.height())
                    current['region']=region
                    window.region_selected(Mode.QUEST,region)
                    deadline=time.perf_counter()+18
                    while not run.get('received') and not run.get('error') and time.perf_counter()<deadline:
                        APP.processEvents();time.sleep(.003)
                    if not run.get('received') and not run.get('error'):run['error']=['timeout'];window.stop(Mode.QUEST)
                    run['single_capture_ocr']=run['capture_calls']==1 and run['ocr_calls']==1
                    print(json.dumps({k:run.get(k) for k in ('id','pass','full_qt_latency_ms','renderable','usable','min_contrast','error','render_warning')},ensure_ascii=True),flush=True)
                    save()
            report['no_quest_monitors']=not controller.capture_streams and not controller.live and Mode.QUEST not in window.monitoring
            report['metrics']=controller.metrics.snapshot();window.stop(Mode.QUEST);APP.processEvents()
            report['stop_hid_overlay']=not window.overlay(Mode.QUEST).isVisible()
            report['stop_released_backdrop']=window.overlay(Mode.QUEST).layout_data is None
            report['completed']=True
    except Exception as error:report['fatal_error']={'type':type(error).__name__,'message':str(error)}
    finally:
        window.close();controller.close();controller.join();store.close();APP.processEvents()
        report['own_model_stopped']=backend is None or backend.poll() is not None
        report['workers_stopped']=all(not t.is_alive() for queue in engine.queues.values() for t in queue.threads)
report['summary']=[]
for repeat in range(ARGS.passes):
    runs=[r for r in report['runs'] if r['pass']==repeat];latencies=[r['full_qt_latency_ms'] for r in runs if r.get('received')]
    report['summary'].append({'pass':repeat,'runs':len(runs),'rendered':sum(bool(r.get('renderable')) for r in runs),
        'usable':sum(bool(r.get('usable')) for r in runs),'source_complete':sum(bool(r.get('source_complete')) for r in runs),
        'numbers_preserved':sum(bool(r.get('numbers_preserved')) for r in runs),'errors':sum(bool(r.get('error')) for r in runs),
        'mean_result_ms':round(float(np.mean(latencies)),2) if latencies else None,'p95_result_ms':round(float(np.percentile(latencies,95)),2) if latencies else None,
        'max_result_ms':max(latencies) if latencies else None,'usable_within_700ms':sum(bool(r.get('usable')) and r['full_qt_latency_ms']<=700 for r in runs)})
report['application_source_unchanged']=all(hashlib.sha256((APPROOT/'babelander'/name).read_bytes()).hexdigest()==value for name,value in report['application_sha256'].items())
save()
html=['<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>任務卡結構實測</title><style>body{background:#11151b;color:#e2e7ee;font:16px system-ui;margin:30px}article{margin:36px 0;padding:18px;background:#1d242e;border-radius:12px}img{max-width:100%;height:auto}summary{cursor:pointer}code{color:#9edaff}pre{white-space:pre-wrap}</style><h1>'+str(len(FIXTURES))+' 張任務卡：原圖與實際翻譯</h1><p>原生 Qt 產生的測試卡，真 OCR、CUDA 模型與原位覆蓋。數值/原文完整性與對比檢查不是完整人工語意評分。</p>']
for fixture in FIXTURES:
    run=next((r for r in report['runs'] if r['id']==fixture.identifier and r['pass']==0),{})
    label='檢查通過' if run.get('usable') else '有問題，需核對'
    html.append(f'<article><h2>{fixture.theme} · {fixture.pattern} — {label}</h2><p>{run.get("full_qt_latency_ms","無結果")} ms · 最低對比 {run.get("min_contrast","N/A")}</p>')
    html.append('<p>'+' · '.join(getattr(fixture,'structural_features',()))+'</p>')
    filename=fixture.identifier+('-comparison.png' if run.get('renderable') else '-original.png')
    html.append(f'<img loading="lazy" src="{filename}" alt="{fixture.theme} 任務卡"><details><summary>測試細節</summary><pre>'+json.dumps({k:run.get(k) for k in ('render_warning','error','missing_source_words','extra_source_words','missing_source_numbers','extra_source_numbers','missing_target_numbers','extra_target_numbers','required_markers','art_unchanged','art_region_checks','cross_panel_blocks','source_color_checks')},ensure_ascii=False,indent=2)+'</pre></details></article>')
(DEST/'gallery.html').write_text(''.join(html),encoding='utf8')
print(json.dumps({'summary':report['summary'],'completed':report.get('completed'),'fatal_error':report.get('fatal_error'),'own_model_stopped':report.get('own_model_stopped'),'workers_stopped':report.get('workers_stopped')},ensure_ascii=True),flush=True)
report['passed']=bool(report.get('completed') and report.get('cuda_offload_confirmed') and report['own_model_stopped'] and report['workers_stopped'] and report.get('no_quest_monitors') and report.get('stop_hid_overlay') and report.get('stop_released_backdrop') and report['application_source_unchanged'] and len(report['runs'])==len(FIXTURES)*ARGS.passes and all(r.get('usable') and r.get('single_capture_ocr') for r in report['runs']))
save()
raise SystemExit(ARGS.strict and not report['passed'])
