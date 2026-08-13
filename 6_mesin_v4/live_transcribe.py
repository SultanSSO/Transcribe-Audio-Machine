"""CLI Live Transcriber v4 STANDALONE — rekam mikrofon + transkripsi real-time.

Satu file mandiri: tidak ada dependensi ke modul lain di folder ini.
Rekam audio langsung dari perangkat input (mikrofon fisik atau virtual
cable seperti VB-CABLE) via ffmpeg dshow, transkripsikan per-chunk dengan
faster-whisper (default model small, bahasa id). Transkrip ditulis
incremental ke transkrip.txt, segmen ke transkrip.json, dan notulen MD
dibuat otomatis saat sesi dihentikan (Ctrl+C).

Usage:
    .venv\\Scripts\\python.exe live_transcribe.py --list-devices
    .venv\\Scripts\\python.exe live_transcribe.py
    .venv\\Scripts\\python.exe live_transcribe.py --device "CABLE Output (VB-Audio Virtual Cable)"
    .venv\\Scripts\\python.exe live_transcribe.py --model small --language id --chunk-sec 15
    .venv\\Scripts\\python.exe live_transcribe.py --max-min 30
    .venv\\Scripts\\python.exe live_transcribe.py --once

Output (folder auto: transcribe_hasil/XX_live_YYYYMMDD-HHMM/):
    transkrip.txt   transkrip incremental (real-time, append per chunk)
    transkrip.json  metadata + segmen (timing sesi)
    Notulen_*.md    notulen otomatis (dibuat saat sesi berhenti)

Prerequisites:
    - System ffmpeg (winget install Gyan.FFmpeg.Essentials)
    - Python venv dengan faster-whisper (lihat requirements.txt)
"""

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import textwrap  # noqa: F401  (kompatibilitas dengan kode notulen warisan)
import time
import types
from datetime import date

# ═══════════════════════════════════════════════════════════════════════════
# Auto-bootstrap: re-run with project venv if current python isn't it.
# ═══════════════════════════════════════════════════════════════════════════
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_VENV_PY = os.path.join(_SCRIPT_DIR, ".venv", "Scripts", "python.exe")


def _rerun_with_venv_python():
    venv_prefix = os.path.abspath(os.path.join(_SCRIPT_DIR, ".venv"))
    if os.path.abspath(sys.prefix) == venv_prefix:
        return False
    if not os.path.isfile(_VENV_PY):
        print(
            f"[bootstrap] bukan venv proyek ({sys.executable}) dan venv tidak ada di {_VENV_PY}.",
            file=sys.stderr,
        )
        return False
    print(f"[bootstrap] menjalankan ulang dengan venv: {_VENV_PY}", file=sys.stderr)
    sys.exit(subprocess.call([_VENV_PY] + sys.argv))


_rerun_with_venv_python()

# ═══════════════════════════════════════════════════════════════════════════
# WDAC workaround (di-inline dari mesin v3): PyAV (.pyd) diblokir kebijakan
# Windows Defender Application Control, jadi decode audio diganti ffmpeg.
# ═══════════════════════════════════════════════════════════════════════════
fake_av = types.ModuleType("av")
fake_av.audio = types.ModuleType("av.audio")
sys.modules["av"] = fake_av
sys.modules["av.audio"] = fake_av.audio

import numpy as np  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402


def decode_audio(input_file, sampling_rate=16000, split_stereo=False):
    """Decode audio ke float32 NumPy (mono, [-1,1]) via ffmpeg subprocess.

    Menggantikan faster_whisper.audio.decode_audio (yang butuh PyAV) agar
    lolos kebijakan WDAC.
    """
    if isinstance(input_file, (str,)):
        input_path = input_file
    else:
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

    if not isinstance(input_file, (str,)):
        try:
            os.unlink(input_path)
        except OSError:
            pass

    if split_stereo:
        return audio[0::2], audio[1::2]
    return audio


import faster_whisper.audio  # noqa: E402
import faster_whisper.transcribe  # noqa: E402
import faster_whisper  # noqa: E402

faster_whisper.audio.decode_audio = decode_audio
faster_whisper.transcribe.decode_audio = decode_audio
faster_whisper.decode_audio = decode_audio


