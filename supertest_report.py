"""Read substantive acceptance checks, not merely successful process exits."""
from pathlib import Path
import argparse,json,hashlib,statistics
from datetime import datetime
import numpy as np
from babelander import __version__
ROOT=Path(__file__).resolve().parent;tag='a'+__version__.split('a')[-1];out=ROOT/'test-results'/('supertest-'+tag)
parser=argparse.ArgumentParser();parser.add_argument('--require-cloud',action='store_true');args=parser.parse_args()
missing=[]
def read(relative):
    p=ROOT/'test-results'/relative
    if not p.is_file():missing.append(relative);return {}
    return json.loads(p.read_text(encoding='utf8'))
base='supertest-'+tag+'/'
units=read(base+'runner-units.json');modes=read(base+'modes/report.json');equipment=read(base+'equipment/report.json');quest=read(base+'quest/report.json');chat=read(base+'chat/report.json');events=read(base+'chat-events/report.json');motion=read('supertest-'+tag+'-motion/results.json');soak=read(base+'soak.json');resources=read(base+'resources.json');exe=read(base+'exe.json');wheel=read(base+'wheel.json');quality=read(base+'quality.json')
runners={name:read(base+'runner-'+name+'.json') for name in ('live','package','soak')}
life={name:read(base+name+'.json') for name in ('model-lifecycle','preload-cancel','native-focus')}
cloud=read(base+'cloud.json') if args.require_cloud or runners['live'].get('cloud_opt_in',False) else None
frozen=read('frozen-source-'+tag+'.json');actual={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}
checks={'snapshot_matches_live_source':bool(frozen) and frozen==actual,
'regressions':len(units.get('runs',[]))==14 and all(r['returncode']==0 for r in units.get('runs',[])) and units.get('application_sha256')==frozen,
'six_modes_and_crash_recovery':modes.get('functional_passed',False) and modes.get('application_sha256')==frozen,
'equipment':len(equipment.get('runs',[]))==40 and all(r.get('usable') and r.get('single_capture_ocr') for r in equipment.get('runs',[])) and equipment.get('application_source_unchanged',False),
'quest':quest.get('passed',False) and len(quest.get('runs',[]))==32,
'chat':chat.get('completed',False) and chat.get('source_sha256')==frozen and len(chat.get('live_results',[]))==100 and not chat.get('errors') and chat.get('workers_stopped') and chat.get('owned_model_stopped') and chat.get('live_summary',{}).get('no_warning')==100 and not chat.get('live_summary',{}).get('missing_message_indices') and not chat.get('live_summary',{}).get('duplicated_message_indices'),
'chat_privacy':chat.get('sqlite_rows')=={'cache':0,'history':0,'usage':0},'chat_duplicate_and_burst':events.get('passed',False),
'moving_background_lifecycle':motion.get('completed',False) and motion.get('owned_model_stopped',False) and motion.get('workers_stopped',False) and motion.get('source_unchanged',False),
'exe_selftest':exe.get('passed',False) and exe.get('version')==__version__ and exe.get('frozen',False),
'isolated_wheel':wheel.get('passed',False) and wheel.get('selftest',{}).get('version')==__version__ and all(wheel.get('wheel_source_matches',{}).values()),
'exe_longevity':soak.get('passed',False) and soak.get('version')==__version__ and soak.get('duration_seconds',0)>=600 and resources.get('passed',False),
**{name:value.get('passed',False) for name,value in life.items()}}
if cloud is not None:checks['three_real_apis']=cloud.get('all_three_apis_verified',False)
expected={'live':{'modes':'modes/report.json','equipment':'equipment/report.json','quest':'quest/report.json','chat':'chat/report.json','chat-events':'chat-events/report.json','motion':'../supertest-'+tag+'-motion/results.json','model-lifecycle':'model-lifecycle.json','preload-cancel':'preload-cancel.json','native-focus':'native-focus.json'},'package':{'exe':'exe.json','wheel':'wheel.json'},'soak':{'soak':'soak.json'}}
if cloud is not None:expected['live']['cloud']='cloud.json'
fresh=True
for phase,files in expected.items():
    runner=runners[phase];records={r['name']:r for r in runner.get('runs',[])}
    start=datetime.fromisoformat(runner['started_utc']).timestamp() if runner.get('started_utc') else float('inf')
    fresh=fresh and runner.get('application_sha256')==frozen and runner.get('source_unchanged',False) and all(r['returncode']==0 for r in records.values())
    for name,file in files.items():
        record=records.get(name,{});p=out/file
        fresh=fresh and record.get('returncode')==0 and p.is_file() and p.stat().st_mtime>=record.get('started_epoch',start)
