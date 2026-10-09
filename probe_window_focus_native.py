"""Read-only foreground timing plus an OWN never-visible Win32 test window.

Does not activate/minimize existing windows, capture pixels, send keys or save
window names/handles/PIDs. Hidden test window is destroyed before returning.
"""
import ctypes
from ctypes import wintypes
import hashlib,json,time
from pathlib import Path
import numpy as np
from babelander.windows import dpi_aware
from babelander.window_focus import NativeWindows,WindowBinding,WindowFocus,FocusState,evaluate

ROOT=Path(__file__).parent
frozen={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*.py')}
dpi_aware();api=NativeWindows();kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.GetModuleHandleW.argtypes=[wintypes.LPCWSTR];kernel.GetModuleHandleW.restype=wintypes.HMODULE
instance=kernel.GetModuleHandleW(None)
proc_type=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM)
api.user.DefWindowProcW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
api.user.DefWindowProcW.restype=ctypes.c_ssize_t
proc=proc_type(lambda hwnd,message,wparam,lparam:api.user.DefWindowProcW(hwnd,message,wparam,lparam))
class WndClass(ctypes.Structure):
    _fields_=[('style',wintypes.UINT),('procedure',proc_type),('class_extra',ctypes.c_int),('window_extra',ctypes.c_int),
              ('instance',wintypes.HINSTANCE),('icon',wintypes.HICON),('cursor',wintypes.HANDLE),('background',wintypes.HBRUSH),
              ('menu',wintypes.LPCWSTR),('name',wintypes.LPCWSTR)]
api.user.RegisterClassW.argtypes=[ctypes.POINTER(WndClass)];api.user.RegisterClassW.restype=wintypes.ATOM
api.user.UnregisterClassW.argtypes=[wintypes.LPCWSTR,wintypes.HINSTANCE];api.user.UnregisterClassW.restype=wintypes.BOOL
api.user.CreateWindowExW.argtypes=[wintypes.DWORD,wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.DWORD,ctypes.c_int,ctypes.c_int,
                                  ctypes.c_int,ctypes.c_int,wintypes.HWND,wintypes.HMENU,wintypes.HINSTANCE,ctypes.c_void_p]
api.user.CreateWindowExW.restype=wintypes.HWND
api.user.DestroyWindow.argtypes=[wintypes.HWND];api.user.DestroyWindow.restype=wintypes.BOOL
api.user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
api.user.SetWindowPos.restype=wintypes.BOOL
name='BabelanderHiddenFocusProbe';wc=WndClass(0,proc,0,0,instance,None,None,None,None,name)
assert api.user.RegisterClassW(ctypes.byref(wc))
handle=None;checks={};samples=[]
try:
    # WS_OVERLAPPEDWINDOW, deliberately WITHOUT WS_VISIBLE.
    handle=api.user.CreateWindowExW(0,name,'',0x00CF0000,80,90,800,600,None,None,instance,None)
    assert handle
    target=api.info(handle);assert target is not None
    checks['owned_hidden_window_read']=not target.visible and target.client[2]>target.client[0]
    checks['enumerated_owned_handle']=any(info.hwnd==handle for info in api.enumerate())
    binding=WindowBinding(target.hwnd,target.pid,target.owner,target.client)
    checks['hidden_window_is_not_active']=WindowFocus(api).state(binding)==FocusState.AWAY
    # Move only this never-visible test window, without activating or reordering.
    assert api.user.SetWindowPos(handle,None,130,140,0,0,0x0015)
    moved=api.info(handle)
    checks['native_client_geometry_changes']=moved.client!=binding.client
    checks['moved_visible_snapshot_policy']=evaluate(binding,__import__('dataclasses').replace(moved,visible=True),target)==FocusState.MOVED
    foreground=api.foreground()
    if foreground is not None:
        observed=WindowBinding(foreground.hwnd,foreground.pid,foreground.owner,foreground.client)
        focus=WindowFocus(api)
        for _ in range(200):
            at=time.perf_counter();focus.state(observed);samples.append((time.perf_counter()-at)*1000)
    assert api.user.DestroyWindow(handle)
    checks['destroyed_window_read_none']=api.info(handle) is None
    handle=None
finally:
    if handle:api.user.DestroyWindow(handle)
    checks['class_unregistered']=bool(api.user.UnregisterClassW(name,instance))
report={'passed':all(checks.values()),'checks':checks,'visible_window_created':False,'foreground_control_calls':0,
        'screen_captures':0,'existing_windows_modified':False,'user_text_saved':False,
        'native_state_timing':{'samples':len(samples),'mean_ms':round(float(np.mean(samples)),4) if samples else None,
                               'p95_ms':round(float(np.percentile(samples,95)),4) if samples else None,
                               'max_ms':round(max(samples),4) if samples else None},
        'real_game_validated':False,'source_sha256':frozen,
        'source_unchanged':all(hashlib.sha256((ROOT/'babelander'/n).read_bytes()).hexdigest()==sha for n,sha in frozen.items())}
(ROOT/'test-results/window-focus-native-a15.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'},indent=2));raise SystemExit(not report['passed'])
