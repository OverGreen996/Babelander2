from PySide6.QtCore import Qt, Signal, QRect, QPoint,QEvent,QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QTextOption
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QPlainTextEdit,
                              QSizeGrip,QDialog,QFormLayout,QSpinBox,QCheckBox,QDialogButtonBox,
                              QScrollArea,QFrame,QApplication,QGraphicsDropShadowEffect)

from .windows import physical_region, exclude_capture
from .equipment_fast_rules import NUMERIC_FIELD


class RegionPicker(QWidget):
    selected = Signal(object)
    cancelled = Signal()

    def __init__(self, screen):
        super().__init__(None,Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool)
        self.screen_reference = screen
        self.start = self.finish = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.winId()
        self.windowHandle().setScreen(screen)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAccessibleName('框選要辨識的文字；Esc 取消')
        self.setMouseTracking(True)

    def showEvent(self, event):
        super().showEvent(event)
        exclude_capture(self)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(),QColor(10,15,22,135))
        painter.setPen(QColor('#f0d29b'))
        painter.drawText(QPoint(32,42),'拖曳框選文字範圍  ·  Esc 取消')
        if self.start is not None:
            rectangle = QRect(self.start,self.finish or self.start).normalized()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rectangle,Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor('#e4c38c'),2))
            painter.drawRect(rectangle)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start = self.finish = event.position().toPoint()
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self.cancelled.emit()

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.finish = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.start is not None:
            rectangle = QRect(self.start,event.position().toPoint()).normalized()
            if rectangle.width()<8 or rectangle.height()<8:
                self.start = self.finish = None
                self.update()
                return
            self.selected.emit(physical_region(self.screen_reference,rectangle))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()


