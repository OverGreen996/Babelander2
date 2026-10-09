"""Windows compatible-bitmap capture; all GDI objects have explicit lifetimes."""
import ctypes
from ctypes import wintypes as w
import numpy as np


class CaptureUnavailable(RuntimeError):
    """A transient desktop access/copy failure; never a backend/API failure."""


class Header(ctypes.Structure):
    _fields_ = [('size',w.DWORD),('width',w.LONG),('height',w.LONG),('planes',w.WORD),('bits',w.WORD),
                ('compression',w.DWORD),('image_size',w.DWORD),('x',w.LONG),('y',w.LONG),('used',w.DWORD),('important',w.DWORD)]


class Info(ctypes.Structure):
    _fields_ = [('header',Header),('colors',ctypes.c_byte*4)]


def capture(region):
    user = ctypes.WinDLL('user32',use_last_error=True)
    gdi = ctypes.WinDLL('gdi32',use_last_error=True)
    signatures = [
        (user,'GetDC',[w.HWND],w.HDC),(user,'ReleaseDC',[w.HWND,w.HDC],ctypes.c_int),
        (gdi,'CreateCompatibleDC',[w.HDC],w.HDC),
        (gdi,'CreateCompatibleBitmap',[w.HDC,ctypes.c_int,ctypes.c_int],w.HBITMAP),
        (gdi,'SelectObject',[w.HDC,w.HGDIOBJ],w.HGDIOBJ),
        (gdi,'BitBlt',[w.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.HDC,ctypes.c_int,ctypes.c_int,w.DWORD],w.BOOL),
        (gdi,'GetDIBits',[w.HDC,w.HBITMAP,w.UINT,w.UINT,ctypes.c_void_p,ctypes.POINTER(Info),w.UINT],ctypes.c_int),
        (gdi,'DeleteObject',[w.HGDIOBJ],w.BOOL),(gdi,'DeleteDC',[w.HDC],w.BOOL),
    ]
    for library,name,arguments,result in signatures:
        function = getattr(library,name)
        function.argtypes,function.restype = arguments,result
    source = user.GetDC(None)
    memory = bitmap = previous = None
    try:
        if not source:
            raise CaptureUnavailable('無法存取畫面，請解鎖桌面並重新框選。')
        memory = gdi.CreateCompatibleDC(source)
        bitmap = gdi.CreateCompatibleBitmap(source,region.width,region.height)
        if not memory or not bitmap:
            raise RuntimeError('畫面擷取資源配置失敗，請縮小框選。')
        previous = gdi.SelectObject(memory,bitmap)
        copied = gdi.BitBlt(memory,0,0,region.width,region.height,source,region.x,region.y,0x00CC0020|0x40000000)
        if not copied:
            copied = gdi.BitBlt(memory,0,0,region.width,region.height,source,region.x,region.y,0x00CC0020)
        if not copied:
            raise CaptureUnavailable('無法擷取這個畫面；請使用視窗／無邊框模式並確認桌面已解鎖。')
        # GetDIBits requires that the bitmap be deselected before reading.
        gdi.SelectObject(memory,previous)
        previous = None
        info = Info()
        info.header = Header(ctypes.sizeof(Header),region.width,-region.height,1,32,0,0,0,0,0,0)
        buffer = (ctypes.c_ubyte*(region.width*region.height*4))()
        if gdi.GetDIBits(memory,bitmap,0,region.height,buffer,ctypes.byref(info),0) != region.height:
            raise CaptureUnavailable('畫面像素讀取失敗，請重新框選。')
        return np.frombuffer(buffer,dtype=np.uint8).reshape(region.height,region.width,4)[:,:,:3].copy()
    finally:
        if previous and memory:gdi.SelectObject(memory,previous)
        if bitmap:gdi.DeleteObject(bitmap)
        if memory:gdi.DeleteDC(memory)
        if source:user.ReleaseDC(None,source)
