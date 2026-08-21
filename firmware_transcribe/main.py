"""Entry point GUI — Mesin Transcribe firmware.

Jalankan dengan venv python (TANPA pattern re-exec — R-13 kajian):
    .venv\\Scripts\\python.exe main.py
"""

import sys

from PySide6.QtWidgets import QApplication

# WDAC patch paling awal (R-02): sebelum import faster_whisper manapun.
# faster_whisper hanya di-import lazy di dalam worker thread.
from src.core.engine import TranscribeEngine

TranscribeEngine.apply_wdac_patch()

from src.gui.main_window import MainWindow  # noqa: E402


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Mesin Transcribe GUI")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
