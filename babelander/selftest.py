"""Exercise bundled Qt, OCR and real external llama.cpp without user data."""
from pathlib import Path
import argparse
from dataclasses import asdict
import json
import os
import sys
import tempfile
import time


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--report',required=True)
    arguments = parser.parse_args()
    from .windows import dpi_aware
    dpi_aware()
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QImage,QPainter,QFont,QColor,QFontDatabase
    import numpy as np
    from .settings import Settings
    from .storage import Store
    from .security import KeyVault
    from .engine import Engine
    from .controller import Controller
    from .window import MainWindow
    from .ocr import OCR
    from .types import Mode,Cancellation,OCRLine,Region
    from .layout import card_blocks,OCRBlock
    from .equipment_layout import capture_layout
    from .equipment_overlay import EquipmentOverlay
    from . import __version__
    app = QApplication(['Babelander2-self-test'])
    if app.platformName()=='offscreen':
        font_root=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
        for name in ('arial.ttf','segoeui.ttf','msjh.ttc'):
            if (font_root/name).is_file():QFontDatabase.addApplicationFont(str(font_root/name))
    app.setStyle('Fusion')
    app.setStyleSheet(Path(__file__).with_name('theme.qss').read_text(encoding='utf-8'))
    checks,rows = {},[]
    report = {'version':__version__,'frozen':bool(getattr(sys,'frozen',False)),'qt_platform':app.platformName(),
              'checks':checks,'translations':rows,'real_desktop_capture':False}
    with tempfile.TemporaryDirectory(prefix='Babelander2-bundle-') as directory:
        settings = Settings(model_path=os.environ.get('BABELANDER_V2_MODEL',''),server_path=os.environ.get('BABELANDER_V2_SERVER',''))
        settings.hotkeys={}
        store = Store(directory)
        vault = KeyVault(directory)
        engine = Engine(settings,store,vault,directory)
        controller = Controller(engine,store,settings)
        window = None
        try:
            window = MainWindow(controller,store,settings,vault,directory)
            window.show()
            app.processEvents()
            checks['native_ui_nine_pages'] = window.stack.count()==9
            window.grab().save(str(Path(arguments.report).with_suffix('.png')))
            image = QImage(1100,110,QImage.Format.Format_RGB32)
            image.fill(QColor('white'))
            painter = QPainter(image)
            painter.setPen(QColor('black'));painter.setFont(QFont('Arial',30))
            painter.drawText(24,68,'Alice, we must leave before sunset.')
            painter.end()
            pixels = np.frombuffer(image.bits(),dtype=np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)[:,:image.width(),:3].copy()
            bundled_ocr=OCR()
            lines = bundled_ocr.recognize(pixels,Cancellation())
            source = ' '.join(line.text for line in lines)
            checks['bundled_ocr'] = 'before sunset' in source
            from .chat_ocr import ChatRecognitionCache
            chat_cache=ChatRecognitionCache()
            bundled_ocr.recognize(pixels,Cancellation(),chat_cache=chat_cache)
            repeated=bundled_ocr.recognize(pixels,Cancellation(),chat_cache=chat_cache)
            checks['bundled_chat_recognition_reuse']=(' '.join(line.text for line in repeated)==source
                and chat_cache.last.get('reused',0)>0 and bundled_ocr.engine.chat_context is None)
            chat_cache.clear()
            checks['bundled_chat_cache_cleanup']=not chat_cache.entries and not chat_cache.regions and chat_cache.current_regions is None
            from .evidence import evidence
            snapshot = evidence(Mode.DIALOG,controller.generations[Mode.DIALOG],pixels,lines)
            window.receive_capture(snapshot); window.show_capture_review(Mode.DIALOG)
            app.processEvents()
            review = window.review_dialogs[Mode.DIALOG]
            review.zoom.setCurrentIndex(4)
            checks['bundled_capture_review'] = 'sunset' in review.text.toPlainText() and review.image.width()==snapshot.preview_width*2
            review.edit_source(); app.processEvents()
            checks['bundled_review_edit_source'] = 'sunset' in window.pages[Mode.DIALOG].source.toPlainText()
            overlay=window.overlay(Mode.DIALOG);overlay.set_text('透明背景測試');overlay.show();app.processEvents()
            opaque=overlay.grab().toImage().pixelColor(4,90).alpha()
            overlay.set_background(False);app.processEvents()
            checks['genuine_transparent_overlay']=opaque>200 and overlay.grab().toImage().pixelColor(4,90).alpha()==0 and overlay.windowOpacity()==1
            overlay.hide()
            def line(text,y):return OCRLine(text,((0,y),(600,y),(600,y+20),(0,y+20)),.99)
            blocks=card_blocks([line('If health is below 30%,',0),line('gain +12% Movement Speed for 5 seconds.',28),line('Otherwise, gain +3% Fire Resistance.',56)])
            translated=controller._translate_blocks(Mode.EQUIPMENT,Cancellation(),blocks)
            checks['conditional_paragraph']=len(translated)==1 and '否則' in translated[0].target and not translated[0].warning
            card=window.overlay(Mode.EQUIPMENT)
            backdrop=np.full((200,700,3),28,np.uint8)
            position=Region(20,50,700,200)
            card.set_translations(translated,capture_layout(position,backdrop,blocks))
            checks['card_overlay']=isinstance(card,EquipmentOverlay) and card.renderable and translated[0].target in card.text.toPlainText() and translated[0].source not in card.text.toPlainText()
            card.show();app.processEvents()
            checks['equipment_original_roi']=card.x()==20 and card.y()==50 and card.width()==700 and card.height()==200
            checks['equipment_single_shot_controls']=not hasattr(window.pages[Mode.EQUIPMENT],'monitor_button') and Mode.EQUIPMENT not in window.overlay_timers
            card.grab().save(str(Path(arguments.report).with_name('equipment-original-roi.png')))
            card.hide()
            quest=window.overlay(Mode.QUEST)
            quest.set_translations(translated,capture_layout(position,backdrop,blocks))
            quest.show();app.processEvents()
            checks['quest_original_roi']=quest.renderable and [quest.x(),quest.y(),quest.width(),quest.height()]==[20,50,700,200]
            checks['quest_single_shot_controls']=hasattr(window.pages[Mode.QUEST],'once_button') and not hasattr(window.pages[Mode.QUEST],'monitor_button') and Mode.QUEST not in window.overlay_timers
            quest.hide()
            checks['quest_exact_label_rule']=engine.request('Objectives',Mode.QUEST,Cancellation()).target=='任務目標'
            low=controller._translate_blocks(Mode.SCREEN,Cancellation(),[OCRBlock((OCRLine('Wait for me.',(),.52),))])[0]
            checks['ocr_review_guard']=not low.target and bool(low.warning) and low.ocr_confidence==.52
            checks['asset_download_panel']=window.asset_panel.start_button.isEnabled() and not window.asset_panel.cancel_button.isEnabled()
            checks['idle_unload_control']=window.idle_unload.value()==300 and window.idle_timer.isActive()
            checks['subtitle_speed_controls']=window.ocr_threads.currentData()==settings.ocr_threads and window.reuse_lines.isChecked()==settings.reuse_dialogue_lines
            checks['chat_observation_control']=window.chat_scan.value()==settings.chat_scan_ms and settings.chat_scan_ms>=100
            checks['bundled_traditional_conversion']=engine.chinese.convert('将在 10 秒后返回。')=='將在 10 秒後返回。'
            checks['manual_preload_controls']=window.prepare_button.isEnabled() and not window.prepare_cancel.isEnabled()
            window.prepare_model()
            preload_deadline=time.monotonic()+65
            while not window.prepare_button.isEnabled() and time.monotonic()<preload_deadline:
                app.processEvents();time.sleep(.005)
            checks['bundled_manual_model_preload']='已就緒' in window.model_status.text() and engine.local.process is not None
            preloaded_process=engine.local.process
            store.clear_cache()
            for mode,text in ((Mode.DIALOG,source),(Mode.EQUIPMENT,'Gain +50% Fire Resistance for 10 seconds.'),
                              (Mode.REPLY,'我五分鐘後回來，請不要開始。')):
                started = time.perf_counter()
                result = engine.request(text,mode,Cancellation())
                rows.append({'mode':mode.value,**asdict(result),'total_ms':round((time.perf_counter()-started)*1000,2)})
                checks['translate_'+mode.value] = not result.warning and result.target!=text
            checks['preloaded_model_reused']=engine.local.process is preloaded_process and rows[0]['backend_state']=='warm'
            before_private={table:store.db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('cache','history','usage')}
            shorthand=engine.request('GG',Mode.CHAT,Cancellation())
            checks['chat_shorthand_retained']=shorthand.target=='GG' and not shorthand.warning and shorthand.model_ms==0
            mixed=engine.request('我需要 potion x4',Mode.CHAT,Cancellation())
            checks['chat_mixed_quantity_rule']=mixed.target=='我需要 藥水 x4' and not mixed.warning and mixed.model_ms==0
            chat=engine.request('I need potions x4.',Mode.CHAT,Cancellation())
            checks['chat_real_quantity_translation']=not chat.warning and '4' in chat.target
            checks['chat_no_persistent_text']=before_private=={table:store.db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('cache','history','usage')}
            checks['chat_reservation_intent']=engine.request('Save one potion for me.',Mode.CHAT,Cancellation()).target=='留一個藥水給我。'
            checks['chat_priority_intent']=engine.request('Focus the healer first.',Mode.CHAT,Cancellation()).target=='優先集火補師。'
            prohibition=engine.request('Do not cross the river yet.',Mode.DIALOG,Cancellation())
            checks['dialog_prohibition_intent']=prohibition.target=='暫時不要越過河流。' and not prohibition.warning
            from .validation import validate
            try:
                validate('請等我6分鐘，不要開始。','Please wait 6 minutes before starting.',reply=True)
                checks['reply_deferred_start_guard']=True
            except ValueError:checks['reply_deferred_start_guard']=False
            checks['zero_legacy_application_imports'] = not any(n=='gamelens' or n.startswith('gamelens.') for n in sys.modules)
            checks['zero_legacy_dependency_paths'] = not any('recovery/editable' in p.replace('\\','/') for p in sys.path)
        except Exception as error:
            report['error'] = {'type':type(error).__name__,'message':str(error)}
        finally:
            if window:window.close()
            controller.close();controller.join();store.close()
            checks['workers_stopped'] = all(not t.is_alive() for q in engine.queues.values() for t in q.threads)
    report['passed'] = bool(checks) and all(checks.values()) and 'error' not in report
    Path(arguments.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return int(not report['passed'])
