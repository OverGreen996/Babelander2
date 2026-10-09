from pathlib import Path
from dataclasses import replace
import copy
import time

from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QKeySequence,QTextCursor
from PySide6.QtWidgets import (QMainWindow,QWidget,QFrame,QHBoxLayout,QVBoxLayout,QLabel,QPushButton,
                              QButtonGroup,QStackedWidget,QScrollArea,QPlainTextEdit,QComboBox,
                              QLineEdit,QSpinBox,QCheckBox,QFormLayout,QFileDialog,QTableWidget,
                              QTableWidgetItem,QHeaderView,QApplication,QKeySequenceEdit)

from .types import Mode,LABELS
from .settings import save_settings
from .widgets import RegionPicker,Overlay,CardOverlay,ReplyInput
from .equipment_overlay import EquipmentOverlay
from .windows import Hotkeys,exclude_capture
from .asset_ui import AssetPanel
from . import __version__

PROVIDERS = [('本機','local'),('Google','google'),('Azure','azure'),('DeepL','deepl')]
DESCRIPTIONS = {
    Mode.DIALOG:'跟上劇情。框選字幕後持續監測，文字穩定才翻譯。',
    Mode.EQUIPMENT:'單次框選裝備卡。譯文覆蓋原區域，保留文字位置、欄位與段落；取消即還原。',
    Mode.QUEST:'單次框選任務面板、快捷任務欄或日誌。譯文覆蓋原區域，保留排版、字色、進度與按鈕；取消即還原。',
    Mode.CHAT:'接上隊友的話。持續讀取新訊息，保留說話者，本機翻譯。',
    Mode.REPLY:'中文寫下想說的話，取得英文後由你複製並送出。',
    Mode.SCREEN:'閱讀攻略、公告與其他畫面。一次框選，原文可修改後重翻。',
}


def label(text, name=None):
    widget = QLabel(text)
    widget.setWordWrap(True)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, callback, primary=False):
    widget = QPushButton(text)
    if primary:
        widget.setObjectName('primary')
    widget.clicked.connect(callback)
    widget.setAccessibleName(text)
    return widget


def table(headers):
    widget = QTableWidget(0,len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setAlternatingRowColors(True)
    widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    widget.verticalHeader().hide()
    widget.setMinimumHeight(230)
    return widget


def populate(widget, rows):
    widget.setRowCount(len(rows))
    for y,row in enumerate(rows):
        for x,value in enumerate(row):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            widget.setItem(y,x,item)
    widget.resizeRowsToContents()


class Workspace(QWidget):
    def __init__(self, mode, window):
        super().__init__()
        self.mode,self.window = mode,window
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(label(LABELS[mode],'pageTitle'))
        layout.addWidget(label(DESCRIPTIONS[mode],'muted'))
        controls = QHBoxLayout()
        controls.addWidget(label('翻譯引擎'))
        self.provider = QComboBox()
        for title,identifier in PROVIDERS:
            self.provider.addItem(title,identifier)
        self.provider.setCurrentIndex(self.provider.findData(window.settings.provider(mode)))
        self.provider.setAccessibleName(LABELS[mode]+'翻譯引擎')
        self.provider.setEnabled(mode != Mode.CHAT)
        self.provider.currentIndexChanged.connect(lambda _:window.change_provider(mode,self.provider.currentData()))
        controls.addWidget(self.provider)
        controls.addStretch()
        controls.addWidget(label('中文 → 英文' if mode == Mode.REPLY else '英文 → 繁體中文','muted'))
        layout.addLayout(controls)
        if mode != Mode.REPLY:
            capture_bar = QHBoxLayout()
            capture_bar.addWidget(button('框選裝備卡' if mode==Mode.EQUIPMENT else '框選'+LABELS[mode],lambda:window.select_region(mode),True))
            if mode in (Mode.DIALOG,Mode.CHAT):
                self.monitor_button = button('開始監測',lambda:window.toggle_monitor(mode))
                capture_bar.addWidget(self.monitor_button)
            if mode in (Mode.EQUIPMENT,Mode.QUEST):
                self.once_button=button('重新辨識',lambda:window.capture_once(mode))
                capture_bar.addWidget(self.once_button)
            capture_bar.addWidget(button('取消／還原' if mode in (Mode.EQUIPMENT,Mode.QUEST) else '取消／停止',lambda:window.stop(mode)))
            self.review_button = button('查看辨識畫面',lambda:window.show_capture_review(mode))
            self.review_button.setEnabled(False)
            capture_bar.addWidget(self.review_button)
            capture_bar.addStretch()
            layout.addLayout(capture_bar)
            self.region_label = label('尚未框選 · 可先輸入文字試譯','muted')
            layout.addWidget(self.region_label)
        self.status = label('準備就緒','status')
        layout.addWidget(self.status)
        self.ocr_note = label('','ocrWarning')
        self.ocr_note.setAccessibleName('辨識核對提示')
        self.ocr_note.hide()
        layout.addWidget(self.ocr_note)
        panel = QFrame()
        panel.setObjectName('panel')
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18,18,18,18)
        source_header = QHBoxLayout()
        source_header.addWidget(label('想回覆的中文' if mode == Mode.REPLY else '原文'))
        source_header.addStretch()
        source_header.addWidget(label('Enter 翻譯 · Shift+Enter 換行' if mode == Mode.REPLY else '可編輯後重新翻譯','muted'))
        panel_layout.addLayout(source_header)
        self.source = ReplyInput() if mode == Mode.REPLY else QPlainTextEdit()
        self.source.setMinimumHeight(80)
        self.source.setMaximumHeight(110)
        self.source.setPlaceholderText('例如：我 5 分鐘後回來，請不要開始。' if mode == Mode.REPLY else '框選後會顯示辨識文字，也可以直接貼上英文。')
        self.source.setAccessibleName(LABELS[mode]+'原文輸入')
        if mode == Mode.REPLY:
            self.source.translate_requested.connect(lambda:window.translate_text(mode))
        panel_layout.addWidget(self.source)
        actions = QHBoxLayout()
        self.translate_button = button('翻成英文' if mode == Mode.REPLY else '翻譯輸入文字',lambda:window.translate_text(mode),mode == Mode.REPLY)
        actions.addWidget(self.translate_button)
        if mode == Mode.REPLY:
            actions.addWidget(button('回覆小窗',window.show_reply))
            actions.addWidget(button('取消',lambda:window.stop(mode)))
        elif mode in (Mode.EQUIPMENT,Mode.QUEST):
            actions.addWidget(button('顯示／隱藏覆蓋',lambda:window.toggle_overlay(mode)))
        else:
            actions.addWidget(button('顯示／隱藏浮層',lambda:window.toggle_overlay(mode)))
            actions.addWidget(button('恢復浮層互動',lambda:window.interact_overlay(mode)))
            actions.addWidget(button('浮層設定',lambda:window.overlay(mode).adjust_geometry()))
        actions.addStretch()
        actions.addWidget(button('清除',lambda:window.clear_workspace(mode)))
        panel_layout.addLayout(actions)
        panel_layout.addWidget(label('英文回覆' if mode == Mode.REPLY else '譯文'))
        self.target = QPlainTextEdit()
        self.target.setReadOnly(True)
        self.target.setMinimumHeight(100)
        self.target.setMaximumHeight(170)
        self.target.setAccessibleName(LABELS[mode]+'譯文')
        self.target.setPlaceholderText('翻譯完成後顯示於此。')
        panel_layout.addWidget(self.target,1)
        footer = QHBoxLayout()
        self.metrics = label('核對原文與譯文後再使用。','muted')
        footer.addWidget(self.metrics,1)
        footer.addWidget(button('複製英文' if mode == Mode.REPLY else '複製譯文',lambda:QApplication.clipboard().setText(self.target.toPlainText())))
        panel_layout.addLayout(footer)
        layout.addWidget(panel,1)
        if mode in (Mode.EQUIPMENT,Mode.QUEST):
            self.cells = table(['原文','譯文','來源／檢查'])
            self.target.hide()
            panel_layout.insertWidget(panel_layout.count()-1,self.cells,1)

    def set_status(self, message, error=False):
        self.status.setText(message)
        self.status.setProperty('error',error)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)


