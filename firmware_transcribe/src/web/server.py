"""FastAPI server — dashboard transcribe via browser (IP local).

Run:
    .venv\\Scripts\\python.exe -m src.web.server            # dev, 127.0.0.1
    .venv\\Scripts\\python.exe -m src.web.server --host 0.0.0.0 --port 8765
"""

import argparse
import json
import os
import re
import socket
import threading
import time
import webbrowser
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.core.engine import TranscribeEngine
from src.notulen.ai_generator import ai_config
from src.utils.config import load_config, save_config
from src.utils.ffmpeg_checker import check_ffmpeg
from src.utils.paths import HASIL_DIR, list_history
from src.web.job_manager import JobManager

WEB_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
PROJECT_ROOT = WEB_DIR.parents[1]
UPLOAD_DIR = PROJECT_ROOT / "uploads"

# Patch WDAC paling awal (R-02 kajian) — sebelum import faster_whisper
TranscribeEngine.apply_wdac_patch()

app = FastAPI(title="Mesin Transcribe GUI", version="0.1.0")
jobs = JobManager()
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

ALLOWED_EXT = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"}


def _sanitize_filename(name: str) -> str:
    name = os.path.basename(name.replace("\\", "/"))
    name = re.sub(r"[^\w.\- ]", "_", name)
    return name.strip() or "audio"


# ── Halaman utama ────────────────────────────────────────────────────────
@app.get("/")
def index():
    return FileResponse(TEMPLATE_DIR / "index.html")


# ── Env check (R-09) ─────────────────────────────────────────────────────
@app.get("/api/env")
def env():
    ff = check_ffmpeg()
    model_cached = TranscribeEngine.is_model_cached("small")
    return {
        "ffmpeg": ff,
        "model_cached": model_cached,
        "model_default": "small",
        "output_dir": str(HASIL_DIR),
        "ai": ai_config(),
        "settings": load_config(),  # settings terakhir tersimpan (persistence)
    }


# ── Upload audio ─────────────────────────────────────────────────────────
@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            400,
            f"Ekstensi {ext or '(kosong)'} tidak didukung. "
            f"Izinkan: {', '.join(sorted(ALLOWED_EXT))}",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_filename(file.filename or "audio")

    # Nama asli dipertahankan (folder hasil = stem nama asli).
    # Jika sudah ada, tambah suffix -2, -3, dst.
    dest = UPLOAD_DIR / safe_name
    if dest.exists():
        stem_ = dest.stem
        i = 2
        while dest.exists():
            dest = UPLOAD_DIR / f"{stem_}-{i}{dest.suffix}"
            i += 1

    size = 0
    with open(dest, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)
            size += len(chunk)

    return {"path": str(dest), "filename": safe_name, "size": size}


# ── Transcribe ───────────────────────────────────────────────────────────
@app.post("/api/transcribe")
def start_transcribe(body: dict):
    audio_path = body.get("audio_path") or body.get("file_path")
    if not audio_path:
        raise HTTPException(400, "audio_path wajib diisi")

    audio_path = os.path.abspath(audio_path)
    if not os.path.exists(audio_path):
        raise HTTPException(404, f"File audio tidak ditemukan: {audio_path}")

    config = {
        "model": body.get("model", "small"),
        "language": body.get("language", "id"),
        "device": body.get("device", "cpu"),
        "compute_type": body.get("compute_type", "int8"),
        "with_md": False,  # fitur MD dimatikan — notulen via AI (DOCX)
    }

    # Settings persistence: simpan pilihan terakhir user (model/bahasa)
    try:
        save_config({"model": config["model"], "language": config["language"],
                     "device": config["device"], "compute_type": config["compute_type"]})
    except OSError:
        pass  # gagal simpan bukan error fatal

    job = jobs.create(audio_path, config)
    return job.to_dict()


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    return job.to_dict()


@app.get("/api/jobs/{job_id}/stream")
def job_stream(job_id: str):
    if not jobs.get(job_id):
        raise HTTPException(404, "Job tidak ditemukan")
    return StreamingResponse(
        jobs.event_stream(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/jobs/{job_id}/cancel")
def job_cancel(job_id: str):
    ok = jobs.cancel(job_id)
    if not ok:
        raise HTTPException(404, "Job tidak ditemukan")
    return {"ok": True}


# ── Notulen AI (Phase 2) ────────────────────────────────────────────────
@app.post("/api/notulen/ai")
def notulen_ai(body: dict):
    """Buat notulen AI dari transkrip di folder hasil → DOCX."""
    output_dir = body.get("output_dir") or body.get("folder")
    if not output_dir:
        raise HTTPException(400, "output_dir wajib diisi")

    fpath = Path(os.path.normpath(output_dir))
    if not re.match(r"^\d{2}_[\w\- ]+$", fpath.name):
        raise HTTPException(400, "Nama folder hasil tidak valid (harus XX_nama)")
    if not fpath.is_dir():
        raise HTTPException(404, "Folder hasil tidak ditemukan")
    if not fpath.resolve().is_relative_to(HASIL_DIR.resolve()):
        raise HTTPException(400, "Folder di luar direktori hasil tidak diizinkan")

    job = jobs.create_ai(str(fpath))
    return job.to_dict()


# ── History (hasil transkripsi) ──────────────────────────────────────────
@app.get("/api/history")
def history():
    items = []
    for folder in list_history():
        folder_path = Path(folder)
        # Fitur MD dimatikan: file .md tidak ditampilkan di UI
        files = [f.name for f in folder_path.iterdir()
                 if f.is_file() and not f.name.lower().endswith(".md")]
        files.sort(key=lambda n: (n.startswith("transkrip"), n))
        items.append({"name": folder_path.name, "path": str(folder_path),
                      "files": files})
    return {"items": items}


@app.get("/api/history/{folder_name}/file/{file_name}")
def history_file(folder_name: str, file_name: str, download: bool = False):
    # Folder name aman: XX_nama (tanpa path traversal)
    if not re.match(r"^\d{2}_[\w\- ]+$", folder_name):
        raise HTTPException(400, "Nama folder tidak valid")
    file_name = os.path.basename(file_name)
    fpath = HASIL_DIR / folder_name / file_name
    if not fpath.is_file():
        raise HTTPException(404, "File tidak ditemukan")

    if download:
        media_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if fpath.suffix.lower() == ".docx" else "text/plain; charset=utf-8"
        )
        return FileResponse(fpath, filename=fpath.name, media_type=media_type)

    try:
        content = fpath.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = fpath.read_text(encoding="utf-8", errors="replace")
    return {"name": file_name, "content": content, "size": fpath.stat().st_size}


# ── Launch helper ────────────────────────────────────────────────────────
def get_local_ips() -> list:
    ips = ["127.0.0.1"]
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return list(dict.fromkeys(ips))


def run_server(host="127.0.0.1", port=8765, open_browser=True):
    import uvicorn

    if host in ("0.0.0.0", "::"):
        urls = [f"http://{ip}:{port}" for ip in get_local_ips()]
    else:
        urls = [f"http://{host}:{port}"]

    print("=" * 56)
    print("  MESIN TRANSCRIBE — DASHBOARD")
    print("=" * 56)
    for u in urls:
        print(f"  Buka di browser: {u}")
    print("  Tekan Ctrl+C untuk menghentikan server.")
    print("=" * 56)

    if open_browser:
        def _open():
            time.sleep(1.2)
            webbrowser.open(urls[0])
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dashboard Mesin Transcribe")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind host (default 127.0.0.1; 0.0.0.0 = semua)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true",
                        help="Jangan buka browser otomatis")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, open_browser=not args.no_browser)
