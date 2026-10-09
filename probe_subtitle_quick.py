"""Full-file subtitle translation plus sampled moving-background OCR, no playback waits."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import argparse
from dataclasses import asdict
from pathlib import Path
import hashlib
import html
import json
import math
import re
import statistics
import tempfile
import time
from unittest.mock import patch
import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont,QFontDatabase,QFontMetrics,QImage,QPainter,QPainterPath,QColor,QPen
from PySide6.QtWidgets import QApplication
from babelander import __version__
from babelander.controller import Controller
from babelander.engine import Engine
from babelander.settings import Settings
from babelander.security import KeyVault
from babelander.storage import Store
from babelander.types import Mode,Region,Cancellation
from babelander.window import MainWindow

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--subtitle',type=Path,required=True)
args=parser.parse_args()
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'test-results/subtitle-quick'
OUT.mkdir(exist_ok=True,parents=True)
SOURCE=args.subtitle.resolve()
source_bytes=SOURCE.read_bytes()
source_hash=hashlib.sha256(source_bytes).hexdigest()
blocks=re.split(r'\n\s*\n',source_bytes.decode('utf-8-sig').replace('\r\n','\n').strip())
CORPUS=[]
for block in blocks:
    lines=block.splitlines()
    if len(lines)<3 or '-->' not in lines[1]:raise ValueError('Invalid SRT cue: '+block[:100])
    original='\n'.join(lines[2:])
    text=re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>','',original))).strip()
    if text:CORPUS.append({'cue_id':int(lines[0]),'timecode':lines[1],'original':original,'text':text})
unique=list({row['text']:row for row in reversed(CORPUS)}.values())[::-1]
assert len(unique)>=100
SAMPLE=[unique[round(i*(len(unique)-1)/99)] for i in range(100)]
assert len({r['text'] for r in SAMPLE})==100
(OUT/'corpus.json').write_text(json.dumps(CORPUS,ensure_ascii=False,indent=2),encoding='utf-8')
def normalized(text):return re.sub(r'\s+',' ',text).strip()
def lexical(text):return re.sub(r'[^a-z0-9%]+',' ',text.casefold()).strip()
def stats(values):
    if not values:return None
    values=sorted(values)
    return {'n':len(values),'mean_ms':round(statistics.mean(values),2),
            'p50_ms':round(values[math.ceil(len(values)*.5)-1],2),
            'p95_ms':round(values[math.ceil(len(values)*.95)-1],2),'max_ms':round(values[-1],2)}
APP=QApplication(['Babelander2 subtitle quick benchmark'])
QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/arial.ttf'))
assert 'Arial' in QFontDatabase.families()
APP.setStyle('Fusion');APP.setStyleSheet((ROOT/'babelander/theme.qss').read_text(encoding='utf-8'))
FONT=QFont('Arial',30);FM=QFontMetrics(FONT)
YY,XX=np.mgrid[0:32,0:182].astype(np.float32)
def render(text,step):
    rng=np.random.default_rng(7127+step)
    wave=24*np.sin(XX*.12+step*.08)+18*np.cos(YY*.31-step*.05)
    grain=rng.normal(0,15,XX.shape)
    small=np.stack([72+wave+grain,53+wave*.8+grain,42-wave*.3+grain],axis=2)
    frame=cv2.resize(np.clip(small,0,170).astype(np.uint8),(1450,250),interpolation=cv2.INTER_LINEAR)
    image=QImage(frame.data,1450,250,4350,QImage.Format.Format_BGR888)
    lines=[];line=''
    for word in text.split():
        candidate=(line+' '+word).strip()
        if FM.horizontalAdvance(candidate)>1390 and line:lines.append(line);line=word
        else:line=candidate
    if line:lines.append(line)
    assert len(lines)<=4
    path=QPainterPath()
    for i,line in enumerate(lines):path.addText(24,55+i*50,FONT,line)
    painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor('black'),4));painter.setBrush(QColor('black'));painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('white'));painter.drawPath(path);painter.end()
    return frame
assert np.count_nonzero(render(SAMPLE[0]['text'],0).min(axis=2)>230)>1000
frozen=json.loads((ROOT/'test-results/frozen-source-a4.json').read_text(encoding='utf-8-sig'))
def source_unchanged():return all(hashlib.sha256((ROOT/'babelander'/n).read_bytes()).hexdigest()==d for n,d in frozen.items())
assert source_unchanged()
report={'version':__version__,'subtitle_file':SOURCE.name,'subtitle_sha256':source_hash,
        'total_cues':len(CORPUS),'unique_texts':len(unique),'sampled_cues':SAMPLE,
        'translation':[],'ocr_ui':[],'extra_ocr_frames':[],'completed':False,
        'qt_platform':APP.platformName(),'real_desktop_capture':False,'cloud_requests':0,
        'profile':'fast','model':'Qwen3 1.7B Q4_K_M','font':'Arial 30 pt, white fill after black outline',
        'noise_steps':[0,17,43],'roi':[1450,250],'application_source_sha256':frozen,
        'scope':'All subtitle cues translated sequentially, natural duplicate cache behavior. 100 unique cues uniformly sampled across file; one real OCR/translation/Qt pass and two extra OCR snapshots of different animated-background times each. No 3-second waits, no monitoring playback, no scan/stability timing, no GDI/game FPS measurement.'}
def save(): (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
def log(value):print(json.dumps(value,ensure_ascii=False),flush=True)
with tempfile.TemporaryDirectory(prefix='Babelander2-subtitle-quick-') as directory:
    settings=Settings(hotkeys={},model_path=str(ROOT/'test-results/asset-install/assets/downloads/Qwen_Qwen3-1.7B-Q4_K_M.gguf'),
        server_path=str(next((ROOT/'test-results/asset-install/assets').glob('llama-b10896-*/llama-server.exe'))))
    store=Store(directory);vault=KeyVault(directory);engine=Engine(settings,store,vault,directory)
    controller=Controller(engine,store,settings);window=MainWindow(controller,store,settings,vault,directory)
    engine.acquire_client('subtitle-quick-benchmark')
    delivered=[];errors=[];last_result=[]
    def metadata(result):
        last_result[:]=[{'generation':result.generation,'stages':dict(result.stages),'ocr_ms':result.ocr_ms,
            'worker_ms':result.total_ms,'cache_hit':any(t.cache_hit for t in result.translations),
            'model_ms':sum(t.model_ms for t in result.translations),
            'backend_states':[t.backend_state for t in result.translations]}]
    controller.result.connect(metadata,Qt.ConnectionType.DirectConnection)
    controller.delivery.connect(lambda mode:delivered.append(time.perf_counter()))
    controller.failed.connect(lambda mode,message,generation:errors.append(message))
    started=time.perf_counter();owned=None
    try:
        for i,case in enumerate(CORPUS,1):
            at=time.perf_counter();result=engine.request(case['text'],Mode.DIALOG,Cancellation())
            report['translation'].append({**case,**asdict(result),'elapsed_ms':round((time.perf_counter()-at)*1000,3)})
            APP.processEvents()
            if i%50==0 or i==len(CORPUS):
                save();log({'phase':'full_subtitle_translation','done':i,'total':len(CORPUS)})
        report['translation_pass_seconds']=round(time.perf_counter()-started,3)
        # Warm CPU OCR outside timing and prevent full-file cache from
        # artificially accelerating the sampled OCR-to-UI pass.
        controller.ocr.recognize(render(SAMPLE[0]['text'],0),Cancellation())
        store.clear_cache()
        sampled_started=time.perf_counter()
        for i,case in enumerate(SAMPLE,1):
            frame=render(case['text'],0)
            hashes=[hashlib.sha256(frame).hexdigest()]
            if i in (1,50,100):
                QImage(frame.data,1450,250,4350,QImage.Format.Format_BGR888).save(str(OUT/f'cue-{case["cue_id"]}-step-0.png'))
            before_ui,before_errors=len(delivered),len(errors)
            at=time.perf_counter()
            with patch('babelander.controller.capture',side_effect=lambda region:frame.copy()):
                controller.submit_region(Mode.DIALOG,Region(0,0,1450,250))
                deadline=time.monotonic()+90
                while len(delivered)==before_ui and len(errors)==before_errors and time.monotonic()<deadline:
                    APP.processEvents();time.sleep(.001)
                if len(errors)>before_errors:raise RuntimeError(errors[-1])
                if len(delivered)==before_ui:raise TimeoutError('Subtitle UI completion timeout')
                page=window.pages[Mode.DIALOG];source=normalized(page.source.toPlainText())
                row={**case,'elapsed_ms':round((delivered[-1]-at)*1000,3),'recognized':source,
                    'target':page.target.toPlainText(),'ocr_exact':source==case['text'],
                    'lexical_exact':lexical(source)==lexical(case['text']),
                    'warning':page.ocr_note.text() if not page.ocr_note.isHidden() else ''}
                assert last_result and last_result[0]['generation']==controller.generations[Mode.DIALOG]
                row.update(last_result[0]);report['ocr_ui'].append(row)
            for step in (17,43):
                frame=render(case['text'],step);hashes.append(hashlib.sha256(frame).hexdigest())
                at=time.perf_counter();lines=controller.ocr.recognize(frame,Cancellation())
                recognized=normalized(' '.join(line.text for line in lines))
                report['extra_ocr_frames'].append({'cue_id':case['cue_id'],'text':case['text'],'step':step,
                    'recognized':recognized,'elapsed_ms':round((time.perf_counter()-at)*1000,3),
                    'ocr_exact':recognized==case['text'],'lexical_exact':lexical(recognized)==lexical(case['text']),
                    'confidence':min((line.confidence for line in lines),default=0)})
                if i==50:QImage(frame.data,1450,250,4350,QImage.Format.Format_BGR888).save(str(OUT/f'cue-{case["cue_id"]}-step-{step}.png'))
            assert len(set(hashes))==3
            row['frame_hashes']=hashes
            if i%20==0:
                save();log({'phase':'sampled_animated_background','done':i,'total':100,'ocr_frames':i*3})
        report['sampled_pass_seconds']=round(time.perf_counter()-sampled_started,3)
        report['completed']=True
    except Exception as error:report['fatal_error']={'type':type(error).__name__,'message':str(error)}
    finally:
        owned=engine.local.process;engine.release_client('subtitle-quick-benchmark')
        window.close();controller.join();store.close();APP.processEvents()
        report['owned_model_stopped']=owned is not None and owned.poll() is not None
        report['workers_stopped']=not engine.release_worker.is_alive() and all(not t.is_alive() for q in engine.queues.values() for t in q.threads)
        report['source_unchanged']=source_unchanged()
        report['subtitle_unchanged']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()==source_hash
        report['wall_seconds']=round(time.perf_counter()-started,3)
rows=report['translation'];ui=report['ocr_ui'];extra=report['extra_ocr_frames']
report['summary']={'translation_all':stats([r['elapsed_ms'] for r in rows]),
    'translation_cold':stats([r['elapsed_ms'] for r in rows if r['backend_state']=='cold']),
    'translation_warm':stats([r['elapsed_ms'] for r in rows if r['backend_state']=='warm']),
    'translation_cache':stats([r['elapsed_ms'] for r in rows if r['cache_hit']]),
    'translation_usable':sum(bool(r['target']) and not r['warning'] for r in rows),
    'translation_rejected':sum(bool(r['warning']) for r in rows),
    'ocr_ui_all':stats([r['elapsed_ms'] for r in ui]),
    'ocr_ui_usable':sum(bool(r['target']) and not r['warning'] for r in ui),
    'ocr_ui_exact':sum(r['ocr_exact'] for r in ui),'ocr_ui_lexical_exact':sum(r['lexical_exact'] for r in ui),
    'all_ocr_frames':len(ui)+len(extra),'all_ocr_exact':sum(r['ocr_exact'] for r in ui+extra),
    'all_ocr_lexical_exact':sum(r['lexical_exact'] for r in ui+extra),
    'extra_ocr_latency':stats([r['elapsed_ms'] for r in extra]),
    'background_text_changed_cases':sum(len({r['recognized'] for r in [u]+[e for e in extra if e['cue_id']==u['cue_id']]})>1 for u in ui),
    'sampled_ui_cache_hits':sum(r['cache_hit'] for r in ui),
    'errors':errors}
save();log({'completed':report['completed'],'summary':report['summary'],'wall_seconds':report['wall_seconds']})
raise SystemExit(not(report['completed'] and report['owned_model_stopped'] and report['workers_stopped'] and report['source_unchanged'] and report['subtitle_unchanged']))