class ReplyWindow(QWidget):
    def __init__(self, window):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.WindowStaysOnTopHint)
        self.window = window
        self.setWindowTitle('譯鄉人 · 中文回覆')
        self.resize(500,370)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(label('中文 → 英文','brand'),1)
        top.addWidget(button('收合／展開',self.collapse))
        layout.addLayout(top)
        self.content = QWidget()
        body = QVBoxLayout(self.content)
        self.source = ReplyInput()
        self.source.setPlaceholderText('Enter 翻譯 · Shift+Enter 換行')
        self.source.translate_requested.connect(self.translate)
        body.addWidget(self.source)
        self.translate_button = button('翻成英文',self.translate,True)
        body.addWidget(self.translate_button)
        body.addWidget(button('取消翻譯',lambda:window.stop(Mode.REPLY)))
        self.target = QPlainTextEdit()
        self.target.setReadOnly(True)
        body.addWidget(self.target)
        body.addWidget(button('複製英文',lambda:QApplication.clipboard().setText(self.target.toPlainText())))
        layout.addWidget(self.content)
        self.status = label('草稿只保留於本次執行；不會自動送出。','muted')
        layout.addWidget(self.status)

    def translate(self):
        if Mode.REPLY in self.window.busy_modes:
            return
        self.window.pages[Mode.REPLY].source.setPlainText(self.source.toPlainText())
        self.window.translate_text(Mode.REPLY)

    def collapse(self):
        self.content.setVisible(not self.content.isVisible())
        self.resize(self.width(),370 if self.content.isVisible() else 100)

    def showEvent(self, event):
        super().showEvent(event)
        exclude_capture(self)


