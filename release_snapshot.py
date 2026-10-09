"""Verify the executable's application modules match source and preserve it."""
from pathlib import Path
import hashlib
import importlib.metadata as metadata
import json
import shutil
import types
import zipfile
from PyInstaller.archive.readers import ZlibArchiveReader
from babelander import __version__

ROOT = Path(__file__).resolve().parent
DIST = ROOT/'dist'
BUNDLE = DIST/'releases'/__version__/'Babelander2'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    if isinstance(value,types.CodeType):
        return (value.co_code,canonical(value.co_consts),value.co_names,value.co_varnames,value.co_freevars,value.co_cellvars,
                value.co_argcount,value.co_posonlyargcount,value.co_kwonlyargcount,value.co_flags,value.co_exceptiontable)
    if isinstance(value,tuple):return tuple(canonical(v) for v in value)
    return value


def main():
    archive = ZlibArchiveReader(str(ROOT/'build/work/Babelander2/PYZ-00.pyz'))
    modules = {}
    for path in (ROOT/'babelander').glob('*.py'):
        name = 'babelander' if path.stem=='__init__' else 'babelander.'+path.stem
        bundled = archive.extract(name)
        current = compile(path.read_text(encoding='utf-8'),bundled.co_filename,'exec',dont_inherit=True,optimize=0)
        modules[name] = canonical(bundled)==canonical(current)
    assert all(modules.values()),'Bundle does not match current source: '+repr(modules)
    assert not any(n=='gamelens' or n.startswith('gamelens.') for n in archive.toc)
    assert not list(BUNDLE.rglob('*.dpapi'))
    assert not list(BUNDLE.rglob('*.sqlite3'))
    assert not list(BUNDLE.rglob('*.gguf'))
    license_root = ROOT/'assets/licenses'
    license_root.mkdir(parents=True,exist_ok=True)
    dependency_info = []
    for distribution in metadata.distributions():
        name = distribution.metadata['Name']
        if name=='babelander-desktop':continue
        record = {'name':name,'version':distribution.version,
                  'license':distribution.metadata.get('License-Expression') or distribution.metadata.get('License') or 'See installed package notices',
                  'notices':[]}
        for file in distribution.files or []:
            parts = str(file).lower()
            if '.dist-info/' not in parts or not any(word in Path(str(file)).name.lower() for word in ('license','copying','notice')):
                continue
            source = Path(distribution.locate_file(file))
            if source.is_file():
                destination = license_root/name/Path(str(file)).name
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,destination)
                record['notices'].append(str(destination.relative_to(ROOT)).replace('\\','/'))
        dependency_info.append(record)
    (ROOT/'assets/dependencies.json').write_text(json.dumps(dependency_info,ensure_ascii=False,indent=2),encoding='utf-8')
    shutil.copytree(license_root,BUNDLE/'licenses',dirs_exist_ok=True)
    shutil.copy2(ROOT/'assets/dependencies.json',BUNDLE/'dependencies.json')
    for name in ('README.md','ARCHITECTURE.md','TEST_REPORT.md','TEST_REPORT_ALPHA3.md','QUALITY_REVIEW.md','CHANGELOG.md','LICENSE'):
        shutil.copy2(ROOT/name,BUNDLE/name)
    if (ROOT/'BENCHMARK_100_ENGLISH.md').exists():
        shutil.copy2(ROOT/'BENCHMARK_100_ENGLISH.md',BUNDLE/'BENCHMARK_100_ENGLISH.md')
    if (ROOT/'BENCHMARK_MOVING_BACKGROUND.md').exists():
        shutil.copy2(ROOT/'BENCHMARK_MOVING_BACKGROUND.md',BUNDLE/'BENCHMARK_MOVING_BACKGROUND.md')
    if (ROOT/'BENCHMARK_SUBTITLE.md').exists():
        shutil.copy2(ROOT/'BENCHMARK_SUBTITLE.md',BUNDLE/'BENCHMARK_SUBTITLE.md')
    for name in ('BENCHMARK_LATENCY_A5.md','BENCHMARK_LATENCY_A6.md','BENCHMARK_LATENCY_A8.md','TEST_REPORT_ALPHA4.md','TEST_REPORT_ALPHA6.md','TEST_REPORT_ALPHA7.md','TEST_REPORT_ALPHA8.md','TEST_REPORT_ALPHA9.md','TEST_REPORT_ALPHA10.md','TEST_REPORT_ALPHA11.md','TEST_REPORT_ALPHA12.md','TEST_REPORT_ALPHA13.md','TEST_REPORT_ALPHA14.md','TEST_REPORT_ALPHA15.md','TEST_REPORT_ALPHA16.md','TEST_REPORT_ALPHA17.md','TEST_REPORT_ALPHA18.md','TEST_REPORT_ALPHA19.md','TEST_REPORT_ALPHA20.md','SUPERTEST.md','LATENCY_NEXT_STEPS.md','DEBATE_700MS.md'):
        if (ROOT/name).exists():shutil.copy2(ROOT/name,BUNDLE/name)
    shutil.copytree(ROOT/'assets',BUNDLE/'assets',dirs_exist_ok=True,ignore=shutil.ignore_patterns('licenses'))
    if (ROOT/'TEST_REPORT_ALPHA21.md').exists():shutil.copy2(ROOT/'TEST_REPORT_ALPHA21.md',BUNDLE/'TEST_REPORT_ALPHA21.md')
    if (ROOT/'TEST_REPORT_ALPHA22.md').exists():shutil.copy2(ROOT/'TEST_REPORT_ALPHA22.md',BUNDLE/'TEST_REPORT_ALPHA22.md')
    if (ROOT/'TEST_REPORT_ALPHA23.md').exists():shutil.copy2(ROOT/'TEST_REPORT_ALPHA23.md',BUNDLE/'TEST_REPORT_ALPHA23.md')
    excluded = {'.venv','__pycache__','build','dist','test-results','babelander_desktop.egg-info'}
    files = sorted(p for p in ROOT.rglob('*') if p.is_file() and not any(part in excluded for part in p.relative_to(ROOT).parts) and p.suffix not in ('.pyc','.dpapi'))
    source_zip = DIST/f'Babelander2-{__version__}-source.zip'
    with zipfile.ZipFile(source_zip,'w',zipfile.ZIP_DEFLATED) as backup:
        for path in files:backup.write(path,'Babelander2/'+path.relative_to(ROOT).as_posix())
    bundle = BUNDLE
    report = {'passed':True,'version':__version__,'compiled_modules_match_current_source':modules,
              'original_application_modules':0,'bundled_credentials':0,
              'bundle_bytes':sum(p.stat().st_size for p in bundle.rglob('*') if p.is_file()),
              'exe_sha256':digest(bundle/'Babelander2.exe'),'source_zip_sha256':digest(source_zip),
              'wheel_sha256':digest(DIST/f'babelander_desktop-{__version__}-py3-none-any.whl'),
              'source_files':{p.relative_to(ROOT).as_posix():digest(p) for p in files}}
    (ROOT/'test-results/artifacts.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='source_files'},indent=2))


if __name__=='__main__':main()