# ═══════════════════════════════════════════════════════════════════════════
# auto_folder — penomoran urut folder output (di-inline dari mesin v3)
# ═══════════════════════════════════════════════════════════════════════════
def auto_folder(audio_stem: str) -> str:
    """Build output folder: transcribe_hasil/XX_nama_audio/, auto-incrementing."""
    hasil_dir = os.path.join(_SCRIPT_DIR, "transcribe_hasil")
    pattern = re.compile(r"^(\d{2})_.*$")
    max_n = 0
    if os.path.isdir(hasil_dir):
        for entry in os.listdir(hasil_dir):
            m = pattern.match(entry)
            if m and os.path.isdir(os.path.join(hasil_dir, entry)):
                max_n = max(max_n, int(m.group(1)))
    return os.path.join(hasil_dir, f"{max_n + 1:02d}_{audio_stem}")


# ═══════════════════════════════════════════════════════════════════════════
# write_notulen_md — generator notulen (di-inline dari mesin v3)
# ═══════════════════════════════════════════════════════════════════════════
def write_notulen_md(full_text: str, audio_name: str, model_name: str, lang: str, out_dir: str) -> str:
    """Generate Notulen_*.md dari teks transkripsi (heuristik template)."""
    text = full_text.strip()
    paragraphs = [p.strip() for p in text.split(".") if len(p.strip()) > 5]

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

    title_raw = audio_name.replace("_", " ").replace("-", " ").title()
    title = f"Notulensi {title_raw}"
    today_str = date.today().strftime("%d %B %Y")

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


