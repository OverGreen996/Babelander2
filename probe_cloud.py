"""Small authorized live API probe. Old DPAPI secrets stay in memory only."""
from bootstrap import prepare
prepare()
from pathlib import Path
import ctypes
from ctypes import wintypes
import json
import os
import tempfile
import time
from dataclasses import asdict,replace

from babelander.security import Blob
from babelander.settings import Settings
from babelander.storage import Store
from babelander.engine import Engine
from babelander.types import Mode,Cancellation

OLD = Path(os.environ['LOCALAPPDATA'])/'Babelander/data'
OUT = Path(__file__).resolve().parent/'test-results/real-cloud.json'


class ReadOnlyExistingVault:
    def get(self,provider):
        data = (OLD/(provider+'-key.dpapi')).read_bytes()
        buffer = (ctypes.c_ubyte*len(data)).from_buffer_copy(data)
        incoming,outgoing = Blob(len(data),buffer),Blob()
        function = ctypes.windll.crypt32.CryptUnprotectData
        function.argtypes = [ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        function.restype = wintypes.BOOL
        if not function(ctypes.byref(incoming),None,None,None,None,1,ctypes.byref(outgoing)):
            raise ValueError('Existing credential unavailable')
        free = ctypes.windll.kernel32.LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        try:
            return ctypes.string_at(outgoing.data,outgoing.length).decode()
        finally:
            free(outgoing.data)


def main():
    old_settings = json.loads((OLD/'settings.json').read_text(encoding='utf-8-sig'))
    settings = Settings(azure_region=old_settings.get('azure_options',{}).get('region',''))
    settings.deepl_free = old_settings.get('deepl_options',{}).get('endpoint','auto') != 'https://api.deepl.com'
    rows = []
    with tempfile.TemporaryDirectory(prefix='Babelander2-api-') as directory:
        store = Store(directory)
        engine = Engine(settings,store,ReadOnlyExistingVault(),directory)
        try:
            for provider in ('google','azure','deepl'):
                for mode,text in ((Mode.DIALOG,'Alice, we must leave before sunset.'),
                                  (Mode.REPLY,'我五分鐘後回來，請不要開始。')):
                    settings.providers[mode.value] = provider
                    started = time.perf_counter()
                    try:
                        result = engine.request(text,mode,Cancellation())
                        before = store.usage()
                        settings=replace(settings,font_size=32 if settings.font_size==24 else 24,overlays={'dialog':{'x':80,'y':300,'width':700,'height':240,'background':False}})
                        engine.reconfigure(settings)
                        cached = engine.request(text,mode,Cancellation())
                        row = {'provider':provider,'mode':mode.value,**asdict(result),
                               'ms':round((time.perf_counter()-started)*1000,2),
                               'cache_without_extra_request':cached.cache_hit and before==store.usage(),
                               'passed':not result.warning}
                    except Exception as error:
                        row = {'provider':provider,'mode':mode.value,'passed':False,'error_type':type(error).__name__}
                    rows.append(row)
                    print(json.dumps(row,ensure_ascii=False),flush=True)
            usage = store.usage()
        finally:
            engine.close();engine.join();store.close()
    report = {'passed':all(r['passed'] and r.get('cache_without_extra_request') for r in rows),
              'requests':6,'input_chars_per_provider':len('Alice, we must leave before sunset.')+len('我五分鐘後回來，請不要開始。'),
              'current_validation_policy_passed':all(r['passed'] for r in rows),
              'credentials':'Existing DPAPI decrypted in process; never copied, saved or exported',
              'accounting':'Temporary V2 reserve/confirm ledger; original application ledger unchanged',
              'usage':usage,'results':rows,'note':'Two small synthetic requests per provider; repeat after font/overlay settings reconfiguration uses cache with no extra billable request; not a production performance benchmark'}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return not report['passed']


if __name__ == '__main__':
    raise SystemExit(main())
