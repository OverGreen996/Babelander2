"""Read-only Win32 foreground binding; no activation, hooks or screenshot history."""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from enum import StrEnum
import os
import sys
import threading
from .types import Cancellation,Cancelled,Region


class FocusState(StrEnum):
    ACTIVE='active'
    AWAY='away'
    MINIMIZED='minimized'
    INVALID='invalid'
    MOVED='moved'


@dataclass(frozen=True)
class WindowInfo:
    hwnd:int
    pid:int
    owner:int
    client:tuple
    outer:tuple
    visible:bool=True
    minimized:bool=False
    cloaked:bool=False
    shell:bool=False
    monitor:int=0
    dpi:int=0
    monitor_bounds:tuple|None=None


@dataclass(frozen=True)
class WindowBinding:
    hwnd:int
    pid:int
    owner:int
    client:tuple
    monitor:int=0
    dpi:int=0
    monitor_bounds:tuple|None=None

    @classmethod
    def from_info(cls,window):
        return cls(window.hwnd,window.pid,window.owner,window.client,window.monitor,window.dpi,window.monitor_bounds)


def contains(rect,region):
    return rect[0]<=region.x and rect[1]<=region.y and rect[2]>=region.x+region.width and rect[3]>=region.y+region.height


def intersects(rect,region):
    return min(rect[2],region.x+region.width)>max(rect[0],region.x) and min(rect[3],region.y+region.height)>max(rect[1],region.y)


def choose_binding(windows,region,own_pid):
    # Z-order enumeration. Never bind a lower window through another app.
    for window in windows:
        if window.pid==own_pid or not window.visible or window.minimized or window.cloaked or window.shell:continue
        if intersects(window.outer,region):
            if not contains(window.client,region):return None
            return WindowBinding.from_info(window)
    return None


def evaluate(binding,target,foreground):
    if target is None or (target.hwnd,target.pid,target.owner)!=(binding.hwnd,binding.pid,binding.owner):return FocusState.INVALID
    if target.minimized:return FocusState.MINIMIZED
    if not target.visible or target.cloaked:return FocusState.AWAY
    if (target.client,target.monitor,target.dpi,target.monitor_bounds)!=(binding.client,binding.monitor,binding.dpi,binding.monitor_bounds):return FocusState.MOVED
    if foreground is None or foreground.pid!=binding.pid or foreground.owner!=binding.owner:return FocusState.AWAY
    return FocusState.ACTIVE


def rebase_region(binding,target,region):
    """Only physical-pixel translation, with known unchanged monitor and DPI."""
    if target is None or (target.hwnd,target.pid,target.owner)!=(binding.hwnd,binding.pid,binding.owner):return None
    if not target.visible or target.minimized or target.cloaked:return None
    if not binding.monitor or not binding.dpi or binding.monitor_bounds is None:return None
    if (target.monitor,target.dpi,target.monitor_bounds)!=(binding.monitor,binding.dpi,binding.monitor_bounds):return None
    old,new=binding.client,target.client
    if (old[2]-old[0],old[3]-old[1])!=(new[2]-new[0],new[3]-new[1]):return None
    if not contains(old,region):return None
    moved=Region(region.x+new[0]-old[0],region.y+new[1]-old[1],region.width,region.height)
    if not contains(new,moved) or not contains(target.monitor_bounds,moved):return None
    return WindowBinding.from_info(target),moved


class MonitorInfo(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('monitor',wintypes.RECT),('work',wintypes.RECT),('flags',wintypes.DWORD)]


