"""CLI Audio Transcriber v2 — faster-whisper (CTranslate2) + system ffmpeg.

Usage:
    # activate venv first
    .venv\\Scripts\\Activate.ps1

    # transcribe audio -> auto-creates folder 01_nama_audio/ with TXT + JSON
    python transcribe.py audio_sidang_OJK.mp3

    # specify model or language
    python transcribe.py sidang.mp3 --model medium --language en

    # optional legacy notulen MD generation (config retained for reuse)
    python transcribe.py sidang.mp3 --with-md

    # manual output directory (skips auto-folder)
    python transcribe.py sidang.mp3 --output-dir hasil/

Default behavior:
    Auto-creates a folder `XX_nama_audio/` inside transcribe_hasil/,
    where XX = auto-increment counter across ALL existing folders,
    nama_audio = audio filename stem (without extension).

Output (inside auto-folder):
    transkrip.txt   plain full text (line-wrapped, no segmentation)
    transkrip.json  full metadata (segments, timing, model info)

Legacy MD notulen generation is retained behind --with-md.

Prerequisites:
    - System ffmpeg (winget install Gyan.FFmpeg.Essentials)
    - Python venv with faster-whisper installed
"""

import argparse
import gc
import io
import json
import os
import re
import subprocess
import sys
import textwrap
import time
import types
from datetime import date

# ═══════════════════════════════════════════════════════════════════════════
# Auto-bootstrap: re-run this script with the project venv if the current
# python doesn't have faster-whisper installed (e.g. system python won).
# ═══════════════════════════════════════════════════════════════════════════
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_VENV_PY = os.path.join(_SCRIPT_DIR, ".venv", "Scripts", "python.exe")


def _rerun_with_venv_python():
    """Re-execute this script using .venv/Scripts/python.exe.

    Returns True if a re-execution was launched, False if already running
    under the venv python (or venv python is missing).
    """
    venv_prefix = os.path.abspath(os.path.join(_SCRIPT_DIR, ".venv"))
    if os.path.abspath(sys.prefix) == venv_prefix:
        return False  # already running under the project venv

    if not os.path.isfile(_VENV_PY):
        print(
            f"[bootstrap] python saat ini bukan venv proyek ({sys.executable})\n"
            f"[bootstrap] dan venv tidak ditemukan di {_VENV_PY}.\n"
            f"[bootstrap] Aktifkan venv dulu: .\\.venv\\Scripts\\Activate.ps1",
            file=sys.stderr,
        )
        return False  # let the original error surface

    print(
        f"[bootstrap] python saat ini bukan venv proyek ({sys.executable})\n"
        f"[bootstrap] menjalankan ulang dengan venv: {_VENV_PY}",
        file=sys.stderr,
    )
    # subprocess (bukan os.execv) agar path dengan spasi di-quote benar di Windows
    sys.exit(subprocess.call([_VENV_PY] + sys.argv))


_rerun_with_venv_python()

import numpy as np

# ═══════════════════════════════════════════════════════════════════════════
# WDAC workaround: PyAV (av) has unsigned .pyd files blocked by WDAC policy.
# faster-whisper imports av at module level for audio decoding.
# We preload a fake 'av' module into sys.modules BEFORE importing faster_whisper,
# then monkey-patch decode_audio with our own ffmpeg-based implementation.
# ═══════════════════════════════════════════════════════════════════════════

fake_av = types.ModuleType("av")
fake_av.audio = types.ModuleType("av.audio")
sys.modules["av"] = fake_av
sys.modules["av.audio"] = fake_av.audio

from faster_whisper import WhisperModel  # noqa: E402


# ─── ffmpeg-based decode_audio (replaces faster_whisper.audio.decode_audio) ───

