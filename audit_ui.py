"""Actual Qt, owned fixture window, desktop capture, OCR, model and picker."""
from bootstrap import prepare
prepare()
from pathlib import Path
from dataclasses import asdict,replace
import ctypes
import json
import sys
import time
import os
import threading
from unittest.mock import patch
import numpy as np

from babelander.windows import dpi_aware,exclude_capture
dpi_aware()
from PySide6.QtCore import Qt,QPoint,QTimer,QEventLoop
from PySide6.QtGui import QPainter,QFont,QColor,QImage
from PySide6.QtWidgets import QApplication,QWidget,QDialog,QSpinBox,QLabel,QFrame
from PySide6.QtTest import QTest
from babelander.settings import load_settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.controller import Controller
from babelander.window import MainWindow
from babelander.types import Mode

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'test-results/ui'
OUT.mkdir(parents=True,exist_ok=True)
app = QApplication.instance() or QApplication(['Babelander2 UI audit'])
app.setStyle('Fusion')
app.setStyleSheet((ROOT/'babelander/theme.qss').read_text(encoding='utf-8'))
settings = load_settings(OUT/'data')
settings.scan_ms = 300
settings.stable_ms = 150
if os.environ.get('BABELANDER_AUDIT_PARALLEL_SOAK')=='1':
    settings.hotkeys={name:'Ctrl+Alt+Shift+'+key.split('+')[-1] if key else '' for name,key in settings.hotkeys.items()}
store = Store(OUT/'data')
vault = KeyVault(OUT/'data')
engine = Engine(settings,store,vault,OUT/'data')
controller = Controller(engine,store,settings)
window = MainWindow(controller,store,settings,vault,OUT/'data')
errors,results = [],[]
controller.failed.connect(lambda mode,message,generation:errors.append((mode,message,generation)))
controller.result.connect(lambda result:results.append(result))


def events(ms=50):
    loop = QEventLoop()
    QTimer.singleShot(ms,loop.quit)
    loop.exec()


def until(predicate,timeout=15):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate():return
        events()
    raise AssertionError('UI timeout: '+repr(errors))


class SourceWindow(QWidget):
    def __init__(self):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('Synthetic OCR fixture · no user content')
        self.resize(1150,130)
        self.move(app.primaryScreen().availableGeometry().x()+40,app.primaryScreen().availableGeometry().y()+(400 if os.environ.get('BABELANDER_AUDIT_PARALLEL_SOAK')=='1' else 40))
        self.text = 'Alice, we must leave before sunset.'

    def paintEvent(self,event):
        painter = QPainter(self)
        painter.fillRect(self.rect(),QColor('white'))
        painter.setPen(QColor('black'))
        painter.setFont(QFont('Arial',28))
        for index,line in enumerate(self.text.split('\n')):
            painter.drawText(24,45+index*42 if '\n' in self.text else 75,line)


fixture = SourceWindow()
checks,shots = {},[]
capture_patch = None
render_timer = None
frame = [None]
synthetic_capture = os.environ.get('BABELANDER_V2_SYNTHETIC_CAPTURE') == '1'
if synthetic_capture:
    def render():
        image = fixture.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)
        frame[0] = np.frombuffer(image.bits(),dtype=np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)[:,:image.width(),:3].copy()
    def rendered_capture(region):
        return frame[0].copy()
    render_timer = QTimer()
    render_timer.timeout.connect(render)
    render_timer.start(50)
    capture_patch = patch('babelander.controller.capture',rendered_capture)
    capture_patch.start()
