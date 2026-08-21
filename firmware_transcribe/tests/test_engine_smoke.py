"""Smoke test engine — transkripsi file pendek via TranscribeEngine.

Butuh model small di cache HuggingFace (sudah ada di mesin ini).
Jalankan dari folder firmware_transcribe:
    .venv\\Scripts\\python.exe -m pytest tests/ -q
"""

import os

from src.core.engine import TranscribeEngine

SAMPLE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "sample_audio", "sample_75s.mp3",
)


def test_ffmpeg_available():
    from src.utils.ffmpeg_checker import check_ffmpeg
    res = check_ffmpeg()
    assert res["ok"], res["error"]


def test_transcribe_smoke(tmp_path):
    if not os.path.exists(SAMPLE):
        import pytest
        pytest.skip("sample_audio/sample_75s.mp3 tidak ada")

    events = []
    result = TranscribeEngine.transcribe(
        SAMPLE,
        config={
            "model": "small", "language": "id", "device": "cpu",
            "compute_type": "int8", "output_dir": str(tmp_path),
        },
        callbacks={
            "on_log": lambda m: events.append(("log", m)),
            "on_progress": lambda p, m: events.append(("progress", p)),
            "on_segment": lambda s, e, t: events.append(("segment", s)),
            "on_finished": lambda d, md: events.append(("finished", d)),
        },
    )

    assert os.path.exists(result["txt_path"])
    assert os.path.exists(result["json_path"])
    assert result["metadata"]["segment_count"] >= 1
    assert any(k == "log" for k, _ in events)
    assert any(k == "segment" for k, _ in events)
    assert any(k == "finished" for k, _ in events)
