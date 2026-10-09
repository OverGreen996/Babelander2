"""Reproducible whole-application acceptance suite. No desktop capture/focus control."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,sys,time
from datetime import datetime,timezone
from babelander import __version__
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--phase',choices=('all','units','live','package','soak'),default='all');parser.add_argument('--cloud',action='store_true',help='Run six real paid/provider API requests using existing credentials');parser.add_argument('--seconds',type=int,default=600);args=parser.parse_args()
tag='a'+__version__.split('a')[-1];out=ROOT/'test-results'/('supertest-'+tag);out.mkdir(parents=True,exist_ok=True)
env=os.environ.copy();env.update(PYTHONIOENCODING='utf-8',QT_QPA_PLATFORM='offscreen')
source={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}
(ROOT/'test-results'/('frozen-source-'+tag+'.json')).write_text(json.dumps(source,indent=2),encoding='utf8')
manifest='frozen-motion-'+tag+'.json';(ROOT/'test-results'/manifest).write_text(json.dumps({k:v for k,v in source.items() if k.endswith('.py')},indent=2),encoding='utf8')
records=[]
def run(name,command,timeout=1200):
    print('START '+name,flush=True);start=time.monotonic();start_epoch=time.time()
    with (out/(name+'.log')).open('w',encoding='utf8') as log:
        result=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,creationflags=subprocess.CREATE_NO_WINDOW)
    text=(out/(name+'.log')).read_text(encoding='utf8',errors='replace');count=re.search(r'Ran (\d+) tests?',text)
    row={'name':name,'started_epoch':start_epoch,'returncode':result.returncode,'elapsed_seconds':round(time.monotonic()-start,2),'tests_run':int(count[1]) if count else None}
    records.append(row);save();print(json.dumps(row),flush=True)
    return result.returncode

def save():
    value={'version':__version__,'started_utc':started,'phase':args.phase,'real_desktop_capture':False,'foreground_control_calls':0,'cloud_opt_in':args.cloud,'application_sha256':source,'runs':records,'source_unchanged':source=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}}
    (out/('runner-'+args.phase+'.json')).write_text(json.dumps(value,indent=2),encoding='utf8')
    if args.phase=='all':
        for phase in ('units','live','package','soak'):
            subset=[r for r in records if (r['name'].startswith('verify') if phase=='units' else r['name'] in ('build','wheel-build','exe','wheel') if phase=='package' else r['name']=='soak' if phase=='soak' else not r['name'].startswith('verify') and r['name'] not in ('build','wheel-build','exe','wheel','soak'))]
            if subset:(out/('runner-'+phase+'.json')).write_text(json.dumps({**value,'phase':phase,'runs':subset},indent=2),encoding='utf8')
started=datetime.now(timezone.utc).isoformat()
if args.phase in ('all','units'):
    for name in ('verify','verify_assets','verify_pipeline','verify_layout','verify_equipment','verify_subtitle_trigger','verify_replay','verify_equipment_recovery','verify_window_focus','verify_preload','verify_quest','verify_chat','verify_chat_ocr','verify_super_regressions'):
        run(name,[sys.executable,name+'.py'])
if args.phase in ('all','live'):
    stages=[('quality',['supertest_quality.py','--out',str(out/'quality.json')]),('modes',['supertest_modes.py','--out',str(out/'modes')]),('equipment',['probe_equipment_matrix.py','--name','supertest-'+tag+'/equipment','--suite','game_structures','--passes','2']),('quest',['probe_quest_matrix.py','--name','supertest-'+tag+'/quest','--suite','game_structures','--passes','2','--strict']),('chat',['probe_chat.py','--name','supertest-'+tag+'/chat']),('chat-events',['probe_chat_events.py','--out',str(out/'chat-events')]),('motion',['probe_moving_background.py','--output','supertest-'+tag+'-motion','--manifest',manifest,'--moving-only','--adaptive-ocr-recheck','--reuse-dialogue-lines']),('model-lifecycle',['probe_model_lifecycle.py']),('preload-cancel',['probe_preload_cancel.py']),('native-focus',['probe_window_focus_native.py'])]
    if args.cloud:stages.append(('cloud',['supertest_cloud.py','--out',str(out/'cloud.json')]))
    for name,cmd in stages:
        run(name,[sys.executable,*cmd])
        legacy={'model-lifecycle':'model-lifecycle.json','preload-cancel':'preload-cancel-real-a17.json','native-focus':'window-focus-native-a15.json'}
        if name in legacy:
            import shutil
            shutil.copy2(ROOT/'test-results'/legacy[name],out/(name+'.json'))
if args.phase in ('all','package'):
    run('build',['pwsh','-NoProfile','-ExecutionPolicy','Bypass','-File','build.ps1'],300)
    run('wheel-build',[sys.executable,'-m','pip','wheel','.','--no-deps','--no-build-isolation','--wheel-dir','dist'],120)
    assets=ROOT.parent/'recovery/test-assets';env.update(BABELANDER_V2_MODEL=str(next((assets/'models').glob('*.gguf'))),BABELANDER_V2_SERVER=str(assets/'runtime/llama-server.exe'))
    run('exe',[str(ROOT/'dist/releases'/__version__/'Babelander2/Babelander2.exe'),'--self-test','--report',str(out/'exe.json')],120)
    run('wheel',[sys.executable,'probe_wheel.py'],150)
    import shutil
    for name in ('wheel.json','wheel-selftest.json'):shutil.copy2(ROOT/'test-results'/name,out/name)
if args.phase in ('all','soak'):run('soak',[sys.executable,'supertest_soak.py','--out',str(out),'--seconds',str(args.seconds)],args.seconds+180)
save();print(json.dumps({'phase':args.phase,'process_checks_passed':all(r['returncode']==0 for r in records),'tests_run':sum(r['tests_run'] or 0 for r in records),'report':str(out)}),flush=True)
if args.phase=='all':
    subprocess.run([sys.executable,'supertest_report.py',*(['--require-cloud'] if args.cloud else [])],cwd=ROOT,env=env,check=True)
    acceptance=json.loads((out/'summary.json').read_text(encoding='utf8'))
    # Exit 2 means the suite ran, but acceptance (including 700ms) failed.
    raise SystemExit(0 if acceptance['all_acceptance_passed'] else 2)
raise SystemExit(any(r['returncode'] for r in records))