class MainWindow(QMainWindow):
    def __init__(self, controller, store, settings, vault, root):
        super().__init__()
        self.controller,self.store,self.settings,self.vault,self.root = controller,store,settings,vault,root
        self.setWindowTitle('Babelander 2 · 譯鄉人')
        self.resize(1190,860)
        self.setMinimumSize(880,680)
        self.regions = {}
        self.monitoring = set()
        self.overlays = {}
        self.overlay_hidden = set()
        self.overlay_timers = {}
        self.busy_modes = set()
        self.pickers = []
        self.chat_messages = []
        self.capture_evidence = {}
        self.review_dialogs = {}
        self.reply_window = None
        self.pages = {}
        self.closing = False
        from .window_focus import WindowFocus
        self.window_focus=WindowFocus()
        self.window_bindings={}
        self.focus_modes=set()
        self.focus_paused=set()
        self.focus_pending_once=set()
        self.focus_guards={}
        self.focus_moves={}
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(24,20,24,20)
        outer.setSpacing(20)
        header = QHBoxLayout()
        brand = QVBoxLayout()
        brand.addWidget(label('B A B E L A N D E R','eyebrow'))
        brand.addWidget(label('譯鄉人','brand'))
        header.addLayout(brand,1)
        self.runtime_status = label('第二代開發版  ·  '+__version__,'muted')
        header.addWidget(self.runtime_status)
        outer.addLayout(header)
        body = QHBoxLayout()
        body.setSpacing(24)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(190)
        navigation = QVBoxLayout(sidebar)
        navigation.setContentsMargins(12,18,12,18)
        navigation.setSpacing(6)
        navigation.addWidget(label('翻譯工作台','muted'))
        self.stack = QStackedWidget()
        self.navigation = QButtonGroup(self)
        self.navigation.setExclusive(True)
        for mode in Mode:
            page = Workspace(mode,self)
            self.pages[mode] = page
            self._add_page(navigation,LABELS[mode],page)
        navigation.addSpacing(16)
        navigation.addWidget(label('管理與設定','muted'))
        self.dictionary_page = self._build_dictionary()
        self.history_page = self._build_history()
        self.settings_page = self._build_settings()
        for title,page in (('我的詞庫',self.dictionary_page),('歷史與用量',self.history_page),('設定',self.settings_page)):
            self._add_page(navigation,title,page)
        navigation.addStretch()
        navigation.addWidget(label('聊天室固定本機\n回覆由你自行送出','muted'))
        self.navigation.button(0).setChecked(True)
        self.navigation.idClicked.connect(self.stack.setCurrentIndex)
        body.addWidget(sidebar)
        body.addWidget(self.stack,1)
        outer.addLayout(body,1)
        controller.delivery.connect(self.receive)
        controller.preparation_done.connect(self.preparation_finished)
        controller.captured.connect(self.receive_capture)
        controller.status_delivery.connect(self.receive_status)
        controller.failed.connect(self.failed)
        controller.started.connect(self.job_started)
        controller.finished.connect(self.job_finished)
        self.hotkeys = Hotkeys(QApplication.instance())
        self.hotkeys.triggered.connect(self.handle_hotkey)
        self.refresh_hotkeys()
        self.refresh_data()
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(5000)
        self.idle_timer.timeout.connect(self.check_idle_model)
        self.idle_timer.start()
        self.focus_timer=QTimer(self)
        self.focus_timer.setInterval(200)
        self.focus_timer.timeout.connect(self.check_window_focus)

    def _add_page(self, navigation, title, page):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        index = self.stack.addWidget(scroll)
        item = QPushButton(title)
        item.setObjectName('navigation')
        item.setCheckable(True)
        item.setAccessibleName(title)
        self.navigation.addButton(item,index)
        navigation.addWidget(item)

    def _build_dictionary(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(label('我的詞庫','pageTitle'))
        layout.addWidget(label('固定名稱與術語的譯法。使用者詞庫優先，儲存後會更新快取。','muted'))
        form = QFormLayout()
        self.term_source,self.term_target = QLineEdit(),QLineEdit()
        self.term_domain = QComboBox()
        self.term_domain.addItem('共用','shared')
        for mode in (Mode.DIALOG,Mode.EQUIPMENT,Mode.QUEST,Mode.CHAT):
            self.term_domain.addItem(LABELS[mode],mode.value)
        form.addRow('原文',self.term_source)
        form.addRow('譯文',self.term_target)
        form.addRow('使用範圍',self.term_domain)
        layout.addLayout(form)
        actions = QHBoxLayout()
        actions.addWidget(button('儲存詞條',self.save_term,True))
        actions.addWidget(button('刪除選取詞條',self.delete_term))
        actions.addStretch()
        layout.addLayout(actions)
        self.term_status = label('任意框選與中文回覆不套用遊戲詞庫。','muted')
        layout.addWidget(self.term_status)
        self.term_table = table(['原文','譯文','範圍'])
        self.term_table.itemSelectionChanged.connect(self.select_term)
        layout.addWidget(self.term_table,1)
        return page

    def _build_history(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(label('歷史與用量','pageTitle'))
        layout.addWidget(label('翻譯歷史保存在這台電腦；聊天訊息與回覆草稿只留在本次執行。','muted'))
        self.usage_label = label('尚無雲端請求。','status')
        layout.addWidget(self.usage_label)
        actions = QHBoxLayout()
        actions.addWidget(button('重新整理',self.refresh_data))
        actions.addWidget(button('清除歷史',lambda:(self.store.clear_history(),self.refresh_data())))
        actions.addWidget(button('清除翻譯快取',lambda:(self.store.clear_cache(),self.controller.engine.volatile.clear(),self.refresh_data())))
        actions.addStretch()
        layout.addLayout(actions)
        self.history_table = table(['功能','原文','譯文','引擎','檢查'])
        layout.addWidget(self.history_table,1)
        layout.addWidget(label('請求字數是保守的安全計數，包含已送出的失敗請求；不等同服務商帳單。','muted'))
        return page

    def _build_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(label('設定','pageTitle'))
        layout.addWidget(label('本機模型、掃描頻率與雲端連線。金鑰由 Windows 加密保護。','muted'))
        form = QFormLayout()
        self.model_path,self.server_path = QLineEdit(self.settings.model_path),QLineEdit(self.settings.server_path)
        for title,field,filter_text in (('GGUF 模型',self.model_path,'GGUF (*.gguf)'),('模型執行元件',self.server_path,'llama-server (*.exe)')):
            row = QHBoxLayout()
            row.addWidget(field,1)
            row.addWidget(button('選擇',lambda checked=False,f=field,t=filter_text:self.choose_file(f,t)))
            form.addRow(title,row)
        self.profile = QComboBox()
        for title,value in [('速度優先','fast'),('低顯存分工','shared'),('CPU 模式','cpu')]:
            self.profile.addItem(title,value)
        self.profile.setCurrentIndex(self.profile.findData(self.settings.profile))
        form.addRow('模型效能',self.profile)
        self.idle_unload = QSpinBox()
        self.idle_unload.setRange(0,3600);self.idle_unload.setValue(self.settings.idle_unload_seconds)
        self.idle_unload.setSuffix(' 秒（0 為不卸載）')
        form.addRow('模型閒置卸載',self.idle_unload)
        model_actions=QHBoxLayout()
        self.prepare_button=button('進遊戲前預載模型',self.prepare_model)
        self.prepare_button.setAccessibleName('預載本機模型')
        self.prepare_button.setToolTip('使用已儲存的本機設定，提早完成模型載入；仍遵守閒置卸載。')
        self.prepare_cancel=button('取消預載',self.cancel_model_preparation)
        self.prepare_cancel.setEnabled(False)
        model_actions.addWidget(self.prepare_button);model_actions.addWidget(self.prepare_cancel);model_actions.addStretch()
        form.addRow('模型準備',model_actions)
        self.model_status=label('模型按需載入；進遊戲前可先預載，減少第一句等待。','muted')
        self.model_status.setAccessibleName('本機模型準備狀態')
        form.addRow('',self.model_status)
        self.scan,self.stable,self.font_size,self.limit = QSpinBox(),QSpinBox(),QSpinBox(),QSpinBox()
        for field,low,high,value,suffix in ((self.scan,300,10000,self.settings.scan_ms,' ms'),(self.stable,0,5000,self.settings.stable_ms,' ms'),
                                          (self.font_size,12,64,self.settings.font_size,' pt'),(self.limit,0,100000000,self.settings.monthly_limit,' 字')):
            field.setRange(low,high)
            field.setValue(value)
            field.setSuffix(suffix)
        form.addRow('字幕背景複查間隔',self.scan)
        self.dialog_scan=QSpinBox()
        self.dialog_scan.setRange(100,10000);self.dialog_scan.setValue(self.settings.dialog_scan_ms)
        self.dialog_scan.setSuffix(' ms')
        form.addRow('字幕觀察間隔',self.dialog_scan)
        self.chat_scan=QSpinBox()
        self.chat_scan.setRange(100,10000);self.chat_scan.setValue(self.settings.chat_scan_ms)
        self.chat_scan.setSuffix(' ms');self.chat_scan.setSingleStep(50)
        self.chat_scan.setAccessibleName('聊天觀察間隔')
        form.addRow('聊天觀察間隔',self.chat_scan)
        chat_hint='預設 100ms。聊天背景持續變動時會增加 CPU 工作，可調高到 300–800ms。'
        self.chat_scan.setAccessibleDescription(chat_hint)
        self.chat_scan.setToolTip(chat_hint)
        form.addRow('',label(chat_hint,'muted'))
        form.addRow('字幕穩定等待',self.stable)
        self.ocr_threshold = QSpinBox()
        self.ocr_threshold.setRange(0,100)
        self.ocr_threshold.setValue(round(self.settings.ocr_review_threshold*100))
        self.ocr_threshold.setSuffix(' %')
        form.addRow('OCR 核對門檻',self.ocr_threshold)
        self.ocr_threads=QComboBox()
        for count,title in ((1,'1 · 較少 CPU'),(2,'2 · 標準'),(3,'3 · 較快'),(4,'4 · 優先速度')):
            self.ocr_threads.addItem(title,count)
        self.ocr_threads.setCurrentIndex(self.ocr_threads.findData(self.settings.ocr_threads))
        self.ocr_threads.setAccessibleName('OCR 執行緒')
        form.addRow('OCR 執行緒',self.ocr_threads)
        self.reuse_lines=QCheckBox('白字字幕加速（試驗）')
        self.reuse_lines.setChecked(self.settings.reuse_dialogue_lines)
        self.reuse_lines.setAccessibleName('白字字幕加速試驗')
        form.addRow('字幕加速',self.reuse_lines)
        form.addRow('',label('適合固定位置的橫排白字。暗字、混色字幕可能漏字；出現漏字時請關閉。','muted'))
        self.mixed_trigger=QCheckBox('白字旁的暗字變化偵測（試驗）')
        self.mixed_trigger.setChecked(self.settings.mixed_text_trigger)
        self.mixed_trigger.setAccessibleName('混色字幕觸發試驗')
        form.addRow('混色字幕',self.mixed_trigger)
        form.addRow('',label('補查白字未變時新增的描邊暗字。需連續畫面確認，可能增加 CPU；保留定期複查。','muted'))
        form.addRow('浮層字級',self.font_size)
        form.addRow('每家每月字數上限（0 為不限制）',self.limit)
        self.region_field = QLineEdit(self.settings.azure_region)
        form.addRow('Azure 區域',self.region_field)
        self.deepl_free = QCheckBox('使用 DeepL API Free')
        self.deepl_free.setChecked(self.settings.deepl_free)
        form.addRow('DeepL 方案',self.deepl_free)
        self.key_fields = {}
        for provider in ('google','azure','deepl'):
            field = QLineEdit()
            field.setEchoMode(QLineEdit.EchoMode.Password)
            field.setPlaceholderText('已儲存；留白保留' if self.vault.has(provider) else '尚未設定')
            self.key_fields[provider] = field
            row = QHBoxLayout()
            row.addWidget(field,1)
            row.addWidget(button('移除',lambda checked=False,p=provider:self.delete_key(p)))
            form.addRow(provider+' API Key',row)
        layout.addLayout(form)
        layout.addWidget(label('低於 OCR 門檻會保留原文，核對後可手動翻譯。辨識信心不代表翻譯正確率。','muted'))
        self.asset_panel = AssetPanel(self.root)
        self.asset_panel.installed.connect(lambda model,server:(self.model_path.setText(model),self.server_path.setText(server)))
        layout.addWidget(self.asset_panel)
        layout.addWidget(button('停止工作並卸載本機模型',self.unload_model))
        layout.addWidget(label('雲端功能會把文字傳給所選服務。聊天室固定本機；沒有自動切換到雲端。','muted'))
        layout.addWidget(label('全域快捷鍵','brand'))
        shortcuts = QFormLayout()
        self.shortcut_fields = {}
        titles = {'select_dialog':'框選字幕','toggle_dialog':'開始／停止字幕','toggle_overlay':'顯示／隱藏字幕浮層',
                  'toggle_background':'切換字幕背景','select_equipment':'框選裝備','toggle_equipment':'顯示／隱藏裝備覆蓋','select_quest':'框選任務',
                  'select_chat':'框選聊天室','select_screen':'任意框選','show_reply':'回覆小窗'}
        for action,title in titles.items():
            field = QKeySequenceEdit(QKeySequence(self.settings.hotkeys.get(action,'')))
            self.shortcut_fields[action] = field
            shortcuts.addRow(title,field)
        layout.addLayout(shortcuts)
        self.settings_status = label('選擇現有資產或下載驗證後，按下儲存設定。','muted')
        layout.addWidget(self.settings_status)
        layout.addWidget(button('儲存設定',self.apply_settings,True))
        layout.addStretch()
        return page

    def refresh_hotkeys(self):
        errors = self.hotkeys.configure(self.settings.hotkeys)
        if errors:
            self.settings_status.setText('\n'.join(errors))

    def change_provider(self, mode, provider):
        self.stop(mode)
        self.settings.providers[mode.value] = provider
        save_settings(self.root,self.settings)

    def choose_file(self, field, filter_text):
        path,_ = QFileDialog.getOpenFileName(self,'選擇檔案',field.text(),filter_text)
        if path:
            field.setText(path)

    def apply_settings(self):
        try:
            settings = replace(self.settings,providers=dict(self.settings.providers),
                               overlays=copy.deepcopy(self.settings.overlays),ocr_review_threshold=self.ocr_threshold.value()/100,
                               model_path=self.model_path.text().strip(),server_path=self.server_path.text().strip(),
                               profile=self.profile.currentData(),scan_ms=self.scan.value(),dialog_scan_ms=self.dialog_scan.value(),stable_ms=self.stable.value(),
                               idle_unload_seconds=self.idle_unload.value(),
                               chat_scan_ms=self.chat_scan.value(),
                               ocr_threads=self.ocr_threads.currentData(),reuse_dialogue_lines=self.reuse_lines.isChecked(),mixed_text_trigger=self.mixed_trigger.isChecked(),
                               font_size=self.font_size.value(),monthly_limit=self.limit.value(),
                               azure_region=self.region_field.text().strip(),deepl_free=self.deepl_free.isChecked(),
                               hotkeys={a:f.keySequence().toString(QKeySequence.SequenceFormat.PortableText) for a,f in self.shortcut_fields.items()})
            settings.validate()
            self.cancel_model_preparation(release_model=False)
            for mode in Mode:
                self.stop(mode)
            for provider,field in self.key_fields.items():
                if field.text().strip():
                    self.vault.put(provider,field.text())
                    field.clear()
                    field.setPlaceholderText('已儲存；留白保留')
            save_settings(self.root,settings)
            self.settings = self.controller.settings = settings
            self.controller.engine.reconfigure(settings)
            for overlay in self.overlays.values():
                overlay.set_font(settings.font_size)
            self.settings_status.setText('已儲存。下一次翻譯會使用新設定。')
            self.refresh_hotkeys()
        except Exception as error:
            self.settings_status.setText(str(error))

    def delete_key(self, provider):
        for mode in Mode:
            self.stop(mode)
        self.vault.delete(provider)
        self.key_fields[provider].clear()
        self.key_fields[provider].setPlaceholderText('尚未設定')
        self.settings_status.setText(provider+' 金鑰已移除。')

    def prepare_model(self):
        if not self.prepare_button.isEnabled():return
        if (self.model_path.text().strip(),self.server_path.text().strip(),self.profile.currentData())!=(self.settings.model_path,self.settings.server_path,self.settings.profile):
            self.model_status.setText('請先儲存模型路徑與效能設定，再預載。')
            return
        self.prepare_button.setEnabled(False);self.prepare_button.setText('模型準備中…')
        self.prepare_cancel.setEnabled(True)
        self.model_status.setText('正在排隊／載入本機模型；首次可能需要數秒。')
        try:self.controller.prepare_local()
        except Exception as error:
            self.preparation_finished(self.controller.preparation_id,{'ready':False,'error':str(error)})

    def preparation_finished(self, identifier, report):
        if self.closing or identifier!=self.controller.preparation_id:return
        self.prepare_button.setEnabled(True);self.prepare_button.setText('進遊戲前預載模型')
        self.prepare_cancel.setEnabled(False)
        if report.get('ready'):
            self.model_status.setText('本機模型已就緒；可開始框選。閒置時仍依設定卸載。')
        else:self.model_status.setText(report.get('error','模型未就緒，請稍後再試。'))

    def cancel_model_preparation(self, release_model=True):
        active=self.prepare_cancel.isEnabled()
        self.controller.cancel_preparation(release_model=release_model and active)
        self.prepare_button.setEnabled(True);self.prepare_button.setText('進遊戲前預載模型')
        self.prepare_cancel.setEnabled(False)
        self.model_status.setText('已取消預載，正在結束尚未完成的載入。' if active else '模型按需載入；進遊戲前可先預載。')

    def unload_model(self):
        self.cancel_model_preparation(release_model=False)
        for mode in Mode:self.stop(mode)
        self.controller.engine.unload_local()
        self.settings_status.setText('已停止工作並卸載本機模型；下次本機翻譯會重新載入。')
        self.model_status.setText('本機模型已卸載；進遊戲前可再次預載。')

    def check_idle_model(self):
        if self.controller.engine.maybe_unload():
            self.settings_status.setText('本機模型已閒置卸載；下次本機翻譯會重新載入。')
            self.model_status.setText('本機模型已閒置卸載；進遊戲前可再次預載。')

    def save_term(self):
        try:
            self.store.save_term(self.term_source.text(),self.term_target.text(),self.term_domain.currentData())
            self.term_status.setText('詞條已儲存。')
            self.refresh_data()
        except ValueError as error:
            self.term_status.setText(str(error))

    def select_term(self):
        row = self.term_table.currentRow()
        if 0 <= row < len(self.term_rows):
            _,source,target,domain = self.term_rows[row]
            self.term_source.setText(source)
            self.term_target.setText(target)
            self.term_domain.setCurrentIndex(self.term_domain.findData(domain))

    def delete_term(self):
        row = self.term_table.currentRow()
        if 0 <= row < len(self.term_rows):
            self.store.delete_term(self.term_rows[row][0])
            self.refresh_data()

    def refresh_data(self):
        self.term_rows = self.store.terms()
        populate(self.term_table,[r[1:] for r in self.term_rows])
        populate(self.history_table,[(LABELS.get(Mode(r[0]),r[0]),*r[1:]) for r in self.store.history()])
        usage = self.store.usage()
        self.usage_label.setText('  ·  '.join(f'{p} 請求 {a:,} 字／成功 {c:,} 字' for p,a,c in usage) or '本月尚無雲端請求。')

    def select_region(self, mode):
        self.stop(mode,release_model=False)
        self._close_pickers()
        self.hide()
        def start():
            if self.closing:
                return
            for screen in QApplication.screens():
                picker = RegionPicker(screen)
                picker.selected.connect(lambda region,m=mode:self.region_selected(m,region))
                picker.cancelled.connect(self.cancel_selection)
                self.pickers.append(picker)
                picker.show()
            if self.pickers:
                self.pickers[0].activateWindow()
                self.pickers[0].setFocus()
        QTimer.singleShot(100,start)

    def _close_pickers(self):
        for picker in self.pickers:
            picker.close()
            picker.deleteLater()
        self.pickers.clear()

    def cancel_selection(self):
        self._close_pickers()
        self.show()

    def region_selected(self, mode, region):
        self._close_pickers()
        self.window_bindings.pop(mode,None)
        if self.window_focus.enabled:
            binding=self.window_focus.bind(region)
            if binding is not None:self.window_bindings[mode]=binding
            elif mode in (Mode.DIALOG,Mode.CHAT):
                self.regions.pop(mode,None)
                self.show()
                self.pages[mode].set_status('無法確認框選視窗，請在同一個遊戲視窗內重新框選。',True)
                return
        self.regions[mode] = region
        self.pages[mode].region_label.setText(f'框選範圍 {region.width} × {region.height} px')
        if mode in (Mode.EQUIPMENT,Mode.QUEST) or mode in self.window_bindings:self.showMinimized()
        else:self.show()
        if mode in (Mode.DIALOG,Mode.CHAT):
            self.toggle_monitor(mode)
        else:
            self._start_region_work(mode,continuous=False)

    def _clear_capture_overlay(self, mode):
        self.capture_evidence.pop(mode,None)
        if hasattr(self.pages.get(mode),'review_button'):self.pages[mode].review_button.setEnabled(False)
        if mode in self.overlays:
            self.overlays[mode].set_text('')
            self.overlays[mode].set_warning('')
            self.overlays[mode].hide()

    def _start_region_work(self, mode, continuous):
        from .window_focus import FocusGuard,FocusState
        binding=self.window_bindings.get(mode)
        if continuous and self.window_focus.enabled and binding is None:
            self.stop(mode,release_model=False)
            self.pages[mode].set_status('無法確認框選視窗，請重新框選。',True)
            return
        guard=None
        if binding is not None:
            state=self.window_focus.state(binding)
            if state==FocusState.MOVED and continuous:
                self._track_window_move(mode)
                return
            if state in (FocusState.INVALID,FocusState.MOVED):
                self.stop(mode)
                self.pages[mode].set_status('框選視窗已關閉或位置／大小改變，請重新框選。',True)
                return
            self.focus_modes.add(mode)
            self.focus_timer.start()
            if state!=FocusState.ACTIVE:
                if not continuous:self.focus_pending_once.add(mode)
                self._pause_for_focus(mode)
                return
            guard=FocusGuard(self.window_focus,binding)
            self.focus_guards[mode]=guard
        self.focus_paused.discard(mode)
        self.focus_pending_once.discard(mode)
        self._clear_capture_overlay(mode)
        if continuous:self.controller.monitor(mode,self.regions[mode],focus_guard=guard)
        else:self.controller.submit_region(mode,self.regions[mode],focus_guard=guard)

    def _pause_for_focus(self, mode):
        if mode in self.focus_paused:return
        self.controller.cancel(mode,release_model=False)
        self.focus_paused.add(mode)
        self.set_busy(mode,False)
        self._clear_capture_overlay(mode)
        if mode==Mode.CHAT:self.chat_messages.clear()
        self.controller.metrics.add('window_focus_paused',mode)
        self.pages[mode].set_status('自動暫停 · 回到框選視窗後恢復。')

    def _track_window_move(self, mode):
        relocated=self.window_focus.relocated(self.window_bindings[mode],self.regions[mode])
        if relocated is None:
            self.stop(mode)
            self.pages[mode].set_status('框選視窗尺寸、縮放或螢幕改變，請重新框選。',True)
            return
        self.focus_modes.add(mode)
        self.focus_timer.start()
        self._pause_for_focus(mode)
        pending=self.focus_moves.get(mode)
        now=time.monotonic()
        if pending is None or pending[0]!=relocated:
            self.focus_moves[mode]=(relocated,now)
            self.pages[mode].set_status('自動暫停 · 等待視窗位置穩定…')
            return
        if now-pending[1]<.2:return
        if self.controller.working(mode):return
        self.window_bindings[mode],self.regions[mode]=relocated
        self.focus_moves.pop(mode,None)
        self.controller.metrics.add('window_region_relocated',mode)
        self.pages[mode].set_status('框選已跟隨視窗 · 正在辨識目前畫面…')
        self._start_region_work(mode,continuous=True)

    def check_window_focus(self):
        from .window_focus import FocusState
        if self.closing:return
        for mode in tuple(self.focus_modes):
            binding=self.window_bindings.get(mode)
            if binding is None:continue
            state=self.window_focus.state(binding)
            if state==FocusState.MOVED and mode in self.monitoring:
                self._track_window_move(mode)
                continue
            self.focus_moves.pop(mode,None)
            if state in (FocusState.INVALID,FocusState.MOVED):
                self.stop(mode)
                self.pages[mode].set_status('框選視窗已關閉或位置／大小改變，請重新框選。',True)
                continue
            guard=self.focus_guards.get(mode)
            interrupted=guard is not None and guard.interrupted.is_set()
            if state!=FocusState.ACTIVE or interrupted:
                if mode not in self.monitoring and mode not in self.focus_pending_once:
                    # A one-shot card is cancelled, never recaptured on return.
                    self.stop(mode,release_model=False)
                    self.pages[mode].set_status('已移除覆蓋 · 回到遊戲後可重新框選／辨識。')
                    continue
                self._pause_for_focus(mode)
            if state==FocusState.ACTIVE and mode in self.focus_paused:
                self.controller.metrics.add('window_focus_resumed',mode)
                self.pages[mode].set_status('已恢復 · 正在辨識目前畫面…')
                self._start_region_work(mode,continuous=mode in self.monitoring)
        if not self.focus_modes:self.focus_timer.stop()

    def translate_text(self, mode):
        if mode in self.busy_modes:
            return
        self.stop(mode,release_model=False)
        self.pages[mode].set_status('正在翻譯…')
        self.controller.submit_text(mode,self.pages[mode].source.toPlainText())

    def capture_once(self, mode):
        if mode not in self.regions:
            self.pages[mode].set_status('請先框選卡片文字區。',True)
            return
        self.stop(mode,release_model=False)
        if mode in (Mode.EQUIPMENT,Mode.QUEST) or mode in self.window_bindings:self.showMinimized()
        self._start_region_work(mode,continuous=False)

    def toggle_monitor(self, mode):
        if mode in (Mode.EQUIPMENT,Mode.QUEST):
            self.capture_once(mode)
            return
        if mode in self.monitoring:
            self.stop(mode)
        elif mode in self.regions:
            self.monitoring.add(mode)
            region=self.regions[mode]
            self.pages[mode].region_label.setText(f'框選範圍 {region.width} × {region.height} px'+(' · 固定卡片文字區' if mode==Mode.EQUIPMENT else ''))
            self.pages[mode].monitor_button.setText('停止跟讀' if mode==Mode.EQUIPMENT else '停止監測')
            self._start_region_work(mode,continuous=True)
        else:
            self.pages[mode].set_status('請先框選文字範圍。',True)

    def stop(self, mode, release_model=True):
        self.controller.cancel(mode,release_model=release_model)
        self.monitoring.discard(mode)
        self.focus_modes.discard(mode)
        self.focus_paused.discard(mode)
        self.focus_pending_once.discard(mode)
        self.focus_guards.pop(mode,None)
        self.focus_moves.pop(mode,None)
        if not self.focus_modes:self.focus_timer.stop()
        if hasattr(self.pages.get(mode),'monitor_button'):
            self.pages[mode].monitor_button.setText('開始跟讀' if mode==Mode.EQUIPMENT else '開始監測')
        self.set_busy(mode,False)
        self._clear_capture_overlay(mode)

    def job_started(self, identifier, generation):
        mode = Mode(identifier)
        if self.controller.current(mode,generation):
            self.set_busy(mode,True)

    def job_finished(self, identifier, generation):
        mode = Mode(identifier)
        if self.controller.current(mode,generation) and mode not in self.monitoring:
            self.set_busy(mode,False)

    def set_busy(self, mode, busy):
        if busy:self.busy_modes.add(mode)
        else:self.busy_modes.discard(mode)
        page = self.pages[mode]
        page.translate_button.setEnabled(not busy)
        text = '翻成英文' if mode==Mode.REPLY else '核對後重新翻譯' if not page.ocr_note.isHidden() else '翻譯輸入文字'
        page.translate_button.setText('正在監測…' if busy and mode in self.monitoring else '正在處理…' if busy else text)
        if mode==Mode.REPLY and self.reply_window:
            self.reply_window.translate_button.setEnabled(not busy)
            self.reply_window.translate_button.setText('正在處理…' if busy else '翻成英文')

    def clear_workspace(self, mode):
        self.stop(mode)
        page = self.pages[mode]
        page.source.clear()
        page.target.clear()
        page.ocr_note.hide()
        self.capture_evidence.pop(mode,None)
        if mode in self.review_dialogs:
            self.review_dialogs[mode].close()
        if hasattr(page,'review_button'):
            page.review_button.setEnabled(False)
        if hasattr(page,'cells'):
            page.cells.setRowCount(0)
        if mode == Mode.CHAT:
            self.chat_messages.clear()
        if mode in self.overlays:
            self.overlays[mode].set_text('')
            self.overlays[mode].set_warning('')
            self.overlays[mode].hide()
        if mode == Mode.REPLY and self.reply_window:
            self.reply_window.source.clear()
            self.reply_window.target.clear()

    def set_status(self, identifier, message, generation):
        mode = Mode(identifier)
        if mode in self.focus_paused:return
        if not self.controller.current(mode,generation):
            return
        self.pages[mode].set_status(message)
        if mode == Mode.REPLY and self.reply_window:
            self.reply_window.status.setText(message)

    def receive_status(self, identifier):
        row = self.controller.take_status(identifier)
        if row:self.set_status(*row)

    def receive_capture(self, snapshot):
        if snapshot is None:snapshot = self.controller.take_capture()
        if snapshot is None:return
        if self.controller.current(snapshot.mode,snapshot.generation):
            self.capture_evidence.clear()
            for page in self.pages.values():
                if hasattr(page,'review_button'):page.review_button.setEnabled(False)
            self.capture_evidence[snapshot.mode] = snapshot
            self.pages[snapshot.mode].review_button.setEnabled(True)

    def show_capture_review(self, mode):
        snapshot = self.capture_evidence.get(mode)
        if snapshot is None:
            return
        if mode in self.review_dialogs:
            self.review_dialogs[mode].raise_()
            self.review_dialogs[mode].activateWindow()
            return
        for dialog in list(self.review_dialogs.values()):dialog.close()
        from .review_ui import CaptureReview
        dialog = CaptureReview(snapshot,self.settings.ocr_review_threshold,self)
        self.review_dialogs[mode] = dialog
        dialog.destroyed.connect(lambda _=None,m=mode:self.review_dialogs.pop(m,None))
        dialog.show()

    def failed(self, identifier, message, generation):
        mode = Mode(identifier)
        if not self.controller.current(mode,generation):
            return
        self.stop(mode)
        self.pages[mode].set_status(message,True)
        if mode == Mode.REPLY and self.reply_window:
            self.reply_window.status.setText(message)

    def receive(self, result):
        if isinstance(result,Mode):result = self.controller.take_result(result)
        if result is None:return
        if not self.controller.displayable(result):
            self.controller.metrics.add('ui_slot_suppressed',result.mode)
            if result.mode in self.focus_modes:self.check_window_focus()
            return
        ui_started = time.perf_counter()
        page = self.pages[result.mode]
        if result.mode in (Mode.DIALOG,Mode.EQUIPMENT,Mode.QUEST) and not result.translations:
            page.source.clear()
            page.target.clear()
            page.ocr_note.hide()
            if hasattr(page,'cells'):page.cells.setRowCount(0)
            if result.mode in self.overlays:
                self.overlays[result.mode].set_text('')
                self.overlays[result.mode].set_warning('')
                self.overlays[result.mode].hide()
            return
        if result.mode == Mode.CHAT:
            self.chat_messages.extend(t.target for t in result.translations if t.target and not t.warning)
            self.chat_messages = self.chat_messages[-100:]
            target = '\n'.join(self.chat_messages)
        else:
            target = '\n'.join(t.target for t in result.translations if not t.warning)
        separator = '\n\n' if result.mode in (Mode.EQUIPMENT,Mode.QUEST) else '\n'
        page.source.setPlainText(separator.join(t.source for t in result.translations))
        page.target.setPlainText(target)
        if result.mode==Mode.CHAT:page.target.moveCursor(QTextCursor.MoveOperation.End)
        warnings = [t.warning for t in result.translations if t.warning]
        page.ocr_note.setText('需核對 · '+'\n'.join(dict.fromkeys(warnings)))
        page.ocr_note.setVisible(bool(warnings))
        hits = sum(t.cache_hit for t in result.translations)
        observed_ms = result.total_ms+(time.perf_counter()-result.emitted_at)*1000 if result.emitted_at else result.total_ms
        page.metrics.setText(f'觀測至介面 {observed_ms:.0f} ms · OCR {result.ocr_ms:.0f} ms · 快取 {hits}/{len(result.translations)}')
        page.metrics.setToolTip('自程式開始擷取／收到輸入至介面處理；不包含字幕出現前的掃描等待。')
        if hasattr(page,'cells'):
            populate(page.cells,[(t.source,t.target,(f'辨識信心 {t.ocr_confidence:.0%} · ' if t.ocr_confidence is not None else '')+(t.warning or t.origin)) for t in result.translations])
        if result.mode == Mode.REPLY:
            if self.reply_window:
                self.reply_window.target.setPlainText(target)
        else:
            overlay = self.overlay(result.mode)
            if isinstance(overlay,EquipmentOverlay):
                try:overlay.set_translations(result.translations,result.equipment_layout)
                except (ValueError,OSError) as error:
                    overlay.set_text('');overlay.render_warning=str(error)
                if overlay.render_warning:
                    page.ocr_note.setText(overlay.render_warning);page.ocr_note.show()
            elif isinstance(overlay,CardOverlay):overlay.set_translations(result.translations)
            else:
                overlay.set_text(target)
                overlay.set_warning('')
            if not target.strip() or (isinstance(overlay,EquipmentOverlay) and not overlay.renderable):overlay.hide()
            elif result.mode not in self.overlay_hidden:
                overlay.show()
                if result.mode==Mode.CHAT:
                    overlay.text.moveCursor(QTextCursor.MoveOperation.End)
                    overlay.text.ensureCursorVisible()
                if isinstance(overlay,EquipmentOverlay) and overlay.render_warning:
                    page.ocr_note.setText(overlay.render_warning);page.ocr_note.show()
        self.controller.metrics.add('ui_applied',result.mode,
            overlay_update_ms=(time.perf_counter()-ui_started)*1000,observed_pipeline_ms=observed_ms)
        # History/dictionary widgets are populated when opened, not each subtitle.
        if self.stack.currentIndex() in (6,7):self.refresh_data()

    def overlay(self, mode):
        if mode not in self.overlays:
            if mode in (Mode.EQUIPMENT,Mode.QUEST):
                widget=EquipmentOverlay(LABELS[mode],self.settings.font_size)
                widget.hidden_by_user.connect(lambda m=mode:self.overlay_hidden.add(m))
                self.overlays[mode]=widget
                return widget
            cls = CardOverlay if mode==Mode.QUEST else Overlay
            widget = cls(LABELS[mode],self.settings.font_size)
            widget.hidden_by_user.connect(lambda m=mode:self.overlay_hidden.add(m))
            geometry = QApplication.primaryScreen().availableGeometry()
            widget.move(geometry.center().x()-widget.width()//2,geometry.bottom()-widget.height()-70)
            widget.restore_state(self.settings.overlays.get(mode.value,{}))
            self.overlays[mode] = widget
            timer = QTimer(self)
            timer.setSingleShot(True);timer.setInterval(250)
            timer.timeout.connect(lambda m=mode:self.save_overlay(m))
            self.overlay_timers[mode] = timer
            widget.geometry_changed.connect(timer.start)
        return self.overlays[mode]

    def save_overlay(self, mode):
        if mode in (Mode.EQUIPMENT,Mode.QUEST):return
        self.settings.overlays[mode.value] = self.overlays[mode].state()
        try:
            save_settings(self.root,self.settings)
        except (OSError,ValueError) as error:
            self.pages[mode].set_status('浮層設定無法儲存：'+str(error),True)

    def toggle_overlay(self, mode=Mode.DIALOG):
        if mode in self.focus_modes:
            self.check_window_focus()
            if mode in self.focus_paused or mode not in self.focus_modes:return
        widget = self.overlay(mode)
        if mode in (Mode.EQUIPMENT,Mode.QUEST) and not widget.renderable:return
        visible = not widget.isVisible()
        self.overlay_hidden.discard(mode) if visible else self.overlay_hidden.add(mode)
        widget.setVisible(visible)

    def interact_overlay(self, mode):
        self.overlay_hidden.discard(mode)
        self.overlay(mode).set_passthrough(False)

    def show_reply(self):
        if self.reply_window is None:
            self.reply_window = ReplyWindow(self)
        self.reply_window.show()
        self.reply_window.raise_()
        self.reply_window.source.setFocus()

    def handle_hotkey(self, action):
        if action.startswith('select_'):
            self.select_region(Mode(action[7:]))
        elif action == 'toggle_dialog':
            self.toggle_monitor(Mode.DIALOG)
        elif action == 'toggle_equipment':
            self.toggle_overlay(Mode.EQUIPMENT)
        elif action == 'toggle_overlay':
            self.toggle_overlay()
        elif action == 'toggle_background':
            self.overlay(Mode.DIALOG).toggle_background()
        elif action == 'show_reply':
            self.show_reply()

    def showEvent(self, event):
        super().showEvent(event)
        exclude_capture(self)

    def closeEvent(self, event):
        self.idle_timer.stop()
        self.focus_timer.stop()
        self.asset_panel.shutdown()
        self.closing = True
        self.hotkeys.close()
        self._close_pickers()
        for mode,timer in self.overlay_timers.items():
            timer.stop()
            self.save_overlay(mode)
        for overlay in self.overlays.values():
            overlay.close()
        if self.reply_window:
            self.reply_window.close()
        for dialog in list(self.review_dialogs.values()):
            dialog.close()
        self.capture_evidence.clear()
        self.controller.close()
        event.accept()
