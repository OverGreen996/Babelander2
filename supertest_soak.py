"""Hidden packaged EXE longevity test with strictly owned-process resource samples."""
from pathlib import Path
import argparse,json,os,subprocess,time,hashlib
from replay_resources import process
from babelander import __version__
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--out',required=True);parser.add_argument('--seconds',type=int,default=600);args=parser.parse_args()
dest=Path(args.out).resolve();dest.mkdir(parents=True,exist_ok=True)
exe=ROOT/'dist/releases'/__version__/'Babelander2/Babelander2.exe'
assets=ROOT.parent/'recovery/test-assets';env=os.environ.copy();env.update(QT_QPA_PLATFORM='offscreen',BABELANDER_V2_MODEL=str(next((assets/'models').glob('*.gguf'))),BABELANDER_V2_SERVER=str(assets/'runtime/llama-server.exe'))
reportfile=dest/'soak.json';progress=reportfile.with_suffix('.progress.jsonl')
# Fresh progress only; never touch prior release evidence.
progress.write_text('',encoding='utf8')
child=subprocess.Popen([str(exe),'--soak-test','--offscreen-fixture','--seconds',str(args.seconds),'--report',str(reportfile)],env=env,creationflags=subprocess.CREATE_NO_WINDOW)
start=time.monotonic();samples=[];next_gpu=0;model_pid=None
try:
    while child.poll() is None:
        elapsed=time.monotonic()-start
        if elapsed>args.seconds+120:raise TimeoutError('Owned EXE soak deadline')
        if progress.exists():
            for line in progress.read_text(encoding='utf8').splitlines():
                try:
                    value=json.loads(line)
                    if value.get('model') and value['model'].get('pid'):model_pid=value['model']['pid']
                except (ValueError,KeyError):pass
        sample={'elapsed':round(elapsed,2),'app':process(child.pid),'model':process(model_pid) if model_pid else None,'gpu':[]}
        if elapsed>=next_gpu and model_pid:
            next_gpu=elapsed+60
            for pid in (child.pid,model_pid):
                command="Get-CimInstance -ClassName Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory | Where-Object { $_.Name -like 'pid_"+str(int(pid))+"_*' } | Select-Object Name,DedicatedUsage,SharedUsage | ConvertTo-Json -Compress"
                try:
                    q=subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,text=True,timeout=8,creationflags=subprocess.CREATE_NO_WINDOW)
                    data=json.loads(q.stdout) if q.returncode==0 and q.stdout.strip() else None
                    rows=data if isinstance(data,list) else [data] if data else []
                    sample['gpu'].append({'pid':pid,'role':'app' if pid==child.pid else 'model','dedicated_mib':round(sum(int(r['DedicatedUsage']) for r in rows)/1048576,2) if rows else None,'shared_mib':round(sum(int(r['SharedUsage']) for r in rows)/1048576,2) if rows else None})
                except Exception as error:sample['gpu'].append({'pid':pid,'error_type':type(error).__name__})
        samples.append(sample);(dest/'resource-progress.json').write_text(json.dumps(samples,indent=2),encoding='utf8')
        if len(samples)%4==0:print(json.dumps({'soak_elapsed_seconds':round(elapsed),'owned_exe_alive':True,'samples':len(samples)}),flush=True)
        time.sleep(15)
finally:
    if child.poll() is None:child.terminate();child.wait(10)
resource={'version':__version__,'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'exit_code':child.returncode,'scope':'Owned EXE and its reported model PID only; WDDM counters are allocated dedicated/shared memory, not game FPS or power. Missing counters are N/A.','samples':samples}
resource['passed']=child.returncode==0 and reportfile.is_file() and json.loads(reportfile.read_text(encoding='utf8')).get('passed',False)
from supertest_resource_acceptance import evaluate
resource['resource_acceptance']=evaluate(resource);resource['passed']=resource['passed'] and resource['resource_acceptance']['passed']
(dest/'resources.json').write_text(json.dumps(resource,indent=2),encoding='utf8')
print(json.dumps({'exe_soak_passed':resource['passed'],'exit_code':child.returncode}),flush=True)
raise SystemExit(not resource['passed'])
