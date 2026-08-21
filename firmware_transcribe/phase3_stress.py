"""Phase 3 stress test — transkripsi audio panjang (meet-teknis-MCE.mp3, 1j42m).

Memakai parameter anti-halusinasi baru (VAD, condition_on_previous_text=False,
hallucination_silence_threshold). Memonitor RSS memori tiap 60 detik.
Output: transcribe_hasil/07_meet-teknis-MCE/ + ringkasan JSON.
"""

import json
import os
import sys
import time

import psutil

from src.core.engine import TranscribeEngine

AUDIO = r"D:\SULTAN NAUFAL\KULIAH\MAGANG\MAGANG BTD\proyek\workspace\5_mesin_v3\meet-teknis-MCE.mp3"
PROJ = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(PROJ, "transcribe_hasil", "07_meet-teknis-MCE")

proc = psutil.Process()
t0 = time.time()
last_report = 0
stats = {"peak_mb": 0, "last_mb": 0, "reports": []}


def on_progress(pct, msg):
    global last_report
    now = time.time()
    if now - last_report >= 60:
        last_report = now
        mb = proc.memory_info().rss / 1048576
        stats["peak_mb"] = max(stats["peak_mb"], mb)
        stats["last_mb"] = mb
        stats["reports"].append({"t": round(now - t0), "pct": pct, "mb": round(mb, 1)})
        print(f"[{now - t0:6.0f}s] {pct:3d}% | RSS {mb:6.0f} MB", flush=True)


def on_segment(start, end, text):
    pass  # tidak di-print — ribuan segmen


print(f"START {time.strftime('%H:%M:%S')} | audio 6161s (1j42m) | model small int8 CPU", flush=True)
try:
    r = TranscribeEngine.transcribe(
        AUDIO,
        {"model": "small", "language": "id", "output_dir": OUT},
        {"on_progress": on_progress, "on_segment": on_segment},
    )
except Exception as e:
    print(f"FAIL: {type(e).__name__}: {e}", flush=True)
    sys.exit(1)

elapsed = time.time() - t0
mb = proc.memory_info().rss / 1048576
stats["peak_mb"] = max(stats["peak_mb"], mb)
stats["last_mb"] = mb

meta = r["metadata"]
txt_path = r["txt_path"]
json_path = r["json_path"]
full_text = r["full_text"]
words = len(full_text.split())
print(f"DONE {time.strftime('%H:%M:%S')} | proses {elapsed:.0f}s ({elapsed/60:.1f}m)", flush=True)
print(f"segmen: {meta['segment_count']} | audio: {meta['audio_duration_s']}s "
      f"| proses: {meta['duration_s']}s | peak RSS: {stats['peak_mb']:.0f} MB", flush=True)
print(f"kata: {words} | TXT: {txt_path} | JSON: {json_path}", flush=True)
print(f"teks awal: {full_text[:150]}", flush=True)

summary = {
    "ok": True,
    "elapsed_s": round(elapsed, 1),
    "metadata": meta,
    "word_count": words,
    "text_chars": len(full_text),
    "stats": stats,
    "txt_path": txt_path,
    "json_path": json_path,
}
with open(os.path.join(OUT, "_phase3_summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print("summary -> transcribe_hasil/07_meet-teknis-MCE/_phase3_summary.json", flush=True)
