"""Test parameter anti-halusinasi diteruskan ke model.transcribe (mock, tanpa model)."""

from src.core.engine import TranscribeEngine


class FakeInfo:
    duration = 10.0
    language = "id"
    language_probability = 0.99


class FakeModel:
    def __init__(self):
        self.captured = {}

    def transcribe(self, audio, **kwargs):
        self.captured.update(kwargs)
        return iter([]), FakeInfo()


def _run(tmp_path, extra_config=None, fake=None):
    audio = tmp_path / "dummy.mp3"
    audio.write_bytes(b"dummy")
    config = {"model": "small", "language": "id", "output_dir": str(tmp_path)}
    if extra_config:
        config.update(extra_config)
    TranscribeEngine.transcribe(str(audio), config)
    return fake.captured


def test_anti_hallucination_defaults(monkeypatch, tmp_path):
    fake = FakeModel()
    monkeypatch.setattr(TranscribeEngine, "load_model", lambda *a, **k: fake)
    captured = _run(tmp_path, fake=fake)

    assert captured["vad_filter"] is True
    assert captured["condition_on_previous_text"] is False
    assert captured["hallucination_silence_threshold"] == 2.0
    assert captured["no_speech_threshold"] == 0.6
    assert captured["compression_ratio_threshold"] == 2.4
    assert captured["log_prob_threshold"] == -1.0
    assert captured["beam_size"] == 5


def test_anti_hallucination_overridable(monkeypatch, tmp_path):
    fake = FakeModel()
    monkeypatch.setattr(TranscribeEngine, "load_model", lambda *a, **k: fake)
    captured = _run(
        tmp_path,
        extra_config={"vad_filter": False, "condition_on_previous_text": True,
                      "hallucination_silence_threshold": None},
        fake=fake,
    )
    assert captured["vad_filter"] is False
    assert captured["condition_on_previous_text"] is True
    assert captured["hallucination_silence_threshold"] is None