class NativeWindows:
    """Explicit 64-bit handle signatures. All methods only read window state."""
    def __init__(self):
        self.user=ctypes.WinDLL('user32',use_last_error=True)
        self.dwm=ctypes.WinDLL('dwmapi',use_last_error=True)
        specifications={
            'IsWindow':([wintypes.HWND],wintypes.BOOL),
            'IsWindowVisible':([wintypes.HWND],wintypes.BOOL),
            'IsIconic':([wintypes.HWND],wintypes.BOOL),
            'GetForegroundWindow':([],wintypes.HWND),
            'GetAncestor':([wintypes.HWND,wintypes.UINT],wintypes.HWND),
            'MonitorFromWindow':([wintypes.HWND,wintypes.DWORD],wintypes.HANDLE),
            'GetMonitorInfoW':([wintypes.HANDLE,ctypes.POINTER(MonitorInfo)],wintypes.BOOL),
            'GetDpiForWindow':([wintypes.HWND],wintypes.UINT),
            'GetWindowThreadProcessId':([wintypes.HWND,ctypes.POINTER(wintypes.DWORD)],wintypes.DWORD),
            'GetClientRect':([wintypes.HWND,ctypes.POINTER(wintypes.RECT)],wintypes.BOOL),
            'GetWindowRect':([wintypes.HWND,ctypes.POINTER(wintypes.RECT)],wintypes.BOOL),
            'ClientToScreen':([wintypes.HWND,ctypes.POINTER(wintypes.POINT)],wintypes.BOOL),
            'GetClassNameW':([wintypes.HWND,wintypes.LPWSTR,ctypes.c_int],ctypes.c_int)}
        for name,(arguments,result) in specifications.items():
            function=getattr(self.user,name);function.argtypes=arguments;function.restype=result
        self.callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
        self.user.EnumWindows.argtypes=[self.callback_type,wintypes.LPARAM];self.user.EnumWindows.restype=wintypes.BOOL
        self.dwm.DwmGetWindowAttribute.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
        self.dwm.DwmGetWindowAttribute.restype=ctypes.c_long

    def info(self,hwnd):
        if not hwnd or not self.user.IsWindow(hwnd):return None
        pid=wintypes.DWORD()
        if not self.user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid)) or not pid.value:return None
        client,outer=wintypes.RECT(),wintypes.RECT()
        if not self.user.GetClientRect(hwnd,ctypes.byref(client)) or not self.user.GetWindowRect(hwnd,ctypes.byref(outer)):return None
        origin=wintypes.POINT(client.left,client.top)
        if not self.user.ClientToScreen(hwnd,ctypes.byref(origin)):return None
        owner=self.user.GetAncestor(hwnd,3)
        if not owner:return None
        cloaked=wintypes.DWORD()
        if self.dwm.DwmGetWindowAttribute(hwnd,14,ctypes.byref(cloaked),ctypes.sizeof(cloaked))!=0:return None
        classname=ctypes.create_unicode_buffer(128)
        self.user.GetClassNameW(hwnd,classname,len(classname))
        monitor=self.user.MonitorFromWindow(hwnd,0)
        details=MonitorInfo();details.size=ctypes.sizeof(details)
        dpi=self.user.GetDpiForWindow(hwnd)
        if not monitor or not dpi or not self.user.GetMonitorInfoW(monitor,ctypes.byref(details)):return None
        bounds=details.monitor
        return WindowInfo(int(hwnd),int(pid.value),int(owner),
                          (origin.x,origin.y,origin.x+client.right-client.left,origin.y+client.bottom-client.top),
                          (outer.left,outer.top,outer.right,outer.bottom),bool(self.user.IsWindowVisible(hwnd)),
                          bool(self.user.IsIconic(hwnd)),bool(cloaked.value),
                          classname.value in ('Progman','WorkerW','Shell_TrayWnd','Shell_SecondaryTrayWnd'),
                          int(monitor),int(dpi),(bounds.left,bounds.top,bounds.right,bounds.bottom))

    def enumerate(self):
        windows=[];errors=[]
        def visit(hwnd,_):
            try:
                info=self.info(hwnd)
                if info is not None:windows.append(info)
            except Exception as error:errors.append(error);return False
            return True
        callback=self.callback_type(visit)
        if not self.user.EnumWindows(callback,0) or errors:raise OSError('無法確認框選視窗。')
        return windows

    def foreground(self):return self.info(self.user.GetForegroundWindow())


class WindowFocus:
    def __init__(self,api=None):
        from PySide6.QtGui import QGuiApplication
        self.enabled=api is not None or (sys.platform=='win32' and QGuiApplication.platformName()=='windows')
        self.api=api if api is not None else NativeWindows() if self.enabled else None

    def bind(self,region):
        if not self.enabled:return None
        try:return choose_binding(self.api.enumerate(),region,os.getpid())
        except OSError:return None

    def state(self,binding):
        try:return evaluate(binding,self.api.info(binding.hwnd),self.api.foreground())
        except OSError:return FocusState.INVALID

    def relocated(self,binding,region):
        try:return rebase_region(binding,self.api.info(binding.hwnd),region)
        except OSError:return None


class FocusGuard:
    """A witnessed loss stays latched until a NEW generation gets a new guard."""
    def __init__(self,focus,binding):
        self.focus,self.binding=focus,binding
        self.interrupted=threading.Event()

    def __call__(self):
        if self.interrupted.is_set():return False
        if self.focus.state(self.binding)!=FocusState.ACTIVE:
            self.interrupted.set();return False
        return not self.interrupted.is_set()


class FocusCancellation(Cancellation):
    def __init__(self,guard):
        super().__init__();self.focus_guard=guard

    def check(self):
        super().check()
        if not self.focus_guard():
            self.cancel();raise Cancelled('框選視窗已離開前景。')
