"""Six tiny authorized real API requests, no credential copying or logging."""
from bootstrap import prepare
prepare()
from pathlib import Path
import os,json,tempfile,time
from dataclasses import asdict
from babelander.settings import Settings,data_root
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.types import Mode,Cancellation
from probe_cloud import ReadOnlyExistingVault,OLD
import argparse
from babelander import __version__
parser=argparse.ArgumentParser();parser.add_argument('--out',default='test-results/supertest-a'+__version__.split('a')[-1]+'/cloud.json');args=parser.parse_args()
OUT=Path(args.out);OUT.parent.mkdir(parents=True,exist_ok=True)
modern=KeyVault(data_root())
class ExistingVault:
    def has(self,provider):return modern.has(provider) or (OLD/(provider+'-key.dpapi')).is_file()
    def get(self,provider):return modern.get(provider) if modern.has(provider) else ReadOnlyExistingVault().get(provider)
vault=ExistingVault();settings=Settings(hotkeys={});config=data_root()/'settings.json'
if config.is_file():
    values=json.loads(config.read_text(encoding='utf-8-sig'));settings.azure_region=values.get('azure_region','');settings.deepl_free=values.get('deepl_free',True)
elif (OLD/'settings.json').is_file():
    values=json.loads((OLD/'settings.json').read_text(encoding='utf-8-sig'));settings.azure_region=values.get('azure_options',{}).get('region','');settings.deepl_free=values.get('deepl_options',{}).get('endpoint','auto')!='https://api.deepl.com'
if not modern.has('azure') and (OLD/'settings.json').is_file():
    legacy=json.loads((OLD/'settings.json').read_text(encoding='utf-8-sig'));settings.azure_region=legacy.get('azure_options',{}).get('region','')
report={'version':__version__,'live_api':True,'credential_values_exported':False,'original_data_modified':False,'results':[],'missing_credentials':[],'requests_attempted':0,'network_provider_calls_attempted':0,'raw_synthetic_outputs':[]}
with tempfile.TemporaryDirectory(prefix='Babelander-super-cloud-') as directory:
    store=Store(directory);engine=Engine(settings,store,vault,directory)
    original=engine.cloud.translate
    def audited(provider,text,reply=False):
        report['network_provider_calls_attempted']+=1
        output=original(provider,text,reply);report['raw_synthetic_outputs'].append({'provider':provider,'source':text,'target':output});return output
    engine.cloud.translate=audited
    try:
        for provider in ('google','azure','deepl'):
            if not vault.has(provider):report['missing_credentials'].append(provider);continue
            for mode,text in ((Mode.DIALOG,'Do not cross the river until I return.'),(Mode.REPLY,'請等我6分鐘，不要開始。')):
                settings.providers[mode.value]=provider;at=time.perf_counter();report['requests_attempted']+=1
                try:
                    t=engine.request(text,mode,Cancellation());before=store.usage();again=engine.request(text,mode,Cancellation()) if not t.warning else None
                    report['results'].append({'provider':provider,'mode':mode.value,**asdict(t),'request_ms':round((time.perf_counter()-at)*1000,2),
                                              'cache_did_not_bill_again':bool(again and again.cache_hit and store.usage()==before),'passed':not t.warning and bool(t.target)})
                except Exception as error:
                    # Never include HTTP exception URLs/headers containing keys.
                    import re
                    code=re.search(r'\bHTTP (\d{3})',str(error))
                    report['results'].append({'provider':provider,'mode':mode.value,'passed':False,'error_type':type(error).__name__,'http_status':int(code[1]) if code else None})
        report['usage']=store.usage()
    finally:engine.close();engine.join();store.close()
report['available_api_passed']=bool(report['results']) and all(row['passed'] and row.get('cache_did_not_bill_again') for row in report['results'])
report['all_three_apis_verified']=len(report['results'])==len(report['raw_synthetic_outputs'])==report['network_provider_calls_attempted']==6 and report['available_api_passed'] and all(row.get('backend_state')=='cloud' for row in report['results'])
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:report[k] for k in ('requests_attempted','missing_credentials','available_api_passed','all_three_apis_verified')},ensure_ascii=True))
raise SystemExit(not report['all_three_apis_verified'])
