from pathlib import Path
import sys


def main():
    if '--soak-test' in sys.argv:
        from .soaktest import run
        return run()
    if '--self-test' in sys.argv:
        from .selftest import run
        return run()
    from .windows import dpi_aware
    dpi_aware()
    from PySide6.QtWidgets import QApplication,QMessageBox
    from .settings import data_root,load_settings
    from .storage import Store
    from .security import KeyVault
    from .engine import Engine
    from .controller import Controller
    from .window import MainWindow
    app = QApplication(sys.argv)
    app.setApplicationName('Babelander 2')
    app.setStyle('Fusion')
    app.setStyleSheet(Path(__file__).with_name('theme.qss').read_text(encoding='utf-8'))
    root = data_root()
    try:
        settings = load_settings(root)
    except (ValueError,TypeError) as error:
        QMessageBox.critical(None,'設定無法載入',str(error)+'\n請檢查 Babelander2/settings.json。')
        return 1
    store = Store(root)
    vault = KeyVault(root)
    engine = Engine(settings,store,vault,root)
    controller = Controller(engine,store,settings)
    window = MainWindow(controller,store,settings,vault,root)
    window.show()
    try:
        return app.exec()
    finally:
        controller.close()
        controller.join()
        store.close()
