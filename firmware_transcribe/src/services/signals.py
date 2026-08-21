"""Custom Qt signals untuk komunikasi worker → GUI.

Pattern dari kajian (services/signals.py):
    progress = Signal(int, str)       # (percent, status_text)
    segment  = Signal(float, float, str)  # (start, end, text)
    log      = Signal(str)
    finished = Signal(str, dict)      # (output_dir, metadata)
    error    = Signal(str)
"""

from PySide6.QtCore import QObject, Signal


class TranscribeSignals(QObject):
    """Objek sinyal yang di-emit dari thread worker ke main thread."""

    progress = Signal(int, str)
    segment = Signal(float, float, str)
    log = Signal(str)
    finished = Signal(str, dict)
    error = Signal(str)
    cancelled = Signal()
