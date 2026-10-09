"""Explicit Windows integration: capture exclusion, screen coordinates, hotkeys."""
import ctypes
from ctypes import wintypes
import sys

from PySide6.QtCore import QObject, Signal, QAbstractNativeEventFilter
from PySide6.QtGui import QGuiApplication


def dpi_aware():
    if sys.platform == 'win32':
        function = ctypes.windll.user32.SetProcessDpiAwarenessContext
        function.argtypes = [ctypes.c_void_p]
        function.restype = wintypes.BOOL
        function(ctypes.c_void_p(-4))


def exclude_capture(widget):
    if sys.platform != 'win32':
        return False
    function = ctypes.windll.user32.SetWindowDisplayAffinity
    function.argtypes = [wintypes.HWND,wintypes.DWORD]
    function.restype = wintypes.BOOL
    return bool(function(int(widget.winId()),0x11))


def monitor_rectangles():
    class Info(ctypes.Structure):
        _fields_ = [('size',wintypes.DWORD),('monitor',wintypes.RECT),('work',wintypes.RECT),
                    ('flags',wintypes.DWORD),('device',wintypes.WCHAR*32)]
    rectangles = {}
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HANDLE,wintypes.HDC,ctypes.POINTER(wintypes.RECT),wintypes.LPARAM)
    def visit(handle,dc,rectangle,parameter):
        info = Info()
        info.size = ctypes.sizeof(info)
        get_info = ctypes.windll.user32.GetMonitorInfoW
        get_info.argtypes = [wintypes.HANDLE,ctypes.POINTER(Info)]
        get_info.restype = wintypes.BOOL
        if get_info(handle,ctypes.byref(info)):
            rectangles[info.device] = (info.monitor.left,info.monitor.top,info.monitor.right,info.monitor.bottom)
        return True
    callback = callback_type(visit)
    function = ctypes.windll.user32.EnumDisplayMonitors
    function.argtypes = [wintypes.HDC,ctypes.POINTER(wintypes.RECT),callback_type,wintypes.LPARAM]
    function(None,None,callback,0)
    return rectangles


def physical_region(screen, rectangle):
    from .types import Region
    geometry = screen.geometry()
    native = monitor_rectangles().get(screen.name()) if sys.platform == 'win32' else None
    ratio = screen.devicePixelRatio()
    # Qt on Windows scales the screen's size, but retains its native origin.
    # Multiplying that origin again breaks monitors at 150%/200% scale.
    origin_x,origin_y = native[:2] if native else (geometry.x(),geometry.y())
    return Region(origin_x+round(rectangle.x()*ratio),origin_y+round(rectangle.y()*ratio),
                  round(rectangle.width()*ratio),round(rectangle.height()*ratio))


def logical_region(region):
    from PySide6.QtCore import QRect
    native_rectangles=monitor_rectangles() if sys.platform=='win32' and QGuiApplication.platformName()=='windows' else {}
    for screen in QGuiApplication.screens():
        geometry=screen.geometry();ratio=screen.devicePixelRatio()
        native=native_rectangles.get(screen.name(),(geometry.x(),geometry.y(),
            geometry.x()+round(geometry.width()*ratio),geometry.y()+round(geometry.height()*ratio)))
        if (native[0]<=region.x and region.x+region.width<=native[2] and
            native[1]<=region.y and region.y+region.height<=native[3]):
            rectangle=QRect(geometry.x()+round((region.x-native[0])/ratio),
                geometry.y()+round((region.y-native[1])/ratio),max(1,round(region.width/ratio)),max(1,round(region.height/ratio)))
            return screen,rectangle
    raise ValueError('框選卡片區域不在目前螢幕上，請重新框選。')


def place_physical(widget,region):
    if sys.platform!='win32' or QGuiApplication.platformName()!='windows':return
    function=ctypes.windll.user32.SetWindowPos
    function.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
    function.restype=wintypes.BOOL
    if not function(int(widget.winId()),wintypes.HWND(-1),region.x,region.y,region.width,region.height,0x0010):
        raise OSError('卡片覆蓋視窗無法對齊框選區域。')
    rectangle=wintypes.RECT()
    read=ctypes.windll.user32.GetWindowRect
    read.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    read.restype=wintypes.BOOL
    if not read(int(widget.winId()),ctypes.byref(rectangle)) or (
        rectangle.left,rectangle.top,rectangle.right-rectangle.left,rectangle.bottom-rectangle.top
    )!=(region.x,region.y,region.width,region.height):
        raise OSError('卡片覆蓋的實際位置與框選不一致，請重新框選。')


def shortcut(text):
    parts = text.replace('Control','Ctrl').split('+')
    modifiers = 0x4000
    flags = {'Ctrl':2,'Alt':1,'Shift':4,'Meta':8}
    for part in parts[:-1]:
        if part not in flags:
            raise ValueError('不支援的快捷鍵修飾符。')
        modifiers |= flags[part]
    key = parts[-1].upper()
    if key.startswith('F') and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        virtual_key = 0x70+int(key[1:])-1
    elif len(key)==1 and key.isascii() and key.isalnum():
        virtual_key = ord(key)
    else:
        raise ValueError('請使用字母、數字或 F1–F24。')
    return modifiers,virtual_key


class NativeFilter(QAbstractNativeEventFilter):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def nativeEventFilter(self, event_type, message):
        if sys.platform == 'win32':
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x312 and int(msg.wParam) in self.owner.actions:
                self.owner.triggered.emit(self.owner.actions[int(msg.wParam)])
                return True,0
        return False,0


class Hotkeys(QObject):
    triggered = Signal(str)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.actions = {}
        self.filter = NativeFilter(self)
        app.installNativeEventFilter(self.filter)

    def configure(self, assignments):
        self.unregister()
        errors = []
        if sys.platform != 'win32':
            return ['全域快捷鍵只支援 Windows。']
        for number,(action,text) in enumerate(assignments.items(),0xB200):
            if not text:
                continue
            try:
                modifiers,key = shortcut(text)
                if ctypes.windll.user32.RegisterHotKey(None,number,modifiers,key):
                    self.actions[number] = action
                else:
                    errors.append(text+' 已被其他程式占用；可改用按鈕。')
            except ValueError as error:
                errors.append(text+'：'+str(error))
        return errors

    def unregister(self):
        if sys.platform == 'win32':
            for number in self.actions:
                ctypes.windll.user32.UnregisterHotKey(None,number)
        self.actions.clear()

    def close(self):
        self.unregister()
        self.app.removeNativeEventFilter(self.filter)
