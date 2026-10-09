"""Small read-only GDI timing probe; pixels never saved, inspected or OCRed."""
from bootstrap import prepare
prepare()
import ctypes,json,time
from pathlib import Path
from babelander.capture import capture
from babelander.types import Region
from replay_analysis import stats
from replay_resources import process,K
user=ctypes.WinDLL('user32',use_last_error=True)
user.SetProcessDpiAwarenessContext.argtypes=[ctypes.c_void_p]
user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
user.GetGuiResources.argtypes=[ctypes.c_void_p,ctypes.c_uint]
user.GetGuiResources.restype=ctypes.c_uint
width,height=user.GetSystemMetrics(0),user.GetSystemMetrics(1)
handle=K.GetCurrentProcess();before=user.GetGuiResources(handle,0)
rows=[]
for label,w,h in [('small_subtitle',650,180),('large_subtitle',1450,250),('equipment',450,737)]:
    w,h=min(w,width),min(h,height)
    region=Region((width-w)//2,(height-h)//2,w,h);samples=[];errors=[]
    capture(region)
    for index in range(20):
        started=time.perf_counter()
        try:
            image=capture(region);assert image.shape==(h,w,3);del image
            samples.append((time.perf_counter()-started)*1000)
        except Exception as error:errors.append(type(error).__name__)
        time.sleep(.1)
    rows.append({'roi_dimensions':[w,h],'case':label,'cpu_readable_capture':stats(samples),'errors':errors})
report={'scope':'Live primary desktop GDI capture to CPU-readable ndarray, no OCR/UI/compositor/game frametime measurement.',
    'real_desktop_capture':True,'frames_saved':0,'pixel_content_or_text_logged':False,'visible_windows_created':0,
    'samples_per_roi':20,'rows':rows,'gdi_handles_before':before,'gdi_handles_after':user.GetGuiResources(handle,0),
    'app_resources_after':process(),'known_game_or_game_scene':False}
out=Path('test-results/native-capture-a13.json');out.write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
