"""Test unit untuk output writer & segment merger (tanpa model)."""

import json
import os
import tempfile

from src.core.output_writer import write_json, write_txt
from src.core.segment_merger import merge_segments


def test_write_txt(tmp_path=None):
    d = tmp_path or tempfile.mkdtemp()
    p = write_txt(d, "Ini teks transkrip.")
    assert os.path.exists(p)
    with open(p, encoding="utf-8") as f:
        assert "Ini teks transkrip." in f.read()


def test_write_json_valid():
    d = tempfile.mkdtemp()
    p = write_json(d, "audio.mp3", "small", "id", 0.99, 12.3,
                   [{"start": 0.0, "end": 2.0, "text": "halo"}])
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    assert data["model"] == "small"
    assert data["language"] == "id"
    assert data["segments"][0]["text"] == "halo"


def test_merge_segments_two_sentences():
    raw = [
        {"start": 0.0, "end": 2.0, "text": "Ini kalimat pertama."},
        {"start": 2.0, "end": 4.0, "text": "Ini kalimat kedua."},
    ]
    merged = merge_segments(raw)
    assert len(merged) == 1
    assert merged[0]["start"] == 0.0
    assert merged[0]["end"] == 4.0


def test_merge_segments_250_chars():
    raw = [
        {"start": 0.0, "end": 2.0, "text": "x" * 260},
    ]
    merged = merge_segments(raw)
    assert len(merged) == 1
    assert len(merged[0]["text"]) == 260


def test_merge_segments_single_sentence_kept():
    raw = [
        {"start": 0.0, "end": 2.0, "text": "Hanya satu kalimat."},
    ]
    merged = merge_segments(raw)
    assert len(merged) == 1
