from dataclasses import dataclass, field, asdict
from pathlib import Path
import json
import os

from .types import Mode


@dataclass
class Settings:
    providers: dict = field(default_factory=lambda: {m.value:'local' for m in Mode})
    model_path: str = ''
    server_path: str = ''
    profile: str = 'fast'
    scan_ms: int = 800
    dialog_scan_ms: int = 100
    chat_scan_ms: int = 100
    ocr_threads: int = 2
    adaptive_ocr_recheck: bool = False
    reuse_dialogue_lines: bool = False
    mixed_text_trigger: bool = False
    stable_ms: int = 100
    font_size: int = 24
    idle_unload_seconds: int = 300
    azure_region: str = ''
    deepl_free: bool = True
    monthly_limit: int = 100000
    ocr_review_threshold: float = .70
    overlays: dict = field(default_factory=dict)
    hotkeys: dict = field(default_factory=lambda: {'select_dialog':'Ctrl+Alt+F1','toggle_dialog':'Ctrl+Alt+F2',
                                                  'toggle_overlay':'Ctrl+Alt+F3','toggle_background':'Ctrl+Alt+F4',
                                                  'select_equipment':'Alt+T','toggle_equipment':'','select_quest':'','select_chat':'Ctrl+Alt+C',
                                                  'select_screen':'Ctrl+Alt+S','show_reply':'Ctrl+Alt+R'})

    def provider(self, mode):
        return 'local' if mode == Mode.CHAT else self.providers.get(mode.value, 'local')

    def validate(self):
        if any(p not in ('local','google','azure','deepl') for p in self.providers.values()):
            raise ValueError('翻譯引擎設定無效。')
        if self.profile not in ('fast','shared','cpu'):
            raise ValueError('模型效能模式無效。')
        if not 300 <= self.scan_ms <= 10000 or not 0 <= self.stable_ms <= 5000:
            raise ValueError('掃描或穩定等待時間超出範圍。')
        if type(self.dialog_scan_ms) is not int or not 100<=self.dialog_scan_ms<=10000:
            raise ValueError('字幕觀察間隔需介於 100–10000 毫秒。')
        if type(self.chat_scan_ms) is not int or not 100<=self.chat_scan_ms<=10000:
            raise ValueError('聊天觀察間隔需介於 100–10000 毫秒。')
        if type(self.ocr_threads) is not int or not 1<=self.ocr_threads<=4:
            raise ValueError('OCR 執行緒需介於 1–4。')
        if type(self.adaptive_ocr_recheck) is not bool:
            raise ValueError('字幕複查設定無效。')
        if type(self.reuse_dialogue_lines) is not bool:
            raise ValueError('字幕行重用設定無效。')
        if type(self.mixed_text_trigger) is not bool:
            raise ValueError('混色字幕觸發設定無效。')
        if self.monthly_limit < 0 or not 12 <= self.font_size <= 64:
            raise ValueError('字數上限或浮層字級無效。')
        if type(self.idle_unload_seconds) is not int or not 0<=self.idle_unload_seconds<=3600:
            raise ValueError('模型閒置卸載時間需介於 0–3600 秒。')
        if not isinstance(self.ocr_review_threshold,(float,int)) or not 0 <= self.ocr_review_threshold <= 1:
            raise ValueError('OCR 核對門檻需介於 0–100%。')
        if not isinstance(self.overlays,dict):
            raise ValueError('浮層位置設定無效。')
        for mode,state in self.overlays.items():
            if mode not in {m.value for m in Mode if m!=Mode.REPLY} or not isinstance(state,dict):
                raise ValueError('浮層位置設定無效。')
            for key,low,high in (('x',-50000,50000),('y',-50000,50000),('width',300,6000),('height',120,6000)):
                if key in state and (type(state[key]) is not int or not low<=state[key]<=high):
                    raise ValueError('浮層位置或大小超出範圍。')
            if 'background' in state and type(state['background']) is not bool:
                raise ValueError('浮層背景設定無效。')
        self.providers['chat'] = 'local'


def data_root():
    if os.environ.get('BABELANDER_V2_DATA'):
        return Path(os.environ['BABELANDER_V2_DATA']).resolve()
    return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Babelander2'


def load_settings(root):
    path = Path(root) / 'settings.json'
    if path.exists():
        raw = json.loads(path.read_text(encoding='utf-8'))
        settings = Settings(**{k:v for k,v in raw.items() if k in Settings.__dataclass_fields__})
        settings.validate()
        return settings
    settings = Settings()
    assets = Path(__file__).resolve().parents[2] / 'recovery/test-assets'
    # Use already verified immutable assets without copying user data.
    server = assets / 'runtime/llama-server.exe'
    models = sorted((assets / 'models').glob('*.gguf'))
    if server.exists():
        settings.server_path = str(server)
    if models:
        settings.model_path = str(models[0])
    return settings


def save_settings(root, settings):
    settings.validate()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / 'settings.json.tmp'
    temporary.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(root / 'settings.json')
