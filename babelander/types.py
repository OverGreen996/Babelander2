from dataclasses import dataclass, field
from enum import StrEnum
import threading
import time


class Mode(StrEnum):
    DIALOG = 'dialog'
    EQUIPMENT = 'equipment'
    QUEST = 'quest'
    CHAT = 'chat'
    REPLY = 'reply'
    SCREEN = 'screen'


LABELS = {Mode.DIALOG:'即時字幕', Mode.EQUIPMENT:'裝備卡', Mode.QUEST:'任務卡',
          Mode.CHAT:'聊天室', Mode.REPLY:'中文回覆', Mode.SCREEN:'框選翻譯'}


class Cancelled(Exception):
    pass


class Cancellation:
    def __init__(self):
        self.event = threading.Event()

    def cancel(self):
        self.event.set()

    def cancelled(self):
        return self.event.is_set()

    def check(self):
        if self.cancelled():
            raise Cancelled('工作已取消')


@dataclass(frozen=True)
class Region:
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self):
        if self.width < 8 or self.height < 8:
            raise ValueError('框選範圍太小，請至少選取 8 × 8 像素。')


@dataclass(frozen=True)
class OCRLine:
    text: str
    box: tuple
    confidence: float


@dataclass(frozen=True)
class CaptureEvidence:
    mode: Mode
    generation: int
    width: int
    height: int
    preview_width: int
    preview_height: int
    pixels: bytes
    lines: tuple[OCRLine, ...]
    created: float = field(default_factory=time.time)


@dataclass(frozen=True)
class Translation:
    source: str
    target: str
    provider: str
    origin: str
    warning: str = ''
    cache_hit: bool = False
    model_ms: float = 0
    ocr_confidence: float | None = None
    queue_ms: float = 0
    postprocess_ms: float = 0
    backend_state: str = 'none'


@dataclass(frozen=True)
class EquipmentSlot:
    source_bounds: tuple[float, float, float, float]
    bounds: tuple[float, float, float, float]
    color: tuple[int, int, int]
    font_pixels: float
    literal: str = ''  # Untranslated numeric cells retain their original glyphs.
    alignment: str = 'left'


@dataclass(frozen=True)
class EquipmentLayout:
    region: Region
    width: int
    height: int
    pixels: bytes  # BGR backdrop with recognized original text removed.
    slots: tuple[EquipmentSlot, ...]


@dataclass(frozen=True)
class JobResult:
    mode: Mode
    generation: int
    translations: tuple[Translation, ...]
    ocr_ms: float = 0
    total_ms: float = 0
    created: float = field(default_factory=time.time)

    event_id: int = 0
    stages: tuple = ()
    emitted_at: float = 0
    capture_epoch: int = 0
    equipment_layout: EquipmentLayout | None = None

    @property
    def text(self):
        return '\n'.join(t.target for t in self.translations)