def decode_audio(input_file, sampling_rate=16000, split_stereo=False):
    """Decode audio to float32 normalized NumPy array using system ffmpeg.

    Mirrors ``faster_whisper.audio.decode_audio`` signature and return type
    but uses subprocess+ffmpeg instead of PyAV to avoid unsigned-DLL block.

    Args:
      input_file: Path to audio file (str) or file-like object (BinaryIO).
      sampling_rate: Resample output to this sample rate (Hz).
      split_stereo: Return (left, right) tuple of arrays if True.

    Returns:
      Float32 NumPy array normalized to [-1.0, 1.0] (mono),
      or a 2-tuple (left, right) for stereo.
    """
    if isinstance(input_file, (str,)):
        input_path = input_file
    else:
        # Write BinaryIO content to temp file; ffmpeg needs a file path.
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".tmp", delete=False)
        try:
            tmp.write(input_file.read())
            tmp.close()
            input_path = tmp.name
        finally:
            pass

    channels = 2 if split_stereo else 1

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-ac", str(channels),
        "-ar", str(sampling_rate),
        "-loglevel", "quiet",
        "-",
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()

    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"ffmpeg decode failed (code {proc.returncode}): {err_msg}")

    raw = np.frombuffer(stdout, dtype=np.int16)
    audio = raw.astype(np.float32) / 32768.0

    # Cleanup temp file if we used one
    if not isinstance(input_file, (str,)):
        try:
            os.unlink(input_path)
        except OSError:
            pass

    if split_stereo:
        left_channel = audio[0::2]
        right_channel = audio[1::2]
        return left_channel, right_channel

    return audio


# Monkey-patch ALL references to decode_audio so our ffmpeg version is used
import faster_whisper.audio  # noqa: E402
import faster_whisper.transcribe  # noqa: E402
import faster_whisper  # noqa: E402

faster_whisper.audio.decode_audio = decode_audio
faster_whisper.transcribe.decode_audio = decode_audio
faster_whisper.decode_audio = decode_audio


def _stem(path: str) -> str:
    """Filename without any extension(s).  audio_sidang_OJK.mp3.mpeg -> audio_sidang_OJK."""
    name = os.path.splitext(os.path.basename(path))[0]
    while True:
        root, ext = os.path.splitext(name)
        if ext == "":
            break
        name = root
    return name


def auto_folder(audio_stem: str) -> str:
    """Build output folder: transcribe_hasil/01_nama_audio/, auto-incrementing counter.

    Scans ALL existing folders inside transcribe_hasil/ matching `XX_*` and picks max+1.
    """
    script_dir = os.path.dirname(__file__) or "."
    hasil_dir = os.path.join(script_dir, "transcribe_hasil")
    pattern = re.compile(r"^(\d{2})_.*$")
    max_n = 0
    if os.path.isdir(hasil_dir):
        for entry in os.listdir(hasil_dir):
            m = pattern.match(entry)
            if m and os.path.isdir(os.path.join(hasil_dir, entry)):
                max_n = max(max_n, int(m.group(1)))
    return os.path.join(hasil_dir, f"{max_n + 1:02d}_{audio_stem}")


