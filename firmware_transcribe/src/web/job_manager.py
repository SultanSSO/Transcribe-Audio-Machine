"""JobManager — transkripsi background di server web.

Setiap job:
  - id unik
  - thread sendiri yang memanggil TranscribeEngine.transcribe
  - queue event thread-safe (untuk SSE streaming ke browser)
  - cancel_event untuk pembatalan

Event queue item (dict):
    {"type": "log", "message": str}
    {"type": "progress", "percent": int, "message": str}
    {"type": "segment", "start": float, "end": float, "text": str}
    {"type": "finished", "output_dir": str, "metadata": dict}
    {"type": "error", "error": str}
    {"type": "cancelled"}
"""

import queue
import threading
import time
import uuid

from src.core.engine import CancelledError, TranscribeEngine

HEARTBEAT_SECONDS = 15


class TranscribeJob:
    """Satu pekerjaan transkripsi (kind=transcribe) atau notulen AI (kind=ai_notulen)."""

    def __init__(self, job_id, audio_path, config, kind="transcribe"):
        self.id = job_id
        self.kind = kind
        self.audio_path = audio_path  # untuk kind=ai_notulen: folder hasil (output_dir)
        self.config = config
        self.status = "pending"  # pending|running|done|error|cancelled
        self.events = queue.Queue()
        self.cancel_event = threading.Event()
        self.output_dir = None
        self.metadata = None
        self.error = None
        self.created_at = time.time()
        self.thread = None

    def to_dict(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "audio": self.audio_path,
            "config": self.config,
            "output_dir": self.output_dir,
            "metadata": self.metadata,
            "error": self.error,
            "created_at": self.created_at,
        }


class JobManager:
    """Registry + lifecycle semua job."""

    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()

    def create(self, audio_path, config) -> TranscribeJob:
        job_id = uuid.uuid4().hex[:12]
        job = TranscribeJob(job_id, audio_path, config)
        with self._lock:
            self._jobs[job_id] = job

        job.thread = threading.Thread(
            target=self._run, args=(job,), daemon=True, name=f"transcribe-{job_id}"
        )
        job.thread.start()
        return job

    def create_ai(self, output_dir) -> TranscribeJob:
        """Job notulen AI: rangkum transkrip di output_dir → DOCX."""
        job_id = uuid.uuid4().hex[:12]
        job = TranscribeJob(job_id, output_dir, {}, kind="ai_notulen")
        with self._lock:
            self._jobs[job_id] = job

        job.thread = threading.Thread(
            target=self._run_ai, args=(job,), daemon=True, name=f"ai-{job_id}"
        )
        job.thread.start()
        return job

    def get(self, job_id):
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id) -> bool:
        job = self.get(job_id)
        if not job:
            return False
        job.cancel_event.set()
        return True

    def _run(self, job):
        job.status = "running"
        job.events.put({"type": "log", "message": f"Job {job.id} dimulai."})

        def on_log(msg):
            job.events.put({"type": "log", "message": msg})

        def on_progress(pct, msg):
            job.events.put({"type": "progress", "percent": pct, "message": msg})

        def on_segment(start, end, text):
            job.events.put({"type": "segment", "start": start, "end": end, "text": text})
            if job.cancel_event.is_set():
                raise CancelledError()

        def on_finished(out_dir, metadata):
            job.output_dir = out_dir
            job.metadata = metadata
            job.events.put({"type": "finished", "output_dir": out_dir,
                            "metadata": metadata})

        def on_error(err):
            job.error = err
            job.events.put({"type": "error", "error": err})

        callbacks = {
            "on_log": on_log,
            "on_progress": on_progress,
            "on_segment": on_segment,
            "on_finished": on_finished,
            "on_error": on_error,
        }

        try:
            TranscribeEngine.transcribe(job.audio_path, job.config, callbacks)
            if job.status != "cancelled":
                job.status = "done"
        except CancelledError:
            job.status = "cancelled"
            job.events.put({"type": "cancelled"})
        except Exception as e:  # noqa: BLE001
            job.status = "error"
            job.error = str(e)
            job.events.put({"type": "error", "error": f"{type(e).__name__}: {e}"})

        # Penanda akhir stream (SSE generator berhenti setelah ini)
        job.events.put({"type": "job_end", "status": job.status})

    # ── Runner notulen AI ──────────────────────────────────────────────
    def _run_ai(self, job):
        job.status = "running"
        job.events.put({"type": "log", "message": f"Job AI {job.id} dimulai."})

        def on_log(msg):
            job.events.put({"type": "log", "message": msg})

        def on_progress(pct, msg):
            job.events.put({"type": "progress", "percent": pct, "message": msg})

        def on_finished(result):
            job.output_dir = job.audio_path
            job.metadata = result
            job.events.put({"type": "finished", "output_dir": job.output_dir,
                            "metadata": result})

        def on_error(err):
            job.error = err
            job.events.put({"type": "error", "error": err})

        callbacks = {
            "on_log": on_log,
            "on_progress": on_progress,
            "on_finished": on_finished,
            "on_error": on_error,
        }

        try:
            from src.notulen.ai_generator import generate_notulen_docx
            generate_notulen_docx(job.audio_path, callbacks)
            if job.status != "cancelled":
                job.status = "done"
        except Exception as e:  # noqa: BLE001
            job.status = "error"
            job.error = str(e)
            job.events.put({"type": "error", "error": f"{type(e).__name__}: {e}"})

        job.events.put({"type": "job_end", "status": job.status})

    # ── SSE generator ───────────────────────────────────────────────────
    def event_stream(self, job_id):
        """Generator SSE: stream event job sampai selesai + heartbeat."""
        job = self.get(job_id)
        if not job:
            yield "event: error\ndata: {\"error\": \"job tidak ditemukan\"}\n\n"
            return

        while True:
            try:
                item = job.events.get(timeout=HEARTBEAT_SECONDS)
            except queue.Empty:
                # heartbeat — jaga koneksi tetap hidup
                yield ": heartbeat\n\n"
                continue

            if item["type"] == "job_end":
                yield f"event: job_end\ndata: {_json(item)}\n\n"
                break

            yield f"event: {item['type']}\ndata: {_json(item)}\n\n"


def _json(obj):
    import json
    return json.dumps(obj, ensure_ascii=False, default=str)
