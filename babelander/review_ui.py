"""Qt capture review with keyboard zoom and an explicit stop/edit action."""
from datetime import datetime
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QPolygonF
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QComboBox, QScrollArea, QPlainTextEdit, QCheckBox)
from .types import LABELS
from .windows import exclude_capture


class CaptureReview(QDialog):
    def __init__(self, snapshot, threshold, window):
        super().__init__(window)
        self.snapshot, self.threshold, self.window = snapshot, threshold, window
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(LABELS[snapshot.mode]+' · 畫面核對')
        self.resize(900, 660)
        self.setMinimumSize(600, 480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        title = QLabel('對照畫面，確認辨識文字'); title.setObjectName('pageTitle')
        layout.addWidget(title)
        stamp = datetime.fromtimestamp(snapshot.created).strftime('%H:%M:%S')
        detail = QLabel(f'最近一次辨識 · {stamp} · 原始 {snapshot.width} × {snapshot.height} px\n'
                        '這是開啟時的快照；只保留在記憶體，關閉程式即清除。')
        detail.setWordWrap(True); detail.setObjectName('muted'); layout.addWidget(detail)
        controls = QHBoxLayout()
        zoom_label = QLabel('縮圖倍率'); controls.addWidget(zoom_label)
        self.zoom = QComboBox()
        for text, value in [('符合視窗', 0), ('50%', .5), ('100%', 1), ('150%', 1.5), ('200%', 2)]:
            self.zoom.addItem(text, value)
        self.zoom.setAccessibleName('擷取縮圖倍率'); zoom_label.setBuddy(self.zoom)
        controls.addWidget(self.zoom)
        self.boxes = QCheckBox('標示辨識框與行號'); self.boxes.setChecked(True)
        controls.addWidget(self.boxes); controls.addStretch(); layout.addLayout(controls)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image = QLabel(); self.image.setAccessibleName('最近一次框選畫面縮圖')
        self.scroll.setWidget(self.image); layout.addWidget(self.scroll, 3)
        self.text = QPlainTextEdit(); self.text.setReadOnly(True)
        self.text.setAccessibleName('辨識文字與各行信心分數')
        self.text.setPlainText('\n'.join(f'{i}. [{line.confidence:.0%}' +
            (' · 請核對' if line.confidence < threshold else '') + f'] {line.text}'
            for i, line in enumerate(snapshot.lines, 1)) or '沒有辨識到文字，請縮小範圍或重新框選。')
        layout.addWidget(self.text, 2)
        actions = QHBoxLayout()
        self.edit_button = QPushButton('停止監測並編輯原文'); self.edit_button.setObjectName('primary')
        self.edit_button.setAccessibleName('停止目前工作並將此快照文字放入原文編輯器')
        self.edit_button.clicked.connect(self.edit_source); actions.addWidget(self.edit_button)
        actions.addStretch()
        close = QPushButton('關閉'); close.clicked.connect(self.close); actions.addWidget(close)
        layout.addLayout(actions)
        self.zoom.currentIndexChanged.connect(self.render)
        self.boxes.toggled.connect(self.render)
        self.render()

    def render(self):
        s = self.snapshot
        image = QImage(s.pixels, s.preview_width, s.preview_height, s.preview_width*3,
                       QImage.Format.Format_BGR888).copy()
        if self.boxes.isChecked():
            painter = QPainter(image)
            for i, line in enumerate(s.lines, 1):
                if not line.box: continue
                color = QColor('#b45309' if line.confidence < self.threshold else '#047857')
                painter.setPen(QPen(color, 2))
                polygon = QPolygonF([QPointF(x*s.preview_width/s.width, y*s.preview_height/s.height)
                                     for x, y in line.box])
                painter.drawPolygon(polygon)
                point = polygon[0]; painter.drawText(QPointF(max(0, point.x()), max(12, point.y()-3)), str(i))
            painter.end()
        scale = self.zoom.currentData()
        if scale == 0:
            viewport = self.scroll.viewport().size()
            scale = min(1, max(1, viewport.width()-8)/image.width(), max(1, viewport.height()-8)/image.height())
        pixmap = QPixmap.fromImage(image).scaled(max(1, round(image.width()*scale)),
                  max(1, round(image.height()*scale)), Qt.AspectRatioMode.KeepAspectRatio,
                  Qt.TransformationMode.SmoothTransformation)
        self.image.setPixmap(pixmap); self.image.resize(pixmap.size())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'zoom'): self.render()

    def showEvent(self, event):
        super().showEvent(event); exclude_capture(self); self.render()

    def edit_source(self):
        mode = self.snapshot.mode
        self.window.stop(mode)
        page = self.window.pages[mode]
        page.source.setPlainText('\n'.join(line.text for line in self.snapshot.lines))
        page.set_status('已停止 · 請核對原文後重新翻譯')
        # Review can be opened from a workspace that is no longer selected.
        for index in range(self.window.stack.count()):
            if self.window.stack.widget(index).widget() is page:
                self.window.stack.setCurrentIndex(index)
                self.window.navigation.button(index).setChecked(True)
                break
        self.close(); page.source.setFocus()