def write_notulen_md(full_text: str, audio_name: str, model_name: str, lang: str, out_dir: str) -> str:
    """Generate a structured Notulen_*.md file from transcription text.

    Uses keyword heuristics to extract: peserta, topik, keputusan, tindak lanjut.
    """
    text = full_text.strip()
    paragraphs = [p.strip() for p in text.split(".") if len(p.strip()) > 5]

    # ── Extract potential unit/tim mentions ──
    unit_keywords = [
        "tim", "bagian", "divisi", "direktorat", "pusat", "unit", "biro",
        "bidang", "departemen", "fakultas", "prodi", "humas", "diti", "btd",
        "ptt", "tte", "ditlit", "pusti", "mpkm", "kde", "scopus", "ojs", "ocs",
    ]
    peserta_set = set()
    for p in paragraphs:
        for w in unit_keywords:
            pattern = re.compile(rf"({w}\s*\w*)", re.IGNORECASE)
            for m in pattern.finditer(p):
                candidate = m.group(1).strip().title()
                if len(candidate) > 2 and candidate.lower() not in (
                    "dan", "yang", "ini", "itu", "ada", "untuk", "dengan", "dalam", "pada",
                ):
                    peserta_set.add(candidate)

    peserta_list = sorted(peserta_set, key=lambda x: x.lower())[:15]
    if not peserta_list:
        peserta_list = ["Peserta rapat"]

    # ── Extract topic phrases ──
    topic_keywords = [
        "sistem", "data", "integrasi", "peluncuran", "koordinasi", "rapat",
        "pengembangan", "riset", "server", "aplikasi", "testing", "evaluasi",
        "laporan", "keuangan", "anggaran", "event", "kegiatan", "proyek",
        "penelitian", "publikasi", "jurnal", "portal", "website", "scopus",
        "approval", "diseminasi", "sosialisasi", "feedback", "notulensi",
    ]
    topics_found = []
    for p in paragraphs:
        for kw in topic_keywords:
            if kw in p.lower() and kw not in topics_found:
                topics_found.append(kw)
                break

    # ── Detect decisions / action items ──
    decision_patterns = [
        r"(?:diputuskan|disepakati|keputusan|kesimpulan)\s*(?:adalah\s*)?(.+?)(?:\.|$)",
        r"(?:akan|harus|perlu|segera|rencana)\s+(.{10,80}?)(?:\.|$)",
    ]
    decisions = []
    for p in paragraphs:
        for pat in decision_patterns:
            for m in re.finditer(pat, p, re.IGNORECASE):
                candidate = m.group(1).strip().rstrip(".")
                if 10 < len(candidate) < 120 and candidate not in decisions:
                    decisions.append(candidate)

    if not decisions:
        decisions = ["Lihat transkrip lengkap untuk detail keputusan dan tindak lanjut."]

    # ── Title & date ──
    title_raw = audio_name.replace("_", " ").replace("-", " ").title()
    title = f"Notulensi {title_raw}"
    today_str = date.today().strftime("%d %B %Y")

    # ── Build Markdown ──
    md = f"""# {title}

**Tanggal**: {today_str} (perkiraan dari waktu transkripsi)
**Model Transkripsi**: faster-whisper {model_name} ({lang.upper()})
**Sumber**: Transkrip otomatis dari rekaman audio

---

## Peserta

"""
    for i, p_name in enumerate(peserta_list, 1):
        md += f"{i}. {p_name}\n"

    md += "\n---\n\n## Agenda / Topik Bahasan\n\n"

    if topics_found:
        for t in topics_found[:10]:
            md += f"- {t.title()}\n"
    else:
        md += "- (Lihat ringkasan dan transkrip lengkap)\n"

    md += "\n---\n\n## Ringkasan Pembahasan\n\n"

    # Pick representative paragraphs
    n = len(paragraphs)
    if n <= 15:
        selected = paragraphs
    else:
        indices = (
            list(range(0, max(1, n // 3)))
            + list(range(n // 2, n // 2 + min(5, n // 6)))
            + list(range(max(n - 5, n // 2 + 5), n))
        )
        selected = [paragraphs[i] for i in sorted(set(indices)) if i < n]

    for p in selected:
        p_clean = p.strip().rstrip(".")
        if len(p_clean) > 5:
            md += f"- {p_clean}.\n"

    md += "\n---\n\n## Keputusan & Tindak Lanjut\n\n"

    for i, dec in enumerate(decisions[:10], 1):
        md += f"{i}. {dec.strip().rstrip('.')}.\n"

    md += f"""
---

## Catatan

- Transkripsi menggunakan model `{model_name}` — untuk hasil lebih akurat gunakan model `small` atau `medium`.
- Dokumen ini dibuat otomatis oleh mesin transkripsi. **Review manual sangat disarankan** sebelum distribusi.
- Transkrip lengkap tersedia di `transkrip.txt` dan `transkrip.json`.

---

*Dokumen dibuat otomatis — {today_str}*
"""

    safe_name = re.sub(r"[^\w\s-]", "", audio_name).strip()[:50]
    md_filename = f"Notulen_{safe_name}.md"
    md_path = os.path.join(out_dir, md_filename)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    return md_path


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe audio file to TXT + JSON using faster-whisper (CTranslate2).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  python transcribe.py rekaman.mp3
  python transcribe.py rapat.wav --model tiny
  python transcribe.py audio.m4a --model medium --language en
  python transcribe.py sidang.mp3 --output-dir hasil/
    python transcribe.py sidang.mp3 --with-md
        """,
    )
    parser.add_argument(
        "audio", help="Path to audio file (mp3, wav, m4a, etc.)"
    )
    parser.add_argument(
        "--model", default="small",
        help="Whisper model: tiny, base, small, medium, large, tiny.en, base.en, etc. "
             "(default: small)"
    )
    parser.add_argument(
        "--language", default="id",
        help="Language code (default: id)"
    )
    parser.add_argument(
        "--device", default="cpu",
        help="Compute device: cpu or cuda (default: cpu)"
    )
    parser.add_argument(
        "--compute-type", default="int8",
        help="CTranslate2 compute type: int8, int16, float32 (default: int8)"
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Manual output directory (overrides auto-folder, e.g. hasil/)"
    )
    parser.add_argument(
        "--with-md", action="store_true",
        help="Generate legacy Notulen_*.md in addition to TXT + JSON"
    )

    args = parser.parse_args()

    audio = os.path.abspath(args.audio)
    if not os.path.exists(audio):
        print(f"ERROR: audio file not found: {audio}")
        sys.exit(1)

    stem = _stem(audio)

    if args.output_dir:
        out_dir = os.path.abspath(args.output_dir)
    else:
        out_dir = auto_folder(stem)

    out_txt = os.path.join(out_dir, "transkrip.txt")
    out_json = os.path.join(out_dir, "transkrip.json")

    print(f"Audio        : {audio}")
    print(f"Folder       : {out_dir}")
    print(f"Model        : {args.model}")
    print(f"Lang         : {args.language}")
    print(f"Device       : {args.device}")
    print(f"Compute type : {args.compute_type}")
    print()

    # ── Check system ffmpeg ────────────────────────────────────────────────
    result = subprocess.run(
        ["ffmpeg", "-version"], capture_output=True,
    )
    if result.returncode != 0:
        print("ERROR: ffmpeg not found on system PATH.")
        print("Install: winget install Gyan.FFmpeg.Essentials")
        sys.exit(1)

    # ── Load model ─────────────────────────────────────────────────────────
    print(f"Loading Whisper model '{args.model}'...")
    model = WhisperModel(
        args.model, device=args.device, compute_type=args.compute_type,
    )

    print("Transcribing (first run downloads model from HuggingFace, may take a while)...")
    start = time.time()

    # faster-whisper: transcribe() returns (segments_iter, info)
    segments_iter, info = model.transcribe(audio, language=args.language)

    # Collect segments
    raw_segments = []
    full_text_parts = []
    for s in segments_iter:
        raw_segments.append({
            "start": round(s.start, 2),
            "end": round(s.end, 2),
            "text": s.text.strip(),
        })
        full_text_parts.append(s.text.strip())

    elapsed = time.time() - start
    print(f"Done in {elapsed:.0f}s ({elapsed/60:.1f}m)")

    # ── Create output folder after successful transcription ────────────────
    os.makedirs(out_dir, exist_ok=True)

    # ── Group raw segments into multi-sentence chunks ──────────────────────
    segments = []
    buf = []
    t_start = None
    sentence_count = 0

    for seg in raw_segments:
        text = seg["text"]
        if t_start is None:
            t_start = seg["start"]
        buf.append(text)
        if text.rstrip().endswith((".", "?", "!")):
            sentence_count += 1
        combined = " ".join(buf)
        if sentence_count >= 2 or len(combined) >= 250:
            merged_text = re.sub(r"\s+([.,!?])", r"\1", combined).strip()
            segments.append({
                "start": t_start,
                "end": round(seg["end"], 2),
                "text": merged_text,
            })
            buf = []
            t_start = None
            sentence_count = 0

    # Flush remaining buffer
    if buf and t_start is not None:
        merged_text = re.sub(r"\s+([.,!?])", r"\1", " ".join(buf)).strip()
        segments.append({
            "start": t_start,
            "end": raw_segments[-1]["end"],
            "text": merged_text,
        })

    full_text = " ".join(full_text_parts).strip()

    # ── Write TXT ──────────────────────────────────────────────────────────
    wrapped = textwrap.fill(full_text, width=100)
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(wrapped)

    # ── Write JSON ─────────────────────────────────────────────────────────
    output = {
        "source": audio,
        "model": args.model,
        "language": info.language,
        "language_probability": round(info.language_probability, 4),
        "duration_s": round(elapsed, 1),
        "segments": segments,
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print()
    print(f"TXT  -> {out_txt}")
    print(f"JSON -> {out_json}")

    # ── Optional legacy Notulen MD ─────────────────────────────────────────
    if args.with_md:
        print("Generating notulen MD...")
        md_path = write_notulen_md(
            full_text, stem, args.model, args.language, out_dir,
        )
        print(f"MD   -> {md_path}")


if __name__ == "__main__":
    main()

