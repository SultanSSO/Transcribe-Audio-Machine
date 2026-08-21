"""Path helpers — konsisten dengan struktur output v3."""

import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HASIL_DIR = PROJECT_ROOT / "transcribe_hasil"


def project_root() -> Path:
    return PROJECT_ROOT


def stem(path: str) -> str:
    """Filename tanpa extension ganda.  audio.mp3.mpeg -> audio."""
    name = os.path.splitext(os.path.basename(path))[0]
    while True:
        root, ext = os.path.splitext(name)
        if ext == "":
            break
        name = root
    return name


def auto_folder(audio_stem: str) -> str:
    """transcribe_hasil/XX_nama/ — XX = max+1 dari folder XX_* yang ADA."""
    pattern = re.compile(r"^(\d{2})_.*$")
    max_n = 0
    if HASIL_DIR.is_dir():
        for entry in os.listdir(HASIL_DIR):
            m = pattern.match(entry)
            if m and (HASIL_DIR / entry).is_dir():
                max_n = max(max_n, int(m.group(1)))
    folder = HASIL_DIR / f"{max_n + 1:02d}_{audio_stem}"
    return str(folder)


def list_history() -> list:
    """Daftar folder hasil transkripsi (descending, terbaru dulu)."""
    if not HASIL_DIR.is_dir():
        return []
    folders = [
        d for d in HASIL_DIR.iterdir()
        if d.is_dir() and re.match(r"^\d{2}_", d.name)
    ]
    folders.sort(key=lambda p: p.name, reverse=True)
    return [str(p) for p in folders]
