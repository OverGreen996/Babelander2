"""Chrome-free single-shot overlay, anchored to the physical selection ROI."""
import math
from PySide6.QtCore import Qt,Signal,QPointF,QRectF
from PySide6.QtGui import QImage,QPainter,QColor,QFont,QTextLayout,QTextOption
from PySide6.QtWidgets import QWidget
from .windows import exclude_capture,logical_region,place_physical


def fitted_text(text,slot,font_scale=1):
    x0,y0,x1,y1=slot.bounds
    width,height=x1-x0,y1-y0
    preferred=slot.font_pixels*font_scale
    minimum=max(8,min(preferred,slot.font_pixels*.60))
    for size in range(max(8,round(preferred)),math.ceil(minimum)-1,-1):
        font=QFont('Microsoft JhengHei UI');font.setPixelSize(size)
        layout=QTextLayout(text,font)
        option=QTextOption();option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        if slot.alignment=='center':option.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.setTextOption(option);layout.beginLayout()
        y=0;overflow=False
        while True:
            line=layout.createLine()
            if not line.isValid():break
            line.setLineWidth(width)
            line.setPosition(QPointF(0,y));y+=line.height()
            if line.naturalTextWidth()>width+.1 or y>height+.1:overflow=True;break
        layout.endLayout()
        if not overflow:return layout,size
    return None,None


class EquipmentOverlay(QWidget):
    hidden_by_user=Signal()
    geometry_changed=Signal()
    def __init__(self,title='裝備卡',font_size=24):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|
                         Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowDoesNotAcceptFocus|
                         Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.title=title
        self.setAccessibleName('原位'+title+'譯文覆蓋；可在主視窗隱藏或重新框選')
        self.layout_data=None;self.image=QImage();self.draw_items=[]
        self.plain='';self.font_scale=font_size/24;self.render_warning=''
        self.transparent_input=True
        self.text=self  # Shared target-only overlay inspection API.
    @property
    def renderable(self):return self.layout_data is not None and bool(self.plain) and not self.render_warning
    def toPlainText(self):return self.plain
    def set_text(self,text):
        if not text:
            self.layout_data=None;self.image=QImage();self.draw_items=[];self.plain='';self.render_warning=''
            self.translations=()
            self.hide();self.update()
    def set_warning(self,text):pass  # Review feedback belongs to the workbench.
    def set_font(self,size):
        self.font_scale=size/24
        if self.layout_data is not None:self._prepare()
    def set_translations(self,translations,layout=None):
        self.set_text('')
        self.translations=tuple(translations)
        if layout is None:
            self.render_warning='原位覆蓋需要框選卡片；文字試譯只顯示在主視窗。'
            return
        if len(translations)!=len(layout.slots):
            self.render_warning='譯文段落與卡片位置不一致，請重新框選。';return
        self.layout_data=layout
        self.image=QImage(layout.pixels,layout.width,layout.height,layout.width*3,QImage.Format.Format_BGR888)
        self._prepare()
        screen,geometry=logical_region(layout.region)
        self.winId();self.windowHandle().setScreen(screen);self.setGeometry(geometry)
    def _prepare(self):
        self.draw_items=[];self.plain='';self.render_warning=''
        if any(t.warning or not t.target.strip() for t in self.translations):
            self.render_warning='部分段落未取得可靠譯文，請在主視窗核對；卡片覆蓋暫不顯示。'
            self.hide();return
        for translation,slot in zip(self.translations,self.layout_data.slots):
            if translation.warning or not translation.target.strip():continue
            if slot.literal:
                if translation.target.strip()!=slot.literal:
                    self.render_warning='卡片數值與原畫面不一致，請重新核對。';self.draw_items=[];self.hide();return
                continue
            layout,size=fitted_text(translation.target,slot,self.font_scale)
            if layout is None:
                self.render_warning='譯文無法完整放入原卡片區塊，請核對或在設定降低浮層字級。'
                self.draw_items=[];self.hide();return
            self.draw_items.append((layout,slot,size))
        self.plain='\n\n'.join(t.target for t in self.translations if not t.warning and t.target.strip())
        self.update()
    def set_passthrough(self,enabled):pass  # Original geometry must stay fixed.
    def adjust_geometry(self):pass  # Re-select the ROI to change its geometry.
    def set_background(self,enabled):pass
    def state(self):return {}
    def restore_state(self,state):pass  # Old detached-card coordinates ignored.
    def hide_by_user(self):self.hide();self.hidden_by_user.emit()
    def paintEvent(self,event):
        if self.layout_data is None:return
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.scale(self.width()/self.layout_data.width,self.height()/self.layout_data.height)
        painter.drawImage(QPointF(0,0),self.image)
        for layout,slot,size in self.draw_items:
            painter.save()
            x0,y0,x1,y1=slot.bounds
            painter.setClipRect(QRectF(x0,y0,x1-x0,y1-y0))
            painter.setPen(QColor(*slot.color))
            layout.draw(painter,QPointF(slot.bounds[0],slot.bounds[1]))
            painter.restore()
        # The captured frame is already the game's native chrome. Preserve its
        # corners, panels and decorations instead of imposing one gold border.
    def showEvent(self,event):
        super().showEvent(event)
        exclude_capture(self)
        if self.layout_data is not None:
            try:place_physical(self,self.layout_data.region)
            except OSError as error:
                self.render_warning=str(error);self.hide()
