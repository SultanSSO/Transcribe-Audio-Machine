"""ffmpeg environment check (R-09 kajian)."""

import shutil
import subprocess


def check_ffmpeg() -> dict:
    """Cek ffmpeg di PATH. Returns dict {ok, version, error}."""
    exe = shutil.which("ffmpeg")
    if not exe:
        return {
            "ok": False,
            "version": None,
            "error": "ffmpeg tidak ditemukan di PATH. "
                     "Install: winget install Gyan.FFmpeg.Essentials",
        }
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, timeout=15
        )
        if result.returncode != 0:
            return {"ok": False, "version": None,
                    "error": "ffmpeg gagal dijalankan."}
        version = result.stdout.decode("utf-8", errors="replace").splitlines()[0]
        return {"ok": True, "version": version, "error": None}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "version": None, "error": str(e)}
