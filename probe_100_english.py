"""100 new English cases, two uncached passes, real OCR/model and offscreen Qt.

No desktop capture, cloud requests, user settings, hotkeys or model changes.
"""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
from pathlib import Path
from dataclasses import asdict
import hashlib
import json
import math
import re
import statistics
import tempfile
import time
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import QRect,Qt
from PySide6.QtGui import QFont,QFontDatabase,QImage,QPainter,QColor
from PySide6.QtWidgets import QApplication
from babelander import __version__
from babelander.controller import Controller
from babelander.engine import Engine
from babelander.settings import Settings
from babelander.security import KeyVault
from babelander.storage import Store
from babelander.types import Mode,Region,Cancellation
from babelander.window import MainWindow

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'test-results/english-100'
OUT.mkdir(exist_ok=True,parents=True)

GROUPS={
 'short':[
  'The lantern has gone out.',
  'Someone is following our wagon.',
  'Your shield is almost broken.',
  'That merchant knows my brother.',
  'The northern tunnel looks abandoned.',
  'This key belongs to the captain.',
  'Our horses need fresh water.',
  'The prisoner has already escaped.',
  'Her footsteps suddenly stopped upstairs.',
  'The harbor smells of burnt wood.',
  'My arrows cannot pierce that armor.',
  'A stranger is waiting outside.',
  'Your disguise fooled the sentries.',
  'The last ferry leaves at dawn.',
  'Their campfire is still warm.',
  'This potion tastes surprisingly bitter.',
  'The floor beneath us is moving.',
  'Our healer is trapped behind you.',
  'The moon has disappeared again.',
  'Nobody remembers the missing prince.',
 ],
 'story':[
  'I promised your mother that I would bring you home safely.',
  'The old watchtower was abandoned after the river changed its course.',
  'She recognized the seal but refused to open the sealed letter.',
  'We found your sword beneath the roots of a fallen oak.',
  'Every winter, the villagers leave bread beside the empty throne.',
  'The captain laughed until he saw the blood on my sleeve.',
  'That quiet child has been listening to us the entire time.',
  'I thought the bells meant victory, but they were a warning.',
  'Your father never told me why he burned the final map.',
  'The innkeeper lowered his voice when we mentioned the silver mine.',
  'Her message arrived three days after the soldiers captured the city.',
  'We shared a meal with the enemy before we knew his name.',
  'The broken statue once stood at the center of the market.',
  'He carried the same empty bottle through seven years of exile.',
  'The queen asked for honesty, then dismissed everyone who answered her.',
  'A single candle was burning in the house we had searched yesterday.',
  'My sister believed the song could guide lost sailors through the fog.',
  'The messenger delivered the package without asking for payment or shelter.',
  'They buried the treasure where the two mountain shadows meet.',
  'I have crossed this valley before, but the trees were different then.',
 ],
 'action':[
  'Stay behind the stone pillars while the archers reload their crossbows.',
  'Use the eastern stairway and avoid the guards near the kitchen.',
  'Tell our scout to check the rooftops before we enter the plaza.',
  'Pull the wounded soldier away from the burning siege engine.',
  'Keep your weapon lowered until the ambassador finishes speaking.',
  'Bring the crystal to the shrine without touching its cracked surface.',
  'Follow the muddy tracks until they disappear into the shallow stream.',
  'Save your strongest spell for the creature guarding the final chamber.',
  'Search the abandoned carts for blankets, medicine, and unspoiled food.',
  'Wait beside the fountain while I speak with the suspicious librarian.',
  'Destroy the alarm bell before the patrol reaches the courtyard.',
  'Move the supply crates away from the damaged bridge support.',
  'Ask the blacksmith whether this blade can be repaired by tomorrow.',
  'Return the stolen ring to its owner before accepting the reward.',
  'Mark the safe passage with chalk so the others can follow us.',
  'Switch to your bow when the creature retreats onto the balcony.',
  'Protect the engineer while she resets the frozen control panel.',
  'Take the injured travelers to the shelter beyond the orchard.',
  'Inspect the loose stones around the doorway for hidden pressure plates.',
  'Keep the signal fire burning until all the fishing boats return.',
 ],
 'conditions':[
  'If the enemy raises its left claw, dodge backward instead of rolling toward the wall.',
  'You may open the gate only after all 4 warning lights have turned blue.',
  'The barrier absorbs 250 damage, but it breaks immediately if the caster is stunned.',
  'Collect 7 iron fragments and deliver them before the remaining timer reaches 02:45.',
  'This charm restores 15 health every 3 seconds while you remain outside combat.',
  'Do not activate the second lever unless the first chamber has completely drained.',
  'When your stamina falls below 40%, heavy attacks consume an additional 8 points.',
  'The rescue party will wait for 12 minutes before returning to the southern camp.',
  'Defeat 6 armored spiders without allowing any of them to reach the supply wagon.',
  'Each successful parry reduces the cooldown by 2 seconds, up to 5 times.',
  'If the lantern turns red, stop moving and wait until the corridor becomes silent.',
  'Recover the lost banner without using fast travel or leaving the mission area.',
  'The poison deals 9 damage per second for 7 seconds unless an antidote is used.',
  'You need at least 180 gold to repair both the helmet and the damaged boots.',
  'Keep your distance from the statue until the protective runes stop flashing.',
  'The chest can be unlocked only by a player carrying the copper expedition badge.',
  'After defeating the guardian, speak to the scholar before picking up the ancient crown.',
  'During the final wave, protect at least 2 villagers and keep the workshop intact.',
  'Do not remove the gem yet; the device is still drawing power from it.',
  'Your mount cannot enter the marsh while its saddle is loaded with fragile supplies.',
 ],
 'long':[
  'I would have trusted his explanation if he had not described a room that nobody outside the royal family was supposed to know existed.',
  'The villagers insist that the creature only appears during heavy rain, yet every footprint we found was pressed into dry ground beneath the old windmill.',
  'Before you accuse the captain of betraying us, remember that he stayed behind to help the wounded while the rest of the fleet escaped.',
  'We can recover the missing supplies by following the river north, but doing so will leave the western outpost without enough soldiers to defend itself.',
  'She said the necklace was worthless, then offered more gold for it than the merchant had earned during an entire year of business.',
  'The prisoner claims he never entered the treasury, although the guards found a matching piece of his torn coat caught on the inner door.',
  'If we destroy the machine now, the city will lose its defenses; if we leave it running, the surrounding villages may disappear beneath the flood.',
  'You do not have to forgive him to accept his help, but make sure he understands that the remaining prisoners are still under our protection.',
  'The scholar translated most of the inscription, but the final sentence uses a dialect that has not been spoken since the northern kingdom collapsed.',
  'I asked her to watch the entrance, not to follow the stranger into the forest, and now we have lost both our guide and our map.',
  'The commander will approve the expedition only if we bring enough medicine for the injured scouts and find another route around the damaged aqueduct.',
  'Although the gate appears unlocked, touching the handle before the nearby candles burn out will alert every guard stationed inside the fortress.',
  'The boy remembered where the soldiers had hidden their weapons, but he could not tell us which tunnel they used to leave the village.',
  'Take whichever path you think is safer, provided that you reach the abandoned chapel before the storm cuts off the mountain crossing.',
  'Our agreement covers the delivery of the sealed crate, not whatever may be inside it, so we should not open it without the owners permission.',
  'He was ready to surrender until he heard that the opposing army had already released the hostages and withdrawn from the eastern border.',
  'If the signal does not arrive by midnight, assume the rescue failed and lead the remaining survivors to the shelters beneath the old observatory.',
  'The medicine can ease her pain, but it cannot reverse the curse unless we recover the missing page from the book that started all this.',
  'We thought the distant lights belonged to another caravan until they moved against the wind and vanished one by one above the frozen lake.',
  'You may keep the reward, but promise me that you will tell the families what happened here instead of repeating the story the governor wants them to hear.',
 ],
}
CASES=[{'id':i+1,'group':group,'text':text} for i,(group,text) in enumerate((g,t) for g,items in GROUPS.items() for t in items)]
assert len(CASES)==100 and len({r['text'].casefold() for r in CASES})==100
# Check novelty against old reports/source, before writing this new corpus.
prior_files=[p for p in (ROOT/'assets/verification').glob('*.json') if not p.name.startswith('english-100')]+list((ROOT/'babelander').glob('*.py'))
prior_files += [p for p in ROOT.glob('probe*.py') if p.name!=Path(__file__).name]
old_text='\n'.join(p.read_text(encoding='utf-8-sig',errors='replace').casefold() for p in prior_files)
assert not [r['id'] for r in CASES if r['text'].casefold() in old_text], 'Repeated previous benchmark input'
(OUT/'corpus.json').write_text(json.dumps(CASES,ensure_ascii=False,indent=2),encoding='utf-8')

