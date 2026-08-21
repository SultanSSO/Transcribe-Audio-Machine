"""Test API dashboard web (FastAPI TestClient) — regresi end-to-end.

Menjalankan transcribe asli pada sample_75s.mp3 (model small, sudah di
cache) — sekitar 12-20 detik. Stream SSE diverifikasi event-by-event.
"""

import json
import os

from fastapi.testclient import TestClient

from src.core.engine import TranscribeEngine

TranscribeEngine.apply_wdac_patch()

from src.web.server import app  # noqa: E402

client = TestClient(app)

SAMPLE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "sample_audio", "sample_75s.mp3",
)


def test_index_page():
    r = client.get("/")
    assert r.status_code == 200
    assert "Mesin Transcribe" in r.text


def test_env():
    r = client.get("/api/env")
    assert r.status_code == 200
    d = r.json()
    assert d["ffmpeg"]["ok"] is True
    assert d["model_cached"] is True


def test_upload_and_transcribe_sse():
    if not os.path.exists(SAMPLE):
        import pytest
        pytest.skip("sample_audio/sample_75s.mp3 tidak ada")

    with open(SAMPLE, "rb") as f:
        up = client.post("/api/upload", files={"file": ("sample_75s.mp3", f, "audio/mpeg")})
    assert up.status_code == 200, up.text
    path = up.json()["path"]

    job = client.post("/api/transcribe", json={
        "audio_path": path, "model": "small", "language": "id",
    })
    assert job.status_code == 200, job.text
    job_id = job.json()["id"]

    events = []
    with client.stream("GET", f"/api/jobs/{job_id}/stream") as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("event:") and not line.startswith("event: :"):
                events.append(line.split("event: ", 1)[1].strip())

    kinds = [e for e in events if e != "heartbeat"]
    assert "log" in kinds
    assert "progress" in kinds
    assert "segment" in kinds
    assert "finished" in kinds
    assert "job_end" in kinds
    assert "error" not in kinds

    # Output folder terdaftar di history
    hist = client.get("/api/history").json()["items"]
    assert len(hist) >= 1


def test_upload_invalid_ext():
    r = client.post("/api/upload", files={"file": ("tes.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_job_not_found():
    r = client.get("/api/jobs/tidak-ada")
    assert r.status_code == 404


# ── Notulen AI (Phase 2) ────────────────────────────────────────────────

def _make_test_folder(name="99_ai-test"):
    """Buat folder hasil sementara di HASIL_DIR (dibersihkan setelah test)."""
    from src.utils.paths import HASIL_DIR
    folder = HASIL_DIR / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "transkrip.txt").write_text(
        "Rapat membahas peluncuran sistem OJS. Keputusan: lanjut bulan depan.",
        encoding="utf-8",
    )
    return folder


def test_history_hides_md_files():
    folder = _make_test_folder()
    (folder / "Notulen_rapat.md").write_text("# lama", encoding="utf-8")
    try:
        items = client.get("/api/history").json()["items"]
        target = next(i for i in items if i["name"] == folder.name)
        assert all(not f.endswith(".md") for f in target["files"])
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)


def test_notulen_ai_endpoint(monkeypatch):
    import src.notulen.ai_generator as ag

    calls = {}

    def fake_generate(output_dir, callbacks):
        calls["output_dir"] = output_dir
        cb = callbacks or {}
        if cb.get("on_log"):
            cb["on_log"]("fake AI berjalan")
        result = {
            "docx_path": os.path.join(output_dir, "NotulenAI_ai-test.docx"),
            "txt_path": os.path.join(output_dir, "notulen_ai.txt"),
            "model": "mock",
            "chars_in": 50,
            "duration_s": 0.1,
        }
        if cb.get("on_finished"):
            cb["on_finished"](result)
        return result

    monkeypatch.setattr(ag, "generate_notulen_docx", fake_generate)

    folder = _make_test_folder()
    try:
        job = client.post("/api/notulen/ai", json={"output_dir": str(folder)})
        assert job.status_code == 200, job.text
        job_id = job.json()["id"]
        assert job.json()["kind"] == "ai_notulen"

        kinds = []
        with client.stream("GET", f"/api/jobs/{job_id}/stream") as r:
            assert r.status_code == 200
            for line in r.iter_lines():
                if line.startswith("event:") and not line.startswith("event: :"):
                    kinds.append(line.split("event: ", 1)[1].strip())

        kinds = [k for k in kinds if k != "heartbeat"]
        assert "finished" in kinds
        assert "job_end" in kinds
        assert "error" not in kinds
        assert calls.get("output_dir") == str(folder)
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)


def test_notulen_ai_rejects_outside_folder():
    r = client.post("/api/notulen/ai", json={"output_dir": os.getcwd()})
    assert r.status_code == 400  # bukan pola XX_nama


def test_download_docx():
    folder = _make_test_folder()
    (folder / "NotulenAI_ai-test.docx").write_bytes(b"PK fake docx")
    try:
        r = client.get(
            f"/api/history/{folder.name}/file/NotulenAI_ai-test.docx?download=1"
        )
        assert r.status_code == 200
        assert r.content == b"PK fake docx"
        assert "attachment" in r.headers.get("content-disposition", "")
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