try:
    window.show()
    fixture.show()
    events(150)
    checks['main_capture_excluded'] = exclude_capture(window)
    window.select_region(Mode.DIALOG)
    until(lambda:bool(window.pickers))
    picker = next(p for p in window.pickers if p.screen_reference is app.primaryScreen())
    origin = picker.geometry().topLeft()
    start = fixture.mapToGlobal(QPoint(10,10))-origin
    finish = fixture.mapToGlobal(QPoint(1100,115))-origin
    QTest.mousePress(picker,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
    QTest.mouseMove(picker,finish,40)
    QTest.mouseRelease(picker,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,finish)
    print('selected_region',asdict(window.regions[Mode.DIALOG]),flush=True)
    until(lambda:any(r.mode == Mode.DIALOG and r.translations for r in results))
    checks['picker_ocr_translate_overlay'] = bool(window.pages[Mode.DIALOG].target.toPlainText()) and window.overlays[Mode.DIALOG].isVisible()
    checks['ocr_fixture_recognized'] = 'before sunset' in window.pages[Mode.DIALOG].source.toPlainText()
    until(lambda:Mode.DIALOG in window.capture_evidence)
    snapshot = window.capture_evidence[Mode.DIALOG]
    checks['capture_preview_real_roi_and_scores'] = snapshot.width>500 and any('sunset' in l.text and l.confidence>.7 for l in snapshot.lines)
    QTest.mouseClick(window.pages[Mode.DIALOG].review_button,Qt.MouseButton.LeftButton)
    events(80)
    review = window.review_dialogs[Mode.DIALOG]
    checks['capture_review_excluded_and_readonly'] = exclude_capture(review) and review.text.isReadOnly() and 'sunset' in review.text.toPlainText()
    review.zoom.setCurrentIndex(4); events(30)
    checks['capture_review_zoom_and_box_toggle'] = review.image.width()==snapshot.preview_width*2
    review.boxes.setChecked(False); events(30)
    review.zoom.setCurrentIndex(0); events(30)
    review.grab().save(str(OUT/'capture-review.png'))
    stale = replace(snapshot,generation=controller.generations[Mode.DIALOG]-1)
    window.receive_capture(stale)
    checks['stale_capture_cannot_replace_preview'] = window.capture_evidence[Mode.DIALOG] is snapshot
    QTest.mouseClick(review.edit_button,Qt.MouseButton.LeftButton); events(80)
    checks['capture_review_stops_then_edits_snapshot'] = Mode.DIALOG not in window.monitoring and 'sunset' in window.pages[Mode.DIALOG].source.toPlainText() and window.pages[Mode.DIALOG].translate_button.isEnabled()
    checks['capture_review_closed_releases_dialog'] = Mode.DIALOG not in window.review_dialogs
    checks['overlay_capture_excluded'] = exclude_capture(window.overlays[Mode.DIALOG])
    window.stop(Mode.DIALOG)
    region = window.regions[Mode.DIALOG]
    for mode,text in ((Mode.EQUIPMENT,'Gain +50% Fire Resistance for 10 seconds.'),
                      (Mode.QUEST,'Collect 3/10 moonstones before 01:30.')):
        fixture.text = text
        fixture.update()
        events(80)
        controller.submit_region(mode,region)
        until(lambda m=mode:any(r.mode==m for r in results))
        checks[mode.value+'_ocr_translation'] = bool(window.pages[mode].target.toPlainText())
    fixture.text = '[Party] Player_007: Wait for me.'
    fixture.update()
    events(80)
    window.regions[Mode.CHAT] = region
    window.toggle_monitor(Mode.CHAT)
    until(lambda:any(r.mode==Mode.CHAT for r in results))
    checks['chat_monitors_and_preserves_speaker'] = 'Player_007:' in window.pages[Mode.CHAT].target.toPlainText()
    window.stop(Mode.CHAT)
    for mode,text in ((Mode.REPLY,'我 5 分鐘後回來，請不要開始。'),
                      (Mode.SCREEN,'Please read the update notes before entering the dungeon.')):
        window.pages[mode].source.setPlainText(text)
        if mode == Mode.REPLY:
            QTest.keyClick(window.pages[mode].source,Qt.Key.Key_Return)
        else:
            window.pages[mode].translate_button.click()
        until(lambda m=mode:any(r.mode==m for r in results))
        checks[mode.value+'_ui_translation'] = bool(window.pages[mode].target.toPlainText())
    window.show_reply()
    window.reply_window.source.setPlainText('我 5 分鐘後回來，請不要開始。')
    QTest.keyClick(window.reply_window.source,Qt.Key.Key_Return)
    until(lambda:bool(window.reply_window.target.toPlainText()))
    checks['reply_popup_enter_and_draft'] = '5 minutes' in window.reply_window.target.toPlainText()
    window.reply_window.hide()
    checks['reply_draft_survives_hide'] = bool(window.reply_window.source.toPlainText())
    # Real multi-line OCR: a condition and its otherwise branch are one card.
    from babelander.types import Region,OCRLine,Translation,JobResult,Cancellation
    from babelander.layout import OCRBlock
    fixture.resize(1150,235)
    fixture.text='If health is below 30%,\ngain +12% Movement Speed for 5 seconds.\nOtherwise, gain +3% Fire Resistance.\nGain +50% Fire Resistance for 10 seconds.'
    fixture.update();events(200)
    origin=fixture.mapToGlobal(QPoint(10,10))
    multi=Region(origin.x(),origin.y(),1090,215)
    before_count=len(results);controller.submit_region(Mode.EQUIPMENT,multi)
    until(lambda:len(results)>before_count)
    card_result=results[-1]
    checks['real_ocr_wrapped_condition_retains_otherwise']=len(card_result.translations)==2 and '否則' in card_result.translations[0].target and not any(t.warning for t in card_result.translations)
    card=window.overlay(Mode.EQUIPMENT)
    window.stack.setCurrentIndex(1);window.resize(1190,860);events(40)
    window.grab().save(str(OUT/'equipment-workspace.png'))
    checks['card_overlay_has_source_target_and_confidence']=len(card.text.findChildren(QFrame,'overlayCard'))==2 and '+12%' in card.text.toPlainText() and len(card.text.findChildren(QLabel,'overlaySource'))==2
    events(80);card.grab().save(str(OUT/'card-overlay.png'));card.hide()
    overlay=window.overlay(Mode.DIALOG);overlay.show();events(80)
    opaque=overlay.grab().toImage().pixelColor(4,90).alpha()
    overlay.background_button.click();events(80)
    transparent=overlay.grab().toImage().pixelColor(4,90).alpha()
    checks['genuine_transparency_retains_full_text_opacity']=opaque>200 and transparent==0 and overlay.windowOpacity()==1 and bool(overlay.text.toPlainText())
    overlay.grab().save(str(OUT/'transparent-overlay.png'))
    before_position=overlay.pos();at=QPoint(12,12)
    QTest.mousePress(overlay.caption,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,at)
    QTest.mouseMove(overlay.caption,at+QPoint(25,20),30)
    QTest.mouseRelease(overlay.caption,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,at+QPoint(25,20))
    checks['overlay_title_drag_moves_window']=overlay.pos()!=before_position
    def accept_geometry():
        dialog=QApplication.activeModalWidget()
        if not isinstance(dialog,QDialog):return
        fields={f.accessibleName():f for f in dialog.findChildren(QSpinBox)}
        fields['寬度'].setValue(820);fields['高度'].setValue(280)
        fields['水平位置'].setValue(app.primaryScreen().availableGeometry().x()+150)
        fields['垂直位置'].setValue(app.primaryScreen().availableGeometry().y()+350)
        dialog.accept()
    QTimer.singleShot(80,accept_geometry);overlay.adjust_button.click();events(350)
    checks['keyboard_geometry_dialog_resizes']=overlay.width()==820 and overlay.height()==280
    restored=load_settings(OUT/'data')
    checks['overlay_geometry_background_persisted']=restored.overlays[Mode.DIALOG.value]==overlay.state() and not restored.overlays[Mode.DIALOG.value]['background']
    overlay.restore_state({'x':49000,'y':49000,'width':680,'height':240,'background':True})
    checks['disconnected_screen_position_recovers']=any((overlay.geometry() & s.availableGeometry()).width()>=240 for s in app.screens())
    # Controlled low-confidence metadata: UI warns and original remains editable.
    block=OCRBlock((OCRLine('Wait for me.',(),.52),))
    translations=controller._translate_blocks(Mode.EQUIPMENT,Cancellation(),[block])
    generation=controller.generations[Mode.EQUIPMENT]
    window.receive(JobResult(Mode.EQUIPMENT,generation,translations,0,0));window.set_busy(Mode.EQUIPMENT,False)
    checks['low_confidence_ui_editable_and_warns']=not window.pages[Mode.EQUIPMENT].ocr_note.isHidden() and not window.pages[Mode.EQUIPMENT].source.isReadOnly() and window.pages[Mode.EQUIPMENT].translate_button.text()=='核對後重新翻譯'
    window.receive(JobResult(Mode.SCREEN,controller.generations[Mode.SCREEN],translations,0,0))
    checks['generic_overlay_shows_review_warning']=not window.overlay(Mode.SCREEN).warning.isHidden() and '52%' in window.overlay(Mode.SCREEN).warning.text()
    # Enter while busy cannot overwrite the draft or replace the current job.
    entered,release=threading.Event(),threading.Event()
    def delayed(system,text):
        entered.set();release.wait(3);return 'Please return in 7 minutes. Do not start.'
    try:
        with patch.object(engine.local,'translate',side_effect=delayed):
            window.show_reply();window.reply_window.source.setPlainText('請在 7 分鐘後回來，不要開始。')
            QTest.keyClick(window.reply_window.source,Qt.Key.Key_Return);until(entered.is_set)
            generation=controller.generations[Mode.REPLY]
            QTest.keyClick(window.reply_window.source,Qt.Key.Key_Return)
            checks['busy_enter_does_not_submit_duplicate']=controller.generations[Mode.REPLY]==generation and not window.reply_window.translate_button.isEnabled()
            release.set();until(lambda:Mode.REPLY not in window.busy_modes)
            checks['busy_button_restored_after_completion']=window.reply_window.translate_button.isEnabled()
    finally:release.set()
    window.reply_window.hide();card.hide()
    checks['idle_model_control_available']=window.idle_unload.value()==settings.idle_unload_seconds and window.idle_timer.isActive()
    window.overlay(Mode.DIALOG).set_passthrough(True)
    checks['overlay_passthrough'] = window.overlay(Mode.DIALOG).transparent_input
    window.interact_overlay(Mode.DIALOG)
    checks['overlay_interaction_restored'] = not window.overlay(Mode.DIALOG).transparent_input
    checks['hotkeys_registered'] = len(window.hotkeys.actions)>=7
    before = window.overlay(Mode.DIALOG).isVisible()
    hotkey_id = next(k for k,v in window.hotkeys.actions.items() if v=='toggle_overlay')
    ctypes.windll.user32.PostThreadMessageW(ctypes.windll.kernel32.GetCurrentThreadId(),0x312,hotkey_id,0)
    until(lambda:window.overlay(Mode.DIALOG).isVisible()!=before,2)
    checks['native_hotkey_dispatch'] = True
    # A manually hidden overlay must stay hidden while monitoring continues.
    dialog_result = next(r for r in reversed(results) if r.mode==Mode.DIALOG and r.translations)
    from dataclasses import replace
    dialog_result = replace(dialog_result,generation=controller.generations[Mode.DIALOG])
    controller.closed = False
    window.overlay(Mode.DIALOG).hide_by_user()
    window.receive(dialog_result)
    checks['hidden_overlay_stays_hidden_on_new_result'] = not window.overlay(Mode.DIALOG).isVisible()
    window.toggle_overlay(Mode.DIALOG)
    checks['hidden_overlay_can_be_restored'] = window.overlay(Mode.DIALOG).isVisible()
    window.clear_workspace(Mode.CHAT)
    checks['clear_releases_capture_preview'] = Mode.CHAT not in window.capture_evidence and not window.pages[Mode.CHAT].review_button.isEnabled()
    checks['clear_chat_removes_session_messages_and_overlay'] = not window.chat_messages and not window.pages[Mode.CHAT].target.toPlainText() and not window.overlay(Mode.CHAT).isVisible()
    before = controller.generations[Mode.DIALOG]
    window.failed(Mode.DIALOG.value,'Old queued failure',before-1)
    checks['stale_failure_cannot_cancel_new_generation'] = controller.generations[Mode.DIALOG]==before
    window.pages[Mode.DIALOG].set_status('翻譯完成 · 可核對原文與譯文')
    window.set_status(Mode.DIALOG.value,'Old queued status',before-1)
    checks['stale_status_cannot_replace_current_status'] = window.pages[Mode.DIALOG].status.text()=='翻譯完成 · 可核對原文與譯文'
    for overlay in window.overlays.values():overlay.hide()
    fixture.hide()
    window.reply_window.hide()
    window.show()
    for width,height in ((1190,860),(880,680)):
        window.resize(width,height)
        for index in range(window.stack.count()):
            nav = window.navigation.button(index)
            nav.setFocus()
            QTest.keyClick(nav,Qt.Key.Key_Space)
            events(40)
            checks[f'keyboard_{index}_{width}'] = window.stack.currentIndex()==index and nav.isChecked()
            filename = f'{width}-page-{index}.png'
            window.grab().save(str(OUT/filename))
            scroll = window.stack.currentWidget()
            shots.append({'page':index,'width':width,'file':filename,'scroll_max':scroll.verticalScrollBar().maximum()})
            if width==880 and scroll.verticalScrollBar().maximum():
                scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                events(20)
                window.grab().save(str(OUT/f'{width}-page-{index}-bottom.png'))
                scroll.verticalScrollBar().setValue(0)
    checks['zero_legacy_imports'] = not any(n=='gamelens' or n.startswith('gamelens.') for n in sys.modules)
    checks['zero_ui_errors'] = not errors
finally:
    fixture.close()
    window.close()
    controller.join()
    checks['all_workers_stopped'] = all(not t.is_alive() for queue in engine.queues.values() for t in queue.threads)
    checks['window_closed'] = not window.isVisible()
    store.close()
    if render_timer:render_timer.stop()
    if capture_patch:capture_patch.stop()
report = {'passed':all(checks.values()),'checks':checks,'errors':errors,'screenshots':shots,
          'results':[{'mode':r.mode.value,'total_ms':r.total_ms,'ocr_ms':r.ocr_ms,
                      'translations':[asdict(t) for t in r.translations]} for r in results],
          'real_desktop_capture':not synthetic_capture,
          'concurrent_soak':os.environ.get('BABELANDER_AUDIT_PARALLEL_SOAK')=='1',
          'capture':'Owned fixture rendering injected because input desktop is Screen-saver; real desktop capture is NOT verified' if synthetic_capture else 'Only synthetic fixture region captured from real desktop; no user game or other desktop content exported'}
(OUT/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed':report['passed'],'checks':checks,'errors':errors},ensure_ascii=False,indent=2))
raise SystemExit(not report['passed'])