checks['fresh_runtime_evidence']=fresh

phase=motion.get('phases',{}).get('moving_noise',{});ms=phase.get('summary',{})
checks['moving_background_usable_subtitles']=ms.get('sentences_presented')==100 and ms.get('usable_display_within_3_seconds')==100
live=chat.get('live_results',[]);latencies=[r['fixture_shown_to_qt_ms'] for r in live if r.get('target') and not r.get('warning') and r.get('fixture_shown_to_qt_ms') is not None]
chat_speed={'successful_full_outputs':len(latencies),'within_700ms':sum(x<=700 for x in latencies),'mean_ms':round(statistics.mean(latencies),2) if latencies else None,'p95_ms':round(float(np.percentile(latencies,95)),2) if latencies else None}
critical=modes.get('quality_marker_passed',False) and quality.get('all_critical_markers_passed',False)
modelgpu=[g for s in resources.get('samples',[]) for g in s.get('gpu',[]) if g.get('role')=='model' and g.get('dedicated_mib') is not None]
warm=[s for s in soak.get('samples',[]) if s.get('elapsed',0)>=120]
ram={'app_warm_private_min_mib':min((s['private_mb'] for s in warm),default=None),'app_warm_private_max_mib':max((s['private_mb'] for s in warm),default=None),
'drift_checks':resources.get('resource_acceptance'),
'model_private_max_mib':max([s['model']['private_mb'] for s in soak.get('samples',[]) if s.get('model') and 'private_mb' in s['model']]+[s['model']['private_mib'] for s in resources.get('samples',[]) if s.get('model')],default=None),
'app_warm_working_min_mib':min((s['rss_mb'] for s in warm),default=None),'app_warm_working_max_mib':max((s['rss_mb'] for s in warm),default=None),
'model_working_max_mib':max([s['model']['rss_mb'] for s in soak.get('samples',[]) if s.get('model') and 'rss_mb' in s['model']]+[s['model']['working_mib'] for s in resources.get('samples',[]) if s.get('model')],default=None),'model_wddm_dedicated_max_mib':max((s['dedicated_mib'] for s in modelgpu),default=None),'model_wddm_shared_max_mib':max((s.get('shared_mib') or 0 for s in modelgpu),default=None),'measurement':'Owned process RAM; WDDM allocated memory. N/A if counters unavailable; no power/FPS attribution.'}
result={'version':__version__,'functional_checks':checks,'functional_passed':not missing and all(checks.values()),'missing_reports':missing,'regression_count':sum(r.get('tests_run') or 0 for r in units.get('runs',[])),
'critical_marker_checks_passed':critical,'semantic_accuracy_scored':False,'novel_quality_markers':{'passed':quality.get('marker_passed_count'),'cases':len(quality.get('cases',[]))},
'latency_target_ms':700,'speed_passed':len(latencies)==100 and all(x<=700 for x in latencies) and ms.get('usable_display_within_700_ms')==100,
'chat_speed':chat_speed,'chat':chat.get('live_summary'),'equipment':equipment.get('summary'),'quest':quest.get('summary'),'moving_background':ms,'resources':ram,'soak':{'duration_seconds':soak.get('duration_seconds'),'changes':soak.get('changes'),'results':len(soak.get('results',[])),'checks':soak.get('checks')},
'cloud':{k:cloud.get(k) for k in ('requests_attempted','available_api_passed','all_three_apis_verified')} if cloud else 'Not requested',
'actual_exe_checks':len(exe.get('checks',{})),'actual_wheel_checks':len(wheel.get('selftest',{}).get('checks',{})),
'exe_sha256':soak.get('exe_sha256'),'application_sha256':frozen,'real_game_validated':False,'real_desktop_capture':False,'foreground_control_calls':0}
result['all_acceptance_passed']=result['functional_passed'] and critical and result['speed_passed']
(out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:result[k] for k in ('functional_passed','critical_marker_checks_passed','speed_passed','all_acceptance_passed','missing_reports','regression_count','chat_speed','novel_quality_markers','resources')},ensure_ascii=True,indent=2))
