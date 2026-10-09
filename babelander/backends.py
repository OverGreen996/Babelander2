"""Real local llama.cpp and cloud transports. No automatic cross-provider fallback."""
from pathlib import Path
import html
import secrets
import socket
import subprocess
import threading
import time

import requests
from .types import Cancelled


class BackendError(Exception):
    pass


class LocalBackend:
    def __init__(self, settings, root):
        self.settings = settings
        self.root = Path(root)
        self.lock = threading.RLock()
        self.process = None
        self.port = None
        self.secret = secrets.token_urlsafe(24)
        self.closed = False
        self.log = None

    def start(self, token=None):
        with self.lock:
            if token is not None:token.check()
            if self.closed:
                raise BackendError('本機模型服務已關閉。')
            if self.process and self.process.poll() is None:
                if token is not None:
                    try:
                        response=requests.get(f'http://127.0.0.1:{self.port}/health',timeout=1,
                                              headers={'Authorization':'Bearer '+self.secret})
                        token.check()
                        if response.status_code!=200:raise BackendError('本機模型尚未就緒，請稍後再試。')
                    except requests.RequestException:
                        raise BackendError('無法確認本機模型狀態，請稍後再試。') from None
                return
            # A crashed server still owns its startup log handle.
            self.stop()
            settings = self.settings
            model, server = Path(settings.model_path),Path(settings.server_path)
            if not model.is_file() or not server.is_file():
                raise BackendError('請到設定選擇 GGUF 模型與 llama-server.exe。')
            with socket.socket() as candidate:
                candidate.bind(('127.0.0.1',0))
                self.port = candidate.getsockname()[1]
            layers = {'fast':99,'shared':14,'cpu':0}[settings.profile]
            args = [str(server),'-m',str(model),'--host','127.0.0.1','--port',str(self.port),
                    '--api-key',self.secret,'-ngl',str(layers),'-c','2048','-np','1','-b','128','-ub','128',
                    '-t','2','-tb','2','-fa','on']
            if settings.profile == 'cpu':
                args += ['--device','none','--no-kv-offload']
            self.root.mkdir(parents=True,exist_ok=True)
            # Model input logging is disabled by llama.cpp's default verbosity.
            # Startup stderr may contain paths but never cloud credentials.
            self.log = (self.root/'model-startup.log').open('wb')
            try:
                self.process = subprocess.Popen(args,cwd=server.parent,stdin=subprocess.DEVNULL,
                                                stdout=self.log,stderr=self.log,
                                                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            except OSError:
                self.stop()
                raise BackendError('模型執行元件無法啟動，請檢查檔案與依賴 DLL。') from None
            deadline = time.monotonic()+60
            while time.monotonic()<deadline:
                if token is not None:
                    try:token.check()
                    except Cancelled:
                        self.stop();raise
                if self.closed:
                    self.stop()
                    raise BackendError('模型載入已取消。')
                if self.process is None or self.process.poll() is not None:
                    self.stop()
                    raise BackendError('模型啟動失敗，請檢查模型路徑或顯存。')
                try:
                    response = requests.get(f'http://127.0.0.1:{self.port}/health',timeout=1,
                                            headers={'Authorization':'Bearer '+self.secret})
                    if response.status_code == 200:
                        if token is not None:
                            try:token.check()
                            except Cancelled:
                                self.stop();raise
                        return
                except requests.RequestException:
                    pass
                time.sleep(.1)
            self.stop()
            raise BackendError('模型載入逾時。')

    def translate(self, system, text):
        self.start()
        try:
            response = requests.post(f'http://127.0.0.1:{self.port}/v1/chat/completions',timeout=(3,30),
                                     headers={'Authorization':'Bearer '+self.secret},
                                     json={'messages':[{'role':'system','content':system},{'role':'user','content':text}],
                                           'temperature':0,'max_tokens':320,'stream':False,
                                           'chat_template_kwargs':{'enable_thinking':False}})
            response.raise_for_status()
            choice = response.json()['choices'][0]
            if choice.get('finish_reason') == 'length':
                raise BackendError('譯文超過模型長度，請縮小框選或分段。')
            output = choice['message']['content']
            if not isinstance(output,str) or not output.strip():
                raise BackendError('本機模型回傳空白或無效內容。')
            return output.strip()
        except (requests.RequestException,KeyError,ValueError,IndexError,TypeError,AttributeError) as error:
            raise BackendError('本機模型請求失敗或逾時。') from error

    def stop(self):
        # No model lock here: shutdown must interrupt a running HTTP request.
        process,self.process = self.process,None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(3)
        if self.log:
            self.log.close()
            self.log = None

    def close(self):
        self.closed = True
        self.stop()


class CloudBackend:
    def __init__(self, settings, vault, store):
        self.settings,self.vault,self.store = settings,vault,store

    def translate(self, provider, text, reply=False):
        key = self.vault.get(provider)
        if provider == 'google':
            url = 'https://translation.googleapis.com/language/translate/v2'
            kwargs = {'params':{'key':key},'json':{'q':text,'format':'text','source':'zh-TW' if reply else 'en','target':'en' if reply else 'zh-TW'}}
        elif provider == 'azure':
            url = 'https://api.cognitive.microsofttranslator.com/translate'
            kwargs = {'params':{'api-version':'3.0','from':'zh-Hant' if reply else 'en','to':'en' if reply else 'zh-Hant'},
                      'headers':{'Ocp-Apim-Subscription-Key':key,'Ocp-Apim-Subscription-Region':self.settings.azure_region},
                      'json':[{'Text':text}]}
        elif provider == 'deepl':
            url = 'https://api-free.deepl.com/v2/translate' if self.settings.deepl_free else 'https://api.deepl.com/v2/translate'
            kwargs = {'headers':{'Authorization':'DeepL-Auth-Key '+key},
                      'json':{'text':[text],'source_lang':'ZH' if reply else 'EN','target_lang':'EN' if reply else 'ZH-HANT'}}
        else:
            raise BackendError('未知雲端引擎。')
        month = self.store.reserve(provider,len(text),self.settings.monthly_limit)
        try:
            response = requests.post(url,timeout=(5,25),allow_redirects=False,**kwargs)
            if response.status_code != 200:
                raise BackendError(f'{provider} 回應 HTTP {response.status_code}，未自動重試。')
            data = response.json()
            if provider == 'google':
                output = html.unescape(data['data']['translations'][0]['translatedText'])
            elif provider == 'azure':
                output = data[0]['translations'][0]['text']
            else:
                output = data['translations'][0]['text']
            if not isinstance(output,str) or not output.strip():
                raise BackendError(provider+' 回傳空白或無效內容，未自動重試。')
            self.store.confirm(provider,len(text),month)
            return output.strip()
        except (requests.RequestException,KeyError,ValueError,IndexError,TypeError,AttributeError) as error:
            raise BackendError(provider+' 請求失敗或逾時，未自動重試。') from error
