"""CLI Audio Transcriber — Whisper + ffmpeg (self-contained venv).

Usage:
    # activate venv first
    .venv\\Scripts\\Activate.ps1

    # transcribe audio -> auto-creates folder 01_30-07_OJK/ with TXT + JSON
    python transcribe.py audio_sidang_OJK.mp3.mpeg

    # specify model, language, or custom folder name
    python transcribe.py sidang.mp3 --name OJK --model medium --language en

    # manual output directory (skips auto-folder)
    python transcribe.py sidang.mp3 --output-dir hasil/

Default behavior:
    Auto-creates a folder `XX_DD-MM_NAME/` inside 03_notulen_enggine/,
    where XX = auto-increment counter, DD-MM = today's date,
    NAME = derived from audio filename (or --name).

Output (inside auto-folder):
    transkrip.txt              plain full text
    transkrip_segmented.txt    text + timestamps
    transkrip.json             full metadata (segments, timing, model info)
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import date

import whisper

# --- ffmpeg: auto-include venv's Scripts/ on PATH (where ffmpeg.exe lives) ---
_VENV_SCRIPTS = os.path.join(os.path.dirname(__file__), ".venv", "Scripts")
if os.path.isdir(_VENV_SCRIPTS):
    os.environ["PATH"] = _VENV_SCRIPTS + os.pathsep + os.environ.get("PATH", "")


def _stem(path: str) -> str:
    """Filename without any extension(s).  audio_sidang_OJK.mp3.mpeg -> audio_sidang_OJK."""
    name = os.path.splitext(os.path.basename(path))[0]
    while True:
        root, ext = os.path.splitext(name)
        if ext == "":
            break
        name = root
    return name


def _derive_name(stem: str) -> str:
    """Derive a short uppercase name from the filename stem.

    audio_sidang_OJK -> OJK
    rekaman_rapat_ugm -> RAPAT_UGM
    sidang -> SIDANG
    """
    clean = re.sub(r'^(audio|rekaman|record|voice|file)[\-_]\s*', '', stem, flags=re.IGNORECASE)
    parts = clean.replace('-', '_').split('_')
    parts = [p for p in parts if p]
    if len(parts) >= 2:
        short = [p for p in parts if len(p) >= 2]
        if short:
            parts = short
        name = '_'.join(parts[-2:]) if len(parts) >= 2 else parts[-1]
    else:
        name = parts[0] if parts else clean
    return name[:20].upper().rstrip('_-')


def auto_folder(short_name: str) -> str:
    """Build output folder: 01_30-07_OJK/ inside script directory, auto-incrementing counter."""
    script_dir = os.path.dirname(__file__) or "."
    today = date.today().strftime("%d-%m")
    pattern = re.compile(r"^(\d{2})_\d{2}-\d{2}_(.*)$")
    max_n = 0
    for entry in os.listdir(script_dir):
        m = pattern.match(entry)
        if m and os.path.isdir(os.path.join(script_dir, entry)):
            max_n = max(max_n, int(m.group(1)))
    return os.path.join(script_dir, f"{max_n + 1:02d}_{today}_{short_name}")


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe audio file to TXT + JSON using OpenAI Whisper.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  python transcribe.py rekaman.mp3
  python transcribe.py rapat.wav --name RAPAT --model tiny
  python transcribe.py audio.m4a --model medium --language en
  python transcribe.py sidang.mp3 --output-dir hasil/
        """,
    )
    parser.add_argument("audio", help="Path to audio file (mp3, wav, m4a, etc.)")
    parser.add_argument("--model", default="small",
                        help="Whisper model: tiny, base, small, medium, large (default: small)")
    parser.add_argument("--language", default="id",
                        help="Language code (default: id)")
    parser.add_argument("--name", default=None,
                        help="Short name for output folder (default: derived from audio filename)")
    parser.add_argument("--output-dir", default=None,
                        help="Manual output directory (overrides auto-folder, e.g. hasil/)")

    args = parser.parse_args()

    audio = os.path.abspath(args.audio)
    if not os.path.exists(audio):
        print(f"ERROR: audio file not found: {audio}")
        sys.exit(1)

    stem = _stem(audio)
    short_name = args.name if args.name else _derive_name(stem)

    if args.output_dir:
        out_dir = os.path.abspath(args.output_dir)
    else:
        out_dir = auto_folder(short_name)

    os.makedirs(out_dir, exist_ok=True)

    out_txt = os.path.join(out_dir, "transkrip.txt")
    out_seg = os.path.join(out_dir, "transkrip_segmented.txt")
    out_json = os.path.join(out_dir, "transkrip.json")

    print(f"Audio  : {audio}")
    print(f"Folder : {out_dir}")
    print(f"Model  : {args.model}")
    print(f"Lang   : {args.language}")
    print()

    print(f"Loading Whisper model '{args.model}'...")
    model = whisper.load_model(args.model)

    print("Transcribing...")
    start = time.time()
    result = model.transcribe(audio, language=args.language)
    elapsed = time.time() - start
    print(f"Done in {elapsed:.0f}s ({elapsed/60:.1f}m)")

    segments = []
    for seg in result["segments"]:
        segments.append({
            "start": round(seg["start"], 2),
            "end": round(seg["end"], 2),
            "text": seg["text"].strip(),
        })

    # plain full text
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(result["text"].strip())

    # segmented with timestamps
    with open(out_seg, "w", encoding="utf-8") as f:
        for seg in segments:
            ts = f"[{seg['start']:.1f}s - {seg['end']:.1f}s]"
            f.write(f"{ts} {seg['text']}\n")

    # JSON metadata
    output = {
        "source": audio,
        "model": args.model,
        "language": result.get("language", args.language),
        "duration_s": round(elapsed, 1),
        "segments": segments,
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print()
    print(f"TXT  -> {out_txt}")
    print(f"TXT+ -> {out_seg}")
    print(f"JSON -> {out_json}")


if __name__ == "__main__":
    main()

