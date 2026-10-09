"""Pinned upstream assets, resumable downloads and verified atomic installs."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path,PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile
import requests
from .types import Cancelled

@dataclass(frozen=True)
class Asset:
    name:str
    url:str
    size:int
    sha256:str

ASSETS=(
    Asset('Qwen_Qwen3-1.7B-Q4_K_M.gguf','https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF/resolve/dcb19155b962dbb6389f4691a982043a8e651022/Qwen_Qwen3-1.7B-Q4_K_M.gguf',1282439584,'72c5c3cb38fa32d5256e2fe30d03e7a64c6c79e668ad84057e3bd66e250b24fb'),
    Asset('llama-b10896-bin-win-cuda-12.4-x64.zip','https://github.com/ggml-org/llama.cpp/releases/download/b10896/llama-b10896-bin-win-cuda-12.4-x64.zip',254080575,'3f73b9d3987fbbf681e153ddf665acba99bd4ab746dbcd1c34d99fbc8f9742c7'),
    Asset('cudart-llama-bin-win-cuda-12.4-x64.zip','https://github.com/ggml-org/llama.cpp/releases/download/b10896/cudart-llama-bin-win-cuda-12.4-x64.zip',391443627,'8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6'),
)

def digest(path,token):
    h=hashlib.sha256()
    with Path(path).open('rb') as source:
        while block:=source.read(1024*1024):
            token.check();h.update(block)
    return h.hexdigest()

def download(asset,directory,token,progress=lambda *args:None,session=None):
    """Only a size+SHA verified .part becomes a usable final file."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    if Path(asset.name).name!=asset.name or '/' in asset.name or '\\' in asset.name:
        raise ValueError('資產檔名無效。')
    final=directory/asset.name;partial=directory/(asset.name+'.part')
    token.check()
    if final.exists() and final.stat().st_size==asset.size and digest(final,token)==asset.sha256:
        progress(asset.name,asset.size,asset.size);return final
    offset=partial.stat().st_size if partial.exists() else 0
    if offset>asset.size:partial.unlink();offset=0
    if offset<asset.size:
        progress(asset.name,offset,asset.size)
        client=session or requests.Session()
        try:
            with client.get(asset.url,headers={'Range':f'bytes={offset}-','Accept-Encoding':'identity'} if offset else {'Accept-Encoding':'identity'},stream=True,timeout=(10,15)) as response:
                response.raise_for_status();token.check()
                if response.status_code==206:
                    match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('Content-Range',''))
                    if not match or tuple(map(int,match.groups()))!=(offset,asset.size-1,asset.size):
                        raise ValueError('下載續傳範圍不符；原檔未變更。')
                elif response.status_code==200:
                    offset=0
                else:raise ValueError('下載回應無效。')
                with partial.open('ab' if offset else 'wb') as target:
                    for block in response.iter_content(1024*1024):
                        token.check()
                        if not block:continue
                        offset+=len(block)
                        if offset>asset.size:raise ValueError('下載大小超出已驗證資產。')
                        target.write(block);progress(asset.name,offset,asset.size)
        except requests.RequestException:
            raise ValueError('下載連線失敗；已下載部分保留，可再按下載續傳。') from None
        finally:
            if session is None:client.close()
    token.check();progress('正在驗證 '+asset.name,asset.size,asset.size)
    if partial.stat().st_size!=asset.size:raise ValueError('下載不完整；可再按下載續傳。')
    if digest(partial,token)!=asset.sha256:
        partial.unlink()
        raise ValueError('SHA-256 不符；已丟棄損壞下載，現有模型未變更。')
    token.check();partial.replace(final)
    return final

def extract_verified(archives,destination,token):
    """Fresh staging directory only, bounded extraction, reject path/link tricks."""
    destination=Path(destination).resolve();seen=set();total=0
    for archive in archives:
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                token.check();name=member.filename.replace('\\','/')
                parts=PurePosixPath(name)
                mode=member.external_attr>>16
                if parts.is_absolute() or '..' in parts.parts or any(':' in p or p.rstrip(' .')!=p or p.upper().split('.')[0] in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]} for p in parts.parts) or stat.S_ISLNK(mode):
                    raise ValueError('執行元件壓縮檔路徑無效。')
                target=destination.joinpath(*parts.parts).resolve()
                if not target.is_relative_to(destination):raise ValueError('壓縮檔路徑超出安裝目錄。')
                if member.is_dir():target.mkdir(parents=True,exist_ok=True);continue
                normalized=name.casefold()
                if normalized in seen:raise ValueError('執行元件出現重複檔案。')
                seen.add(normalized);total+=member.file_size
                if len(seen)>500 or total>3*1024**3:raise ValueError('執行元件解壓大小無效。')
                target.parent.mkdir(parents=True,exist_ok=True)
                with bundle.open(member) as source,target.open('xb') as output:
                    while block:=source.read(1024*1024):token.check();output.write(block)
    return seen

def install(root,token,progress=lambda *args:None):
    root=Path(root)/'assets';root.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(root).free<4*1024**3:
        raise ValueError('下載與安裝需至少 4 GB 可用空間。')
    downloaded=[download(asset,root/'downloads',token,progress) for asset in ASSETS]
    token.check();progress('正在安裝已驗證執行元件',0,1)
    # Unique immutable directory makes a failed install harmless to running jobs.
    with tempfile.TemporaryDirectory(prefix='runtime-staging-',dir=root) as staging:
        stage=Path(staging);extract_verified(downloaded[1:],stage,token)
        server=stage/'llama-server.exe'
        if not server.is_file() or not (stage/'cudart64_12.dll').is_file():raise ValueError('執行元件不完整。')
        files={p.relative_to(stage).as_posix():digest(p,token) for p in stage.rglob('*') if p.is_file()}
        (stage/'verified-assets.json').write_text(json.dumps({'assets':[a.__dict__ for a in ASSETS],'files':files},indent=2),encoding='utf-8')
        token.check()
        # A destination chosen by the OS is owned by this install, never delete
        # an existing runtime or switch application paths before completion.
        destination=Path(tempfile.mkdtemp(prefix='llama-b10896-',dir=root))
        destination.rmdir();stage.rename(destination)
    progress('模型與執行元件已驗證',1,1)
    return str(downloaded[0]),str(destination/'llama-server.exe')
