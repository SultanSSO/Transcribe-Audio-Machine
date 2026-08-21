"""MainWindow PoC — Phase 1 kajian.

Konten minimal:
  - tombol "Test Worker"  (dummy 10 detik, progress 0-100)
  - tombol "Transcribe"   (transkripsi asli via worker thread)
  - progress bar
  - log panel (QPlainTextEdit read-only)
UI tidak pernah memanggil engine di main thread (R-01).
"""

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QPlainTextEdit, QProgressBar, QPushButton, QComboBox, QVBoxLayout,
    QWidget,
)

from src.core.engine import TranscribeEngine
from src.services.signals import TranscribeSignals
from src.services.transcribe_worker import TranscribeWorker


class MainWindow(QMainWindow):
    """Window utama — PoC Phase 1."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mesin Transcribe GUI — PoC Phase 1")
        self.resize(760, 560)

        self.threadpool = QThreadPool.globalInstance()
        self.current_worker = None

        self._build_ui()

        # Environment check startup (R-09)
        self._check_environment()

    # ── UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # ── Input file ──
        file_box = QGroupBox("File Audio")
        file_layout = QHBoxLayout(file_box)
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("Pilih atau drag file audio (mp3/wav/m4a/flac/aac/ogg)...")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(self.file_edit, 1)
        file_layout.addWidget(browse_btn)
        layout.addWidget(file_box)

        # ── Settings ringkas ──
        set_box = QGroupBox("Pengaturan")
        set_layout = QHBoxLayout(set_box)
        set_layout.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium"])
        self.model_combo.setCurrentText("small")
        set_layout.addWidget(self.model_combo)
        set_layout.addWidget(QLabel("Bahasa:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["id", "en"])
        self.lang_combo.setCurrentText("id")
        set_layout.addWidget(self.lang_combo)
        set_layout.addStretch(1)
        layout.addWidget(set_box)

        # ── Actions ──
        act_layout = QHBoxLayout()
        self.btn_test = QPushButton("Test Worker (10s)")
        self.btn_test.clicked.connect(self._start_test_worker)
        self.btn_transcribe = QPushButton("Transcribe")
        self.btn_transcribe.clicked.connect(self._start_transcribe)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_worker)
        act_layout.addWidget(self.btn_test)
        act_layout.addWidget(self.btn_transcribe)
        act_layout.addWidget(self.btn_cancel)
        act_layout.addStretch(1)
        layout.addLayout(act_layout)

        # ── Progress ──
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.status_label = QLabel("Siap.")
        layout.addWidget(self.status_label)

        # ── Log ──
        log_box = QGroupBox("Log")
        log_layout = QVBoxLayout(log_box)
        self.log_panel = QPlainTextEdit()
        self.log_panel.setReadOnly(True)
        log_layout.addWidget(self.log_panel)
        layout.addWidget(log_box, 1)

        # Drag-drop
        self.setAcceptDrops(True)

    # ── Environment check (R-09) ────────────────────────────────────────
    def _check_environment(self):
        from src.utils.ffmpeg_checker import check_ffmpeg
        res = check_ffmpeg()
        if res["ok"]:
            self._log(f"✅ ffmpeg OK: {res['version']}")
        else:
            self._log(f"⚠️ {res['error']}")

        cached = TranscribeEngine.is_model_cached(self.model_combo.currentText())
        self._log(f"Model '{self.model_combo.currentText()}' di cache: {cached}")

    # ── Actions ─────────────────────────────────────────────────────────
    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih file audio", "",
            "Audio (*.mp3 *.wav *.m4a *.flac *.aac *.ogg)",
        )
        if path:
            self.file_edit.setText(path)

    def _start_test_worker(self):
        self._set_running(True)
        self._log("Memulai test worker...")
        signals = TranscribeSignals()
        signals.progress.connect(self._on_progress)
        signals.log.connect(self._log)
        signals.finished.connect(self._on_finished)
        signals.error.connect(self._on_error)

        worker = TranscribeWorker(mode="test", signals=signals)
        self.current_worker = worker
        self.threadpool.start(worker)

    def _start_transcribe(self):
        audio = self.file_edit.text().strip()
        if not audio:
            self._log("⚠️ Pilih file audio dulu.")
            return

        self._set_running(True)
        self._log(f"Memulai transkripsi: {audio}")

        signals = TranscribeSignals()
        signals.progress.connect(self._on_progress)
        signals.segment.connect(self._on_segment)
        signals.log.connect(self._log)
        signals.finished.connect(self._on_finished)
        signals.error.connect(self._on_error)
        signals.cancelled.connect(self._on_cancelled)

        config = {
            "model": self.model_combo.currentText(),
            "language": self.lang_combo.currentText(),
            "device": "cpu",
            "compute_type": "int8",
        }
        worker = TranscribeWorker(
            mode="transcribe", audio_path=audio, config=config,
            signals=signals,
        )
        self.current_worker = worker
        self.threadpool.start(worker)

    def _cancel_worker(self):
        if self.current_worker:
            self.status_label.setText("Membatalkan...")
            self.btn_cancel.setEnabled(False)
            self.current_worker.cancel()

    # ── Slots ───────────────────────────────────────────────────────────
    def _set_running(self, running):
        self.btn_test.setEnabled(not running)
        self.btn_transcribe.setEnabled(not running)
        self.btn_cancel.setEnabled(running)
        self.model_combo.setEnabled(not running)
        self.lang_combo.setEnabled(not running)

    def _on_progress(self, pct, msg):
        self.progress.setValue(pct)
        self.status_label.setText(msg)

    def _on_segment(self, start, end, text):
        preview = text if len(text) <= 120 else text[:117] + "..."
        self._log(f"[{start:.0f}s] {preview}")

    def _on_finished(self, out_dir, metadata):
        self._set_running(False)
        self.progress.setValue(100)
        self.status_label.setText("Selesai.")
        if out_dir:
            self._log(f"✅ Selesai. Output: {out_dir}")
            self._log(f"   Segmen: {metadata.get('segment_count', '?')}, "
                      f"durasi proses: {metadata.get('duration_s', '?')}s")

    def _on_cancelled(self):
        self._set_running(False)
        self.status_label.setText("Dibatalkan.")

    def _on_error(self, err):
        self._set_running(False)
        self.status_label.setText("Error.")
        self._log(f"❌ {err}")

    def _log(self, msg):
        self.log_panel.appendPlainText(msg)

    # ── Drag-drop ───────────────────────────────────────────────────────
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self.file_edit.setText(urls[0].toLocalFile())
