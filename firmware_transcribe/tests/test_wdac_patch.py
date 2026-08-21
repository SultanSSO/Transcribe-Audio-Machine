"""Test WDAC patch — verifikasi fake av module terpasang sebelum import."""

import sys


def test_fake_av_registered():
    """Setelah apply_wdac_patch, 'av' di sys.modules harus module palsu."""
    from src.core.engine import TranscribeEngine

    TranscribeEngine.apply_wdac_patch()
    assert "av" in sys.modules, "fake av tidak terdaftar"
    assert "av.audio" in sys.modules, "fake av.audio tidak terdaftar"


def test_no_real_av_loaded():
    """av palsu tidak boleh punya atribut PyAV asli (mis. .AudioResampler)."""
    from src.core.engine import TranscribeEngine

    TranscribeEngine.apply_wdac_patch()
    av = sys.modules["av"]
    assert not hasattr(av, "AudioResampler"), "ini av asli, bukan palsu"


def test_patch_idempotent():
    from src.core.engine import TranscribeEngine

    TranscribeEngine.apply_wdac_patch()
    TranscribeEngine.apply_wdac_patch()  # tidak boleh error


def test_engine_import_does_not_load_faster_whisper():
    """Import engine saja TIDAK boleh meng-import faster_whisper
    (harus lazy — WDAC patch diterapkan dulu)."""
    import sys as _sys

    fw_loaded = "faster_whisper" in _sys.modules
    if fw_loaded:
        # Sudah ter-load karena test lain; verifikasi 'av' palsu yang aktif
        from src.core.engine import TranscribeEngine
        TranscribeEngine.apply_wdac_patch()
        assert "av" in _sys.modules
        assert not hasattr(_sys.modules["av"], "AudioResampler")
    else:
        from src.core.engine import TranscribeEngine  # noqa: F401
        assert "faster_whisper" not in _sys.modules