class Overlay(QWidget):
    hidden_by_user = Signal()
    geometry_changed = Signal()
    def __init__(self, title, font_size=24):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName('translationOverlay')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(520,160)
        self.resize(660,240)
        self.transparent_input = False
        self.background = True
        self.drag = None
        self.setProperty('background',True)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.caption = QLabel(title)
        self.caption.setObjectName('overlayCaption')
        self.caption.setToolTip('拖曳標題移動；也可使用「位置／大小」輸入座標')
        self.caption.installEventFilter(self)
        self.adjust_button = QPushButton('位置／大小')
        self.adjust_button.clicked.connect(self.adjust_geometry)
        self.background_button = QPushButton('背景')
        self.background_button.setCheckable(True)
        self.background_button.setChecked(True)
        self.background_button.clicked.connect(self.set_background)
        self.passthrough = QPushButton('滑鼠穿透')
        self.passthrough.setCheckable(True)
        self.passthrough.setToolTip('穿透後可在主視窗恢復互動')
        self.passthrough.clicked.connect(self.set_passthrough)
        close = QPushButton('隱藏')
        close.clicked.connect(self.hide_by_user)
        top.addWidget(self.caption,1)
        top.addWidget(self.adjust_button)
        top.addWidget(self.background_button)
        top.addWidget(self.passthrough)
        top.addWidget(close)
        layout.addLayout(top)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.text.setAccessibleName(title+'翻譯結果')
        shadow = QGraphicsDropShadowEffect(self.text)
        shadow.setBlurRadius(4)
        shadow.setOffset(1,1)
        shadow.setColor(QColor('black'))
        self.text.setGraphicsEffect(shadow)
        layout.addWidget(self.text)
        self.warning = QLabel()
        self.warning.setObjectName('overlayWarning')
        self.warning.setWordWrap(True)
        self.warning.setTextFormat(Qt.TextFormat.PlainText)
        self.warning.setAccessibleName('浮層核對提示')
        self.warning.hide()
        layout.addWidget(self.warning)
        footer = QHBoxLayout()
        self.hint = QLabel('可選取複製文字 · 右下角拖曳縮放')
        self.hint.setObjectName('overlayCaption')
        footer.addWidget(self.hint,1)
        self.size_grip = QSizeGrip(self)
        self.size_grip.setAccessibleName('調整浮層大小；也可使用位置與大小按鈕')
        footer.addWidget(self.size_grip)
        layout.addLayout(footer)
        self.set_font(font_size)

    def set_font(self, size):
        font = self.text.font()
        font.setPointSize(size)
        self.text.setFont(font)
        self.text.setStyleSheet(f'font-size:{size}pt; background:transparent; border:none;')

    def set_text(self, text):
        self.text.setPlainText(text)

    def set_warning(self, text):
        self.warning.setText('需核對 · '+text if text else '')
        self.warning.setVisible(bool(text))

    def hide_by_user(self):
        self.hide()
        self.hidden_by_user.emit()

    def set_passthrough(self, enabled):
        self.transparent_input = bool(enabled)
        self.passthrough.setChecked(enabled)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput,enabled)
        self.show()
        exclude_capture(self)

    def toggle_background(self):
        self.set_background(not self.background)

    def set_background(self, enabled):
        self.background = bool(enabled)
        self.background_button.setChecked(self.background)
        self.setProperty('background',self.background)
        for widget in [self,*self.findChildren(QWidget)]:
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.update()
        self.geometry_changed.emit()

    def paintEvent(self, event):
        if self.background:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(19,28,39,238))
            painter.setPen(QPen(QColor('#53657b'),1))
            painter.drawRoundedRect(self.rect().adjusted(1,1,-1,-1),12,12)

    def state(self):
        return {'x':self.x(),'y':self.y(),'width':self.width(),'height':self.height(),'background':self.background}

    def restore_state(self, state):
        self.resize(state.get('width',self.width()),state.get('height',self.height()))
        position = QPoint(state.get('x',self.x()),state.get('y',self.y()))
        proposed = QRect(position,self.size())
        if not any((proposed & s.availableGeometry()).width()>=min(240,self.width()) and (proposed & s.availableGeometry()).height()>=100 for s in QApplication.screens()):
            area = QApplication.primaryScreen().availableGeometry()
            position = QPoint(area.center().x()-self.width()//2,area.bottom()-self.height()-70)
        self.move(position)
        self.set_background(state.get('background',True))

    def adjust_geometry(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('浮層位置與大小')
        form = QFormLayout(dialog)
        fields = {}
        for name,title,low,high,value in (('x','水平位置',-50000,50000,self.x()),('y','垂直位置',-50000,50000,self.y()),
                                        ('width','寬度',self.minimumWidth(),6000,self.width()),('height','高度',self.minimumHeight(),6000,self.height())):
            field = QSpinBox();field.setRange(low,high);field.setValue(value)
            field.setAccessibleName(title)
            fields[name] = field
            form.addRow(title,field)
        background = QCheckBox('顯示背景')
        background.setChecked(self.background)
        form.addRow(background)
        reset = QPushButton('移到目前螢幕中央')
        def center():
            area = (self.screen() or QApplication.primaryScreen()).availableGeometry()
            fields['x'].setValue(area.center().x()-fields['width'].value()//2)
            fields['y'].setValue(area.center().y()-fields['height'].value()//2)
        reset.clicked.connect(center)
        form.addRow(reset)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(dialog.accept);actions.rejected.connect(dialog.reject)
        form.addRow(actions)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            state = {name:field.value() for name,field in fields.items()}
            self.restore_state({**state,'background':background.isChecked()})
            self.geometry_changed.emit()
        dialog.deleteLater()

    def eventFilter(self, watched, event):
        if watched is self.caption:
            if event.type()==QEvent.Type.MouseButtonPress and event.button()==Qt.MouseButton.LeftButton:
                self.drag = event.globalPosition().toPoint()-self.frameGeometry().topLeft()
                return True
            if event.type()==QEvent.Type.MouseMove and self.drag is not None:
                self.move(event.globalPosition().toPoint()-self.drag)
                return True
            if event.type()==QEvent.Type.MouseButtonRelease and self.drag is not None:
                self.drag = None
                self.geometry_changed.emit()
                return True
        return super().eventFilter(watched,event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.geometry_changed.emit()

    def showEvent(self, event):
        super().showEvent(event)
        exclude_capture(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y()<55:
            self.drag = event.globalPosition().toPoint()-self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self.drag is not None:
            self.move(event.globalPosition().toPoint()-self.drag)

    def mouseReleaseEvent(self, event):
        self.drag = None
        self.geometry_changed.emit()


class CardPane(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(0,0,0,0)
        self.body.setSpacing(12)
        self.setWidget(self.content)
        self.plain = ''
        self.font_size = 24
        self.translations = ()
        self.equipment = False

    def clear_items(self):
        while self.body.count():
            item = self.body.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def setPlainText(self, text):
        self.clear_items()
        self.plain = text
        self.translations = ()
        label = QLabel(text)
        label.setWordWrap(True)
        self.body.addWidget(label)
        self.body.addStretch()

    def toPlainText(self):
        return self.plain

    def set_translations(self, translations):
        self.clear_items()
        self.verticalScrollBar().setValue(0)
        self.translations = tuple(t for t in translations if t.target.strip() and not t.warning)
        self.plain = '\n\n'.join(t.target for t in self.translations)
        for index,translation in enumerate(self.translations):
            card = QFrame()
            field=self.equipment and NUMERIC_FIELD.fullmatch(translation.source.strip()) is not None
            heading=(self.equipment and index==0 and len(self.translations)>1 and
                     '\n' not in translation.source and len(translation.source)<=50 and
                     not any(character in translation.source for character in '.!?%:+-0123456789'))
            card.setObjectName('overlayStat' if field else 'overlayCard')
            body = QVBoxLayout(card)
            body.setContentsMargins(16,12,16,12)
            target = QLabel(translation.target)
            target.setObjectName('overlayHeading' if heading else 'overlayStatText' if field else 'overlayTarget')
            target.setWordWrap(True)
            target.setTextFormat(Qt.TextFormat.PlainText)
            target.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse|Qt.TextInteractionFlag.TextSelectableByKeyboard)
            size=self.font_size+2 if heading else self.font_size
            font = target.font();font.setPointSize(size);target.setFont(font)
            target.setStyleSheet(f'font-size:{size}pt;')
            body.addWidget(target)
            self.body.addWidget(card)
        self.body.addStretch()


class CardOverlay(Overlay):
    stop_requested=Signal()
    def __init__(self, title, font_size=24, *, equipment=False):
        super().__init__(title,font_size)
        prior = self.text
        self.text = CardPane()
        self.text.equipment=equipment
        self.text.font_size = font_size
        self.text.setAccessibleName(title+'譯文段落')
        self.layout().replaceWidget(prior,self.text)
        prior.deleteLater()
        self.resize(760,560)
        self.setMinimumSize(520,260)
        self.stop_button=QPushButton('停止跟讀')
        self.stop_button.setAccessibleName('停止裝備卡自動跟讀')
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.layout().itemAt(self.layout().count()-1).layout().insertWidget(1,self.stop_button)
        self.stop_button.hide()

    def set_monitoring(self, enabled):
        self.stop_button.setVisible(enabled)
        self.hint.setText('跟讀中 · 換卡自動更新' if enabled else '可選取複製文字 · 右下角拖曳縮放')

    def set_font(self, size):
        if isinstance(getattr(self,'text',None),CardPane):
            self.text.font_size = size
            self.text.set_translations(self.text.translations)
        else:
            super().set_font(size)

    def set_translations(self, translations):
        self.text.set_translations(translations)


class ReplyInput(QPlainTextEdit):
    translate_requested = Signal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.translate_requested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)
