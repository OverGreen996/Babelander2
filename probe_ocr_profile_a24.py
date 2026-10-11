"""Offscreen real OCR profile, without desktop capture or model startup."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import cProfile,io,json,pstats,time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from babelander.ocr import OCR
from babelander.chat_ocr import ChatRecognitionCache
from babelander.types import Cancellation
from chat_fixtures import chat_frame
from chat_gate_fixtures import variants
app=QApplication([])
for f in ('arial.ttf','msjh.ttc'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+f)
ocr=OCR();token=Cancellation();cache=ChatRecognitionCache()
frames=[variants(chat_frame(list(range(i-3,i+1)))[1],i) for i in (5,25,45,65,85,97)]
ocr.recognize(frames[0][0],token)
profile=cProfile.Profile();samples=[]
profile.enable()
for pair in frames:
    cache.clear()
    for repeat in range(4):
        at=time.perf_counter();lines=ocr.recognize(pair[repeat%2],token,chat_cache=cache)
        samples.append({'ms':(time.perf_counter()-at)*1000,'cache':dict(cache.last),'texts':[l.text for l in lines]})
profile.disable()
out=Path('test-results/ocr-profile-a24');out.mkdir(parents=True,exist_ok=True)
stream=io.StringIO();pstats.Stats(profile,stream=stream).strip_dirs().sort_stats('cumtime').print_stats(45)
(out/'profile.txt').write_text(stream.getvalue(),encoding='utf8')
(out/'samples.json').write_text(json.dumps(samples,ensure_ascii=False,indent=2),encoding='utf8')
print(stream.getvalue())
