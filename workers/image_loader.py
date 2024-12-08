# workers/image_loader.py

from PyQt5.QtCore import QObject, pyqtSignal, QRunnable
from PyQt5.QtGui import QPixmap
from utils.constants import SUPPORTED_IMAGE_FORMATS, UNIFORM_HEIGHT

class ImageLoadSignals(QObject):
    finished = pyqtSignal(str, str, QPixmap, float)  # folder_path, filepath, pix, scale_factor
    error = pyqtSignal(str, Exception)
    progress = pyqtSignal(int)

class ImageLoadWorker(QRunnable):
    def __init__(self, folder_path, filepaths):
        super().__init__()
        self.folder_path = folder_path
        self.filepaths = filepaths
        self.signals = ImageLoadSignals()

    def run(self):
        total = len(self.filepaths)
        for i, filepath in enumerate(self.filepaths):
            try:
                pix = QPixmap(filepath)
                if pix.isNull():
                    raise ValueError(f"Could not load image: {filepath}")
                
                scale_factor = UNIFORM_HEIGHT / pix.height()
                self.signals.finished.emit(self.folder_path, filepath, pix, scale_factor)
                
                progress = int((i + 1) / total * 100)
                self.signals.progress.emit(progress)
            except Exception as e:
                self.signals.error.emit(filepath, e)
