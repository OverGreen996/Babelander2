from pathlib import Path
from PySide6.QtCore import QThread,Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QProgressBar
from .assets import install,ASSETS
from .types import Cancellation,Cancelled

class DownloadWorker(QThread):
    progress=Signal(str,int,int)
    completed=Signal(str,str)
    failed=Signal(str)
    def __init__(self,root,parent=None):
        super().__init__(parent);self.root=root;self.token=Cancellation()
    def run(self):
        try:
            model,server=install(self.root,self.token,self.progress.emit)
            self.completed.emit(model,server)
        except Cancelled:self.failed.emit('已取消；已下載部分保留，之後可續傳。')
        except Exception as error:
            message=str(error) if isinstance(error,ValueError) else '安裝失敗，請檢查空間、目錄權限或網路後再試。'
            self.failed.emit(message)

class AssetPanel(QWidget):
    installed=Signal(str,str)
    def __init__(self,root,parent=None):
        super().__init__(parent);self.root=Path(root);self.worker=None
        layout=QVBoxLayout(self);layout.setContentsMargins(0,8,0,12)
        title=QLabel('取得本機模型');title.setObjectName('brand');layout.addWidget(title)
        info=QLabel('Qwen3-1.7B Q4_K_M + llama.cpp b10896 CUDA 12.4 · 約 1.93 GB\n下載自 Hugging Face／llama.cpp，完成 SHA-256 驗證後才套入欄位；需 4 GB 可用空間。')
        info.setWordWrap(True);layout.addWidget(info)
        licenses=QLabel('<a href="https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF">模型與 Apache-2.0</a> · <a href="https://github.com/ggml-org/llama.cpp/releases/tag/b10896">llama.cpp / MIT</a> · <a href="https://docs.nvidia.com/cuda/eula/index.html">CUDA 條款</a>')
        licenses.setOpenExternalLinks(True);licenses.setWordWrap(True);layout.addWidget(licenses)
        buttons=QHBoxLayout();self.start_button=QPushButton('下載／續傳並驗證');self.cancel_button=QPushButton('取消下載')
        self.cancel_button.setEnabled(False);buttons.addWidget(self.start_button);buttons.addWidget(self.cancel_button);buttons.addStretch();layout.addLayout(buttons)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setValue(0);self.progress.setAccessibleName('本機資產下載進度');layout.addWidget(self.progress)
        self.status=QLabel('也可自行選擇現有 GGUF 與執行元件。');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.start_button.clicked.connect(self.start);self.cancel_button.clicked.connect(self.cancel)
    def start(self):
        if self.worker and self.worker.isRunning():return
        self.start_button.setEnabled(False);self.cancel_button.setEnabled(True)
        self.worker=DownloadWorker(self.root,self);self.worker.progress.connect(self.update_progress)
        self.worker.completed.connect(self.complete);self.worker.failed.connect(self.status.setText)
        self.worker.finished.connect(self.finish);self.worker.start()
    def update_progress(self,name,done,total):
        self.status.setText(name);self.progress.setValue(int(done*100/max(1,total)))
    def complete(self,model,server):
        self.status.setText('已下載、驗證並填入路徑；按下「儲存設定」即可使用。');self.installed.emit(model,server)
    def finish(self):
        self.start_button.setEnabled(True);self.cancel_button.setEnabled(False)
        worker=self.worker;self.worker=None
        if worker:worker.deleteLater()
    def cancel(self):
        if self.worker:
            self.worker.token.cancel();self.status.setText('正在取消下載…');self.cancel_button.setEnabled(False)
    def shutdown(self):
        if self.worker:
            self.worker.token.cancel();self.worker.wait()