# ═══════════════════════════════════════════════════════════════════════════
# Live recording (ffmpeg dshow)
# ═══════════════════════════════════════════════════════════════════════════
def list_devices() -> list:
    """Enumerasi perangkat audio input via ffmpeg dshow."""
    try:
        proc = subprocess.run(
            ["ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        print("ERROR: ffmpeg tidak ditemukan di PATH. Install: winget install Gyan.FFmpeg.Essentials")
        sys.exit(1)
    out = (proc.stdout or "") + (proc.stderr or "")
    devices = []
    for line in out.splitlines():
        m = re.search(r'"([^"]+)"\s*\((audio|video)\)', line, re.IGNORECASE)
        if m and m.group(2).lower() == "audio":
            name = m.group(1).strip()
            if name and name not in devices:
                devices.append(name)
    return devices


def record_chunk(device: str, seconds: float, out_wav: str, sample_rate: int = 16000) -> None:
    """Rekam `seconds` detik dari perangkat input ke WAV mono 16 kHz via ffmpeg dshow."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "dshow",
        "-i", f"audio={device}",
        "-ac", "1",
        "-ar", str(sample_rate),
        "-t", str(seconds),
        "-f", "wav",
        out_wav,
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"ffmpeg capture gagal (code {proc.returncode}): {err[-500:]}")


def main():
    parser = argparse.ArgumentParser(
        description="Rekam perangkat input + transkripsi real-time (faster-whisper + ffmpeg dshow).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--model", default="small", help="Model Whisper (default: small)")
    parser.add_argument("--language", default="id", help="Kode bahasa (default: id)")
    parser.add_argument("--device", default=None,
                        help="Nama perangkat input (lihat --list-devices). Default: perangkat audio pertama.")
    parser.add_argument("--list-devices", action="store_true",
                        help="Tampilkan daftar perangkat audio input lalu keluar.")
    parser.add_argument("--chunk-sec", type=float, default=15.0,
                        help="Durasi tiap chunk rekaman dalam detik (default: 15).")
    parser.add_argument("--max-min", type=float, default=None,
                        help="Auto-stop setelah N menit (default: tanpa batas, Ctrl+C untuk berhenti).")
    parser.add_argument("--once", action="store_true",
                        help="Rekam satu chunk lalu selesai (untuk tes).")
    parser.add_argument("--compute-type", default="int8",
                        help="CTranslate2 compute type (default: int8).")
    args = parser.parse_args()

    if args.list_devices:
        devices = list_devices()
        if not devices:
            print("Tidak ada perangkat audio input terdeteksi.")
            sys.exit(1)
        print("Perangkat audio input terdeteksi:")
        for i, d in enumerate(devices, 1):
            print(f"  {i}. {d}")
        return

    # ── Cek ffmpeg ────────────────────────────────────────────────────────
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except Exception:
        print("ERROR: ffmpeg tidak ditemukan. Install: winget install Gyan.FFmpeg.Essentials")
        sys.exit(1)

    # ── Pilih perangkat input ─────────────────────────────────────────────
    devices = list_devices()
    if not devices:
        print("ERROR: tidak ada perangkat input terdeteksi. Coba: python live_transcribe.py --list-devices")
        sys.exit(1)
    device = args.device or devices[0]
    if device not in devices:
        print(f"ERROR: perangkat '{device}' tidak ada. Terdeteksi: {devices}")
        sys.exit(1)
    print(f"Perangkat     : {device}")
    print(f"Model         : {args.model}")
    print(f"Bahasa        : {args.language}")
    print(f"Chunk         : {args.chunk_sec}s")

    # ── Load model ─────────────────────────────────────────────────────────
    print(f"Loading Whisper model '{args.model}'...")
    model = WhisperModel(args.model, device="cpu", compute_type=args.compute_type)
    print("Model siap. Rekaman dimulai — Ctrl+C untuk berhenti.\n")

    # ── Folder output auto ─────────────────────────────────────────────────
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    out_dir = auto_folder(f"live_{stamp}")
    os.makedirs(out_dir, exist_ok=True)
    out_txt = os.path.join(out_dir, "transkrip.txt")
    print(f"Output        : {out_dir}\n")

    tmp_wav = os.path.join(out_dir, "_chunk_tmp.wav")
    session_start = time.time()
    segments_all = []
    transcript_parts = []
    chunk_no = 0
    info = None

    def ts_label():
        return dt.datetime.now().strftime("%H:%M:%S")

    try:
        while True:
            chunk_no += 1
            print(f"[{ts_label()}] Merekam chunk {chunk_no} ({args.chunk_sec:.0f}s)...", end="", flush=True)
            record_chunk(device, args.chunk_sec, tmp_wav)
            print(" transkripsi...", flush=True)

            # Konteks lanjutan: 200 karakter terakhir agar chunk tersambung
            tail = " ".join(transcript_parts)[-200:]
            seg_iter, info = model.transcribe(
                tmp_wav, language=args.language,
                initial_prompt=tail if tail.strip() else None,
            )
            chunk_text_parts = []
            for s in seg_iter:
                rel = round(session_start + (chunk_no - 1) * args.chunk_sec + s.start, 2)
                segments_all.append({
                    "start": rel,
                    "end": round(rel + (s.end - s.start), 2),
                    "text": s.text.strip(),
                })
                chunk_text_parts.append(s.text.strip())

            chunk_text = " ".join(chunk_text_parts).strip()
            if chunk_text:
                transcript_parts.append(chunk_text)
                print(f"[{ts_label()}] {chunk_text}")
                with open(out_txt, "a", encoding="utf-8") as f:
                    f.write(f"[{ts_label()}] {chunk_text}\n")
            else:
                print(f"[{ts_label()}] (hening — tidak ada ucapan terdeteksi)")

            if args.once:
                break
            if args.max_min and (time.time() - session_start) / 60 >= args.max_min:
                print(f"[{ts_label()}] Mencapai batas {args.max_min} menit, berhenti.")
                break
    except KeyboardInterrupt:
        print(f"\n[{ts_label()}] Sesi dihentikan oleh pengguna.")

    try:
        os.unlink(tmp_wav)
    except OSError:
        pass

    # ── Finalisasi: JSON + Notulen MD ──────────────────────────────────────
    full_text = " ".join(transcript_parts).strip()
    elapsed = round(time.time() - session_start, 1)

    out_json = os.path.join(out_dir, "transkrip.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({
            "source": f"live:input ({device})",
            "model": args.model,
            "language": args.language,
            "language_probability": round(getattr(info, "language_probability", 1.0), 4),
            "duration_s": elapsed,
            "chunks": chunk_no,
            "segments": segments_all,
        }, f, ensure_ascii=False, indent=2)

    print(f"\nTXT  -> {out_txt}")
    print(f"JSON -> {out_json}")

    if full_text:
        md_path = write_notulen_md(
            full_text, f"live_{stamp}", args.model, args.language, out_dir,
        )
        print(f"MD   -> {md_path}")
    else:
        print("Tidak ada teks yang tertranskripsi — notulen MD dilewati.")


if __name__ == "__main__":
    main()
