"""TranscribeEngine — wrapper faster-whisper + WDAC patch.

Dapat dipakai dari CLI maupun GUI. Semua call pemblokir harus dipanggil
dari background thread (bukan main/Qt thread).

Callback contract (semua opsional, dipanggil dari thread worker):
    on_log(message: str)
    on_progress(percent: int, message: str)
    on_segment(start: float, end: float, text: str)
    on_finished(output_dir: str, metadata: dict)
    on_error(error: str)
"""

import os
import re
import sys
import time
import types
from pathlib import Path


class CancelledError(Exception):
    """Transkripsi dibatalkan user (bukan error)."""


# Root proyek: firmware_transcribe/ (2 level di atas src/core/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
HASIL_DIR = PROJECT_ROOT / "transcribe_hasil"


class TranscribeEngine:
    """Wraps faster-whisper with the WDAC fake-av workaround.

    Urutan import KRITIS:
      1. apply_wdac_patch() dipanggil PERTAMA
      2. baru import faster_whisper (dilakukan lazy di dalam method)
    Jangan pernah import faster_whisper di module-level GUI.
    """

    _model_cache = {}
    _patch_applied = False

    # ── WDAC patch ────────────────────────────────────────────────────────
    @classmethod
    def apply_wdac_patch(cls):
        """Pasang fake `av` module + monkey-patch decode_audio ke ffmpeg.

        Harus dipanggil sekali sebelum import faster_whisper manapun.
        Aman dipanggil berulang (idempotent).
        """
        if cls._patch_applied:
            return
        cls._patch_applied = True

        fake_av = types.ModuleType("av")
        fake_av.audio = types.ModuleType("av.audio")
        sys.modules["av"] = fake_av
        sys.modules["av.audio"] = fake_av.audio

        from .audio_decoder import decode_audio  # noqa: E402

        import faster_whisper  # noqa: E402
        import faster_whisper.audio  # noqa: E402
        import faster_whisper.transcribe  # noqa: E402

        faster_whisper.audio.decode_audio = decode_audio
        faster_whisper.transcribe.decode_audio = decode_audio
        faster_whisper.decode_audio = decode_audio

    # ── Model ─────────────────────────────────────────────────────────────
    @classmethod
    def load_model(cls, model_name="small", device="cpu", compute_type="int8"):
        """Load (dan cache) WhisperModel. Panggil dari worker thread."""
        key = (model_name, device, compute_type)
        if key in cls._model_cache:
            return cls._model_cache[key]

        cls.apply_wdac_patch()
        from faster_whisper import WhisperModel  # noqa: E402

        model = WhisperModel(model_name, device=device, compute_type=compute_type)
        cls._model_cache[key] = model
        return model

    @classmethod
    def is_model_cached(cls, model_name="small") -> bool:
        """Cek apakah model sudah ada di cache HuggingFace (tanpa download)."""
        from huggingface_hub import snapshot_download  # noqa: E402
        cache_dir = os.path.join(Path.home(), ".cache", "huggingface", "hub")
        repo = f"models--Systran--faster-whisper-{model_name}"
        return os.path.isdir(os.path.join(cache_dir, repo))

    # ── Path helper ───────────────────────────────────────────────────────
    @staticmethod
    def _stem(path: str) -> str:
        name = os.path.splitext(os.path.basename(path))[0]
        while True:
            root, ext = os.path.splitext(name)
            if ext == "":
                break
            name = root
        return name

    @classmethod
    def auto_folder(cls, audio_stem: str) -> str:
        """transcribe_hasil/XX_nama/, XX = max+1 dari folder XX_* yang ADA."""
        pattern = re.compile(r"^(\d{2})_.*$")
        max_n = 0
        if HASIL_DIR.is_dir():
            for entry in os.listdir(HASIL_DIR):
                m = pattern.match(entry)
                if m and (HASIL_DIR / entry).is_dir():
                    max_n = max(max_n, int(m.group(1)))
        folder = HASIL_DIR / f"{max_n + 1:02d}_{audio_stem}"
        return str(folder)

    # ── Transcribe ────────────────────────────────────────────────────────
    @classmethod
    def transcribe(cls, audio_path, config=None, callbacks=None):
        """Transkripsi satu file audio.

        Args:
          audio_path: path absolut file audio.
          config: dict opsional {model, language, device, compute_type,
                  output_dir, with_md, beam_size}
          callbacks: dict opsional {on_log, on_progress, on_segment,
                    on_finished, on_error}

        Returns:
          dict {"segments", "info", "full_text", "output_dir", "txt_path",
                "json_path", "md_path"}
        """
        cfg = {
            "model": "small",
            "language": "id",
            "device": "cpu",
            "compute_type": "int8",
            "output_dir": None,
            "with_md": False,
            "beam_size": 5,
            # Anti-halusinasi / audio panjang (Phase 3)
            "vad_filter": True,                      # lewati bagian non-speech (silence panjang)
            "condition_on_previous_text": False,     # cegah loop halusinasi pada audio panjang
            "hallucination_silence_threshold": 2.0,  # drop segmen halusinasi setelah silence > 2s
            "no_speech_threshold": 0.6,
            "compression_ratio_threshold": 2.4,
            "log_prob_threshold": -1.0,
        }
        if config:
            cfg.update(config)
        cb = callbacks or {}

        def log(msg):
            if cb.get("on_log"):
                cb["on_log"](msg)

        try:
            audio = os.path.abspath(audio_path)
            if not os.path.exists(audio):
                raise FileNotFoundError(f"File audio tidak ditemukan: {audio}")

            stem = cls._stem(audio)
            out_dir = cfg["output_dir"] or cls.auto_folder(stem)

            log(f"Memuat model '{cfg['model']}' ({cfg['device']}/{cfg['compute_type']})...")
            model = cls.load_model(cfg["model"], cfg["device"], cfg["compute_type"])
            log(f"Model '{cfg['model']}' siap.")

            log("Transkripsi dimulai...")
            start = time.time()

            segments_iter, info = model.transcribe(
                audio,
                language=cfg["language"],
                beam_size=cfg["beam_size"],
                vad_filter=cfg["vad_filter"],
                condition_on_previous_text=cfg["condition_on_previous_text"],
                hallucination_silence_threshold=cfg["hallucination_silence_threshold"],
                no_speech_threshold=cfg["no_speech_threshold"],
                compression_ratio_threshold=cfg["compression_ratio_threshold"],
                log_prob_threshold=cfg["log_prob_threshold"],
            )

            total_duration = float(getattr(info, "duration", 0.0)) or 0.0

            raw_segments = []
            full_text_parts = []
            for s in segments_iter:
                seg = {
                    "start": round(s.start, 2),
                    "end": round(s.end, 2),
                    "text": s.text.strip(),
                }
                raw_segments.append(seg)
                full_text_parts.append(s.text.strip())

                if cb.get("on_segment"):
                    cb["on_segment"](seg["start"], seg["end"], seg["text"])
                if cb.get("on_progress") and total_duration > 0:
                    pct = int((seg["end"] / total_duration) * 100)
                    cb["on_progress"](min(pct, 99), f"Segmen {seg['start']:.0f}s")

            elapsed = time.time() - start
            log(f"Selesai dalam {elapsed:.0f}s ({elapsed / 60:.1f}m)")

            # ── Output ──────────────────────────────────────────────────
            from .segment_merger import merge_segments
            from .output_writer import write_txt, write_json

            os.makedirs(out_dir, exist_ok=True)
            segments = merge_segments(raw_segments)
            full_text = " ".join(full_text_parts).strip()

            txt_path = write_txt(out_dir, full_text)
            json_path = write_json(
                out_dir, audio, cfg["model"],
                info.language, info.language_probability, elapsed, segments,
            )

            md_path = None
            if cfg["with_md"]:
                from ..notulen.generator import write_notulen_md
                md_path = write_notulen_md(
                    full_text, stem, cfg["model"], cfg["language"], out_dir
                )
                log(f"Notulen MD -> {md_path}")

            log(f"TXT  -> {txt_path}")
            log(f"JSON -> {json_path}")

            metadata = {
                "source": audio,
                "model": cfg["model"],
                "language": info.language,
                "language_probability": round(float(info.language_probability), 4),
                "duration_s": round(elapsed, 1),
                "audio_duration_s": round(total_duration, 1),
                "segment_count": len(segments),
            }

            if cb.get("on_finished"):
                cb["on_finished"](out_dir, metadata)

            return {
                "segments": segments,
                "info": info,
                "full_text": full_text,
                "output_dir": out_dir,
                "txt_path": txt_path,
                "json_path": json_path,
                "md_path": md_path,
                "metadata": metadata,
            }
        except CancelledError:
            raise  # cancel bukan error — biarkan caller menanganinya
        except Exception as e:  # noqa: BLE001 — diteruskan ke callback
            if cb.get("on_error"):
                cb["on_error"](str(e))
            raise