def stats(values):
    if not values:return None
    ordered=sorted(values)
    def percentile(p):return ordered[max(0,math.ceil(len(ordered)*p)-1)]
    return {'samples':len(values),'mean_ms':round(statistics.mean(values),2),'p50_ms':round(percentile(.5),2),
            'p95_ms':round(percentile(.95),2),'min_ms':round(min(values),2),'max_ms':round(max(values),2)}

def checkpoint(report):
    (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

APP=QApplication(['Babelander2 100-sentence background benchmark'])
for name in ('arial.ttf','segoeui.ttf','msjh.ttc'):
    path=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name
    if path.is_file():QFontDatabase.addApplicationFont(str(path))
assert 'Arial' in QFontDatabase.families()
APP.setStyle('Fusion');APP.setStyleSheet((ROOT/'babelander/theme.qss').read_text(encoding='utf-8'))
model=ROOT/'test-results/asset-install/assets/downloads/Qwen_Qwen3-1.7B-Q4_K_M.gguf'
server=next((ROOT/'test-results/asset-install/assets').glob('llama-b10896-*/llama-server.exe'))
frozen=json.loads((ROOT/'test-results/frozen-source-a4.json').read_text(encoding='utf-8-sig'))
assert all(hashlib.sha256((ROOT/'babelander'/n).read_bytes()).hexdigest()==digest for n,digest in frozen.items())
report={'version':__version__,'hardware':'RTX 3080 Ti; same machine as alpha 4 verification',
        'model':model.name,'profile':'fast','context':2048,'temperature':0,'thinking':False,
        'qt_platform':APP.platformName(),'unique_sentences':100,'new_against_previous_fixture_corpus':True,
        'mode':'dialog','cloud_requests':0,'real_desktop_capture':False,'model_pass':[],'ocr_ui_pass':[],
        'scope':'Two uncached passes over 100 unique sentences. OCR uses owned rendered images; capture is a CPU frame copy. No GDI/game/polling/stability/compositor latency claim. UI end means Qt slot applied target or warning, not visible desktop pixels.',
        'application_source_sha256':frozen,'summary':{},'completed':False}

with tempfile.TemporaryDirectory(prefix='Babelander2-English100-') as directory:
    settings=Settings(model_path=str(model),server_path=str(server),hotkeys={})
    store=Store(directory);vault=KeyVault(directory);engine=Engine(settings,store,vault,directory)
    controller=Controller(engine,store,settings);window=MainWindow(controller,store,settings,vault,directory)
    engine.acquire_client('benchmark-100')
    delivered=[];errors=[];last_result=[]
    def received_result(result):
        last_result[:] = [{'generation':result.generation,'stages':dict(result.stages),'ocr_ms':result.ocr_ms,
            'worker_ms':result.total_ms,'cache_hit':any(t.cache_hit for t in result.translations),
            'model_ms':sum(t.model_ms for t in result.translations),
            'backend_states':[t.backend_state for t in result.translations]}]
    controller.result.connect(received_result,Qt.ConnectionType.DirectConnection)
    controller.delivery.connect(lambda mode:delivered.append(time.perf_counter()))
    controller.failed.connect(lambda mode,message,generation:errors.append((time.perf_counter(),message)))
    started_all=time.perf_counter();owned=None
    try:
        for case in CASES:
            at=time.perf_counter()
            result=engine.request(case['text'],Mode.DIALOG,Cancellation())
            row={**case,**asdict(result),'elapsed_ms':round((time.perf_counter()-at)*1000,3)}
            report['model_pass'].append(row)
            assert not result.cache_hit,'Unexpected cache in first pass'
            if case['id']%20==0:
                checkpoint(report)
                print(json.dumps({'phase':'translation','done':case['id'],'total':100,
                                  'mean_ms':stats([r['elapsed_ms'] for r in report['model_pass']])['mean_ms']},ensure_ascii=False),flush=True)
        store.clear_cache()
        for case in CASES:
            image=QImage(1450,250,QImage.Format.Format_RGB32);image.fill(QColor('white'))
            painter=QPainter(image);painter.setPen(QColor('black'));painter.setFont(QFont('Arial',30))
            painter.drawText(QRect(24,18,1400,220),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop|Qt.TextFlag.TextWordWrap,case['text'])
            painter.end()
            frame=np.frombuffer(image.bits(),dtype=np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)[:,:image.width(),:3].copy()
            begin_delivered,begin_errors=len(delivered),len(errors)
            at=time.perf_counter()
            with patch('babelander.controller.capture',side_effect=lambda region:frame.copy()):
                controller.submit_region(Mode.DIALOG,Region(0,0,1450,250))
                deadline=time.monotonic()+90
                while len(delivered)==begin_delivered and len(errors)==begin_errors and time.monotonic()<deadline:
                    APP.processEvents();time.sleep(.001)
                if len(errors)>begin_errors:
                    ended,message=errors[-1]
                    row={**case,'elapsed_ms':round((ended-at)*1000,3),'error':message,'target':''}
                elif len(delivered)>begin_delivered:
                    ended=delivered[-1]
                    target=window.pages[Mode.DIALOG].target.toPlainText()
                    source=window.pages[Mode.DIALOG].source.toPlainText()
                    # The UI consumes its coalesced payload; the diagnostic hook
                    # retains only metadata for the same generation.
                    row={**case,'elapsed_ms':round((ended-at)*1000,3),'recognized':source,'target':target,
                         'ocr_exact':re.sub(r'\s+',' ',source).strip()==case['text'],
                         'warning':window.pages[Mode.DIALOG].ocr_note.text() if not window.pages[Mode.DIALOG].ocr_note.isHidden() else ''}
                    until_metadata=time.monotonic()+2
                    while (not last_result or last_result[-1]['generation']!=controller.generations[Mode.DIALOG]) and time.monotonic()<until_metadata:
                        time.sleep(.001)
                    assert last_result and last_result[-1]['generation']==controller.generations[Mode.DIALOG]
                    row.update(last_result[-1])
                    assert not row['cache_hit'],'Unexpected cache in OCR pass'
                else:raise TimeoutError(f'No UI completion for benchmark case {case["id"]}')
            report['ocr_ui_pass'].append(row)
            if case['id']%20==0:
                checkpoint(report)
                print(json.dumps({'phase':'ocr_to_ui','done':case['id'],'total':100,
                                  'mean_ms':stats([r['elapsed_ms'] for r in report['ocr_ui_pass']])['mean_ms']},ensure_ascii=False),flush=True)
        report['completed']=True
    except Exception as error:
        report['fatal_error']={'type':type(error).__name__,'message':str(error)}
    finally:
        owned=engine.local.process
        engine.release_client('benchmark-100')
        window.close();controller.join();store.close();APP.processEvents()
        report['owned_model_stopped']=owned is not None and owned.poll() is not None
        report['workers_stopped']=not engine.release_worker.is_alive() and all(not t.is_alive() for q in engine.queues.values() for t in q.threads)
        report['wall_seconds']=round(time.perf_counter()-started_all,3)

model_rows=report['model_pass'];ui_rows=report['ocr_ui_pass']
report['summary']={
    'translation_all':stats([r['elapsed_ms'] for r in model_rows]),
    'translation_cold':stats([r['elapsed_ms'] for r in model_rows if r['backend_state']=='cold']),
    'translation_warm':stats([r['elapsed_ms'] for r in model_rows if r['backend_state']=='warm']),
    'ocr_to_ui_all':stats([r['elapsed_ms'] for r in ui_rows]),
    'ocr_to_ui_usable':stats([r['elapsed_ms'] for r in ui_rows if r.get('target') and not r.get('warning') and not r.get('error')]),
    'translation_rejected':sum(bool(r['warning']) for r in model_rows),
    'ocr_to_ui_rejected':sum(bool(r.get('warning') or r.get('error')) for r in ui_rows),
    'ocr_exact':sum(r.get('ocr_exact',False) for r in ui_rows),
    'cache_hits':sum(r.get('cache_hit',False) for r in model_rows+ui_rows),
    'groups':{group:{'sentences':len(items),'translation':stats([r['elapsed_ms'] for r in model_rows if r['group']==group]),
                     'ocr_to_ui':stats([r['elapsed_ms'] for r in ui_rows if r['group']==group])} for group,items in GROUPS.items()},
}
checkpoint(report)
print(json.dumps({'completed':report['completed'],'summary':report['summary']},ensure_ascii=False),flush=True)
raise SystemExit(not(report['completed'] and report['owned_model_stopped'] and report['workers_stopped']))
