"""TranscribeWorker — QRunnable untuk transkripsi background (R-01).

Jalankan via QThreadPool. GUI tidak pernah memanggil engine langsung
di main thread.
"""

import time

from PySide6.QtCore import QRunnable

from src.core.engine import CancelledError, TranscribeEngine
from src.services.signals import TranscribeSignals


class TranscribeWorker(QRunnable):
    """Worker transkripsi. mode="test" → dummy 10 detik (PoC);
    mode="transcribe" → engine asli."""

    def __init__(self, mode="test", audio_path=None, config=None,
                 signals=None):
        super().__init__()
        self.mode = mode
        self.audio_path = audio_path
        self.config = config or {}
        self.signals = signals or TranscribeSignals()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            if self.mode == "test":
                self._run_test()
            else:
                self._run_transcribe()
        except CancelledError:
            self.signals.log.emit("Transkripsi dibatalkan user.")
            self.signals.cancelled.emit()
        except Exception as e:  # noqa: BLE001
            if not self._cancelled:
                self.signals.error.emit(f"{type(e).__name__}: {e}")

    # ── Test worker: dummy 10 detik, progress 0-100 ─────────────────────
    def _run_test(self):
        self.signals.log.emit("Test worker dimulai (10 detik)...")
        for i in range(1, 101):
            if self._cancelled:
                self.signals.log.emit("Test dibatalkan.")
                self.signals.cancelled.emit()
                return
            time.sleep(0.1)
            self.signals.progress.emit(i, f"Test step {i}/100")
        self.signals.log.emit("Test worker selesai.")
        self.signals.progress.emit(100, "Selesai")
        self.signals.finished.emit("", {"mode": "test"})

    # ── Transcribe asli ─────────────────────────────────────────────────
    def _run_transcribe(self):
        if not self.audio_path:
            self.signals.error.emit("Tidak ada file audio dipilih.")
            return

        def on_log(msg):
            self.signals.log.emit(msg)

        def on_progress(pct, msg):
            if self._cancelled:
                return
            self.signals.progress.emit(pct, msg)

        def on_segment(start, end, text):
            self.signals.segment.emit(start, end, text)
            if self._cancelled:
                raise CancelledError()

        def on_finished(out_dir, metadata):
            self.signals.finished.emit(out_dir, metadata)

        def on_error(err):
            self.signals.error.emit(err)

        callbacks = {
            "on_log": on_log,
            "on_progress": on_progress,
            "on_segment": on_segment,
            "on_finished": on_finished,
            "on_error": on_error,
        }
        TranscribeEngine.transcribe(self.audio_path, self.config, callbacks)
