"""Settings persistence (AD-05 kajian) — JSON config di folder user.

Lokasi: %APPDATA%/TranscribeGUI/config.json (via platformdirs jika ada,
fallback ke Path.home()/.transcribe_gui/config.json).
"""

import json
import os
from pathlib import Path

try:
    import platformdirs
    _CONFIG_DIR = Path(platformdirs.user_config_dir("TranscribeGUI"))
except Exception:  # noqa: BLE001
    _CONFIG_DIR = Path.home() / ".transcribe_gui"

DEFAULTS = {
    "model": "small",
    "language": "id",
    "device": "cpu",
    "compute_type": "int8",
    "output_dir": "",
    "with_md": False,
}


def config_path() -> Path:
    return _CONFIG_DIR / "config.json"


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    path = config_path()
    try:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    except Exception:  # noqa: BLE001 — config corrupt → backup + reset (R-12)
        try:
            os.replace(path, path.with_suffix(".json.bak"))
        except OSError:
            pass
    return cfg


def save_config(cfg: dict) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    clean = {k: cfg.get(k, DEFAULTS[k]) for k in DEFAULTS}
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
