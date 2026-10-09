"""Windows DPAPI secrets with provider-bound entropy; no plaintext key files."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import sys


class Blob(ctypes.Structure):
    _fields_ = [('length',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]


def crypt(data, provider, decrypt=False):
    if sys.platform != 'win32':
        raise RuntimeError('API 金鑰保護需要 Windows DPAPI。')
    crypto = ctypes.WinDLL('crypt32',use_last_error=True)
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = (ctypes.c_ubyte*len(data)).from_buffer_copy(data)
    entropy_data = ('Babelander2:'+provider).encode()
    entropy_buffer = (ctypes.c_ubyte*len(entropy_data)).from_buffer_copy(entropy_data)
    incoming = Blob(len(data),buffer)
    entropy = Blob(len(entropy_data),entropy_buffer)
    outgoing = Blob()
    function = crypto.CryptUnprotectData if decrypt else crypto.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.POINTER(Blob),ctypes.c_void_p,
                         ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(incoming),None,ctypes.byref(entropy),None,None,1,ctypes.byref(outgoing)):
        raise ValueError('API 金鑰無法解密或儲存；請重新輸入。')
    try:
        return ctypes.string_at(outgoing.data,outgoing.length)
    finally:
        kernel.LocalFree(outgoing.data)


class KeyVault:
    def __init__(self, root):
        self.root = Path(root)/'credentials'

    def path(self, provider):
        if provider not in ('google','azure','deepl'):
            raise ValueError('未知翻譯服務。')
        return self.root/(provider+'.dpapi')

    def put(self, provider, key):
        if not key.strip():
            raise ValueError('API 金鑰不能空白。')
        data = crypt(key.strip().encode(),provider)
        self.root.mkdir(parents=True,exist_ok=True)
        temporary = self.path(provider).with_suffix('.tmp')
        temporary.write_bytes(data)
        temporary.replace(self.path(provider))

    def get(self, provider):
        path = self.path(provider)
        if not path.exists():
            raise ValueError('尚未設定 '+provider+' API 金鑰。')
        return crypt(path.read_bytes(),provider,True).decode()

    def has(self, provider):
        return self.path(provider).exists()

    def delete(self, provider):
        self.path(provider).unlink(missing_ok=True)
