"""Seal local OCR evidence after benchmark, regressions and package checks."""
import json,hashlib,types
from pathlib import Path
from PyInstaller.archive.readers import ZlibArchiveReader
from babelander import __version__

ROOT=Path(__file__).resolve().parent
def read(path):return json.loads((ROOT/path).read_text(encoding='utf8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
source={p.name:digest(p) for p in (ROOT/'babelander').glob('*') if p.suffix in ('.py','.qss')}
benchmark=read('test-results/ocr-chat-a24/report.json')
fixed=read('test-results/ocr-fixed-a24.json')
runner=read('test-results/a24-acceptance/runner.json')
clean=read('test-results/a24-acceptance/clean/0-100.json')
edges=read('test-results/a24-acceptance/ocr-edges.json')
flash=read('test-results/a24-acceptance/weak-flash.json')
events=read('test-results/a24-acceptance/chat-events/report.json')
modes=read('test-results/a24-acceptance/modes/report.json')
package=read('test-results/supertest-a24/runner-package.json')
exe=read('test-results/supertest-a24/exe.json')
wheel=read('test-results/supertest-a24/wheel.json')
assert benchmark['functional_passed'] and benchmark['speed_gate_passed'] and fixed['passed']
assert runner['passed'] and runner['source_sha256']==source and len(runner['stages'])==21
assert clean['passed'] and edges['passed'] and flash['recall_not_worse'] and events['passed']
assert modes['overall_passed'] and all(r['returncode']==0 for r in package['runs'])
assert exe['passed'] and wheel['passed'] and package['application_sha256']==source
tested=benchmark['runs'][1]['source_sha256']
assert all(r['source_sha256']==tested for r in benchmark['runs'])
assert all(source[k]==v for k,v in tested.items() if k!='__init__.py')
assert all(source[k]==v for k,v in fixed['source_sha256'].items() if k!='__init__.py')
assert set(source)==set(tested)

def canonical(value):
    if isinstance(value,types.CodeType):
        return (value.co_code,canonical(value.co_consts),value.co_names,value.co_varnames,value.co_freevars,
                value.co_cellvars,value.co_argcount,value.co_posonlyargcount,value.co_kwonlyargcount,value.co_flags,value.co_exceptiontable)
    if isinstance(value,tuple):return tuple(canonical(v) for v in value)
    return value
archive=ZlibArchiveReader(str(ROOT/'build/work/Babelander2/PYZ-00.pyz'))
modules={}
for path in (ROOT/'babelander').glob('*.py'):
    name='babelander' if path.stem=='__init__' else 'babelander.'+path.stem
    bundled=archive.extract(name)
    modules[name]=canonical(bundled)==canonical(compile(path.read_text(encoding='utf8'),bundled.co_filename,'exec',dont_inherit=True,optimize=0))
assert all(modules.values())
evidence_paths=['test-results/ocr-chat-a24/report.json','test-results/ocr-fixed-a24.json',
    'test-results/a24-acceptance/runner.json','test-results/a24-acceptance/ocr-edges.json',
    'test-results/a24-acceptance/weak-flash.json','test-results/a24-acceptance/modes/report.json',
    'test-results/supertest-a24/exe.json','test-results/supertest-a24/wheel.json']
summary={'version':__version__,'baseline_commit':benchmark['baseline_commit'],
    'scope':benchmark['scope'],'animation_abba':benchmark['summary'],
    'functional_passed':True,'speed_gate_passed':True,'identical_pixel_ocr_frames':fixed['frames'],
    'identical_pixel_all_texts_equal':fixed['all_texts_equal'],
    'live_ocr_literal_sources_equal':benchmark['same_source_messages'],
    'live_event_sequence_equal':benchmark['same_event_sequence'],
    'regression_groups':sum(r['name'].startswith('verify') for r in runner['stages']),
    'regression_tests':sum(r['tests_run'] or 0 for r in runner['stages']),
    'ocr_edge_checks':len(edges['checks']),'chat_event_checks':len(events['checks']),
    'mode_checks':len(modes['checks']),'exe_checks':len(exe['checks']),
    'wheel_checks':len(wheel['selftest']['checks']),
    'clean_complete_translation':{},'dim_flash_full_translation_ms':[v['events'][0]['shown_to_qt_ms'] for v in flash['runs']],
    'application_sha256':source,'benchmark_application_sha256':tested,
    'benchmark_version_stamp':'2.0.0a23; only __init__.py version stamp changed before alpha24 final regression/package validation.',
    'compiled_modules_match_source':modules,'evidence_sha256':{p:digest(ROOT/p) for p in evidence_paths},
    'exe_sha256':digest(ROOT/'dist/releases'/__version__/'Babelander2/Babelander2.exe'),
    'limitations':['Warm offscreen fixtures, not real-game display latency or FPS.',
        'Complete translation max increased; P95 improved but not all messages meet 700ms.',
        'App-process CPU per wall second increased as faster OCR permits more scans; no total resource reduction claim.',
        'No claim of universal semantic accuracy.']}
import numpy as np
values=[r['shown_to_qt_ms'] for r in clean['results']]
summary['clean_complete_translation']={'n':len(values),'mean_ms':float(np.mean(values)),
    'p95_ms':float(np.percentile(values,95)),'max_ms':max(values),'within700':sum(v<=700 for v in values)}
dest=ROOT/'assets/verification/ocr-chat-a24';dest.mkdir(parents=True,exist_ok=True)
(dest/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:summary[k] for k in ('version','functional_passed','speed_gate_passed','regression_tests','mode_checks','exe_checks','wheel_checks','clean_complete_translation')},ensure_ascii=False))
