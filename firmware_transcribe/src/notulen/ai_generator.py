"""AI Notulen Generator — rangkum transkrip via LLM lokal (9router).

Alur: baca transkrip (TXT + JSON) dari folder hasil → kirim ke router lokal
(OpenAI-compatible) → notulen markdown → render langsung ke DOCX via
MdToDocx.from_text. Tidak ada file .md yang disimpan atau dipakai.

Konfigurasi (env var, bisa di .env project):
    TRANSCRIBE_AI_BASE_URL   default http://localhost:20128/v1
    TRANSCRIBE_AI_MODEL      default gemini/gemini-3.7-flash
    TRANSCRIBE_AI_API_KEY    default "" (9router lokal tanpa key)

Callback contract (dipanggil dari thread worker):
    on_log(message)
    on_progress(percent, message)
    on_finished(result: dict)
    on_error(error)
"""

import os
import re
import time
from datetime import datetime
from pathlib import Path

import httpx

from src.export.docx_converter import MdToDocx

AI_BASE_URL = os.environ.get("TRANSCRIBE_AI_BASE_URL", "http://localhost:20128/v1")
AI_MODEL = os.environ.get("TRANSCRIBE_AI_MODEL", "gemini/gemini-3.7-flash")
AI_API_KEY = os.environ.get("TRANSCRIBE_AI_API_KEY", "")

MAX_INPUT_CHARS = 180_000  # transkrip lebih panjang dipotong (model 1M context, ini batas hemat)


def ai_config() -> dict:
    """Konfigurasi AI saat ini (dipakai /api/env + log)."""
    return {"base_url": AI_BASE_URL, "model": AI_MODEL, "key_set": bool(AI_API_KEY)}


def load_transcript(output_dir: str) -> tuple:
    """Baca transkrip dari folder hasil.

    Returns (full_text, meta). Sumber: transkrip.txt; fallback transkrip.json
    (gabung segmen). Meta: {source_name, audio_duration}.
    """
    out = Path(output_dir)
    txt = out / "transkrip.txt"
    js = out / "transkrip.json"

    meta = {"source_name": out.name, "audio_duration": None}

    if txt.is_file():
        full_text = txt.read_text(encoding="utf-8").strip()
    elif js.is_file():
        import json
        data = json.loads(js.read_text(encoding="utf-8"))
        segs = data.get("segments", data if isinstance(data, list) else [])
        full_text = " ".join(
            str(s.get("text", "")).strip() for s in segs if isinstance(s, dict)
        ).strip()
        meta["audio_duration"] = data.get("audio_duration_s") if isinstance(data, dict) else None
    else:
        raise FileNotFoundError(
            f"transkrip.txt / transkrip.json tidak ditemukan di {output_dir}. "
            "Transkripsikan audio dulu sebelum membuat notulen AI."
        )

    if not full_text:
        raise ValueError("Transkrip kosong — tidak bisa membuat notulen AI.")

    return full_text, meta


def build_prompt(full_text: str, meta: dict) -> tuple:
    """Bangun (system, user) prompt. Transkrip panjang dipotong + ditandai."""
    truncated = False
    text = full_text
    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS]
        truncated = True

    system = (
        "Kamu adalah notulis rapat profesional. Tugasmu mengubah transkrip mentah "
        "menjadi notulen yang rapi, terstruktur, dan jelas."
    )

    dur_str = meta["audio_duration"] if meta["audio_duration"] is not None else "tidak diketahui"
    trunc_note = "CATATAN: transkrip asli lebih panjang dari batas, hanya bagian awal yang dikirim.\n" if truncated else ""

    user = f"""Ubahlah transkrip rapat berikut menjadi notulen yang rapi, terstruktur, dan jelas.

ATURAN:
1. Tulis dalam Bahasa Indonesia formal dan mudah dibaca.
2. Susun struktur terbaik menurutmu. Contoh bagian yang bisa dipakai (hanya jika datanya ada di transkrip):
   - Ringkasan eksekutif (2-4 kalimat)
   - Konteks / latar belakang rapat
   - Pembahasan per topik (poin-poin penting)
   - Keputusan yang disepakati
   - Tindak lanjut / action items (sebutkan penanggung jawab & tenggat bila disebut di transkrip)
   - Catatan
   Jangan memaksakan bagian yang tidak didukung data.
3. HANYA gunakan informasi yang ada di transkrip. JANGAN menambah, menebak, atau mengarang
   nama, angka, tanggal, keputusan, atau fakta apa pun. Bagian yang tidak jelas atau terpotong
   tulis "[tidak jelas]".
4. Rangkum poin penting — jangan menyalin seluruh transkrip kata demi kata.
5. Format output markdown ringan: # untuk judul, ## untuk bagian, - untuk poin, tabel jika cocok.
   Jangan menulis penjelasan di luar isi notulen.

Informasi berkas:
- Nama berkas audio: {meta['source_name']}
- Durasi audio: {dur_str} detik
{trunc_note}=== MULAI TRANSKRIP ===
{text}
=== AKHIR TRANSKRIP ===
"""
    return system, user


def call_llm(system: str, user: str) -> str:
    """Panggil router lokal (OpenAI-compatible) — non-streaming, retry 1x."""
    url = f"{AI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if AI_API_KEY:
        headers["Authorization"] = f"Bearer {AI_API_KEY}"

    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        "max_tokens": 8192,
        "stream": False,
    }

    last_err = None
    for attempt in (1, 2):
        try:
            with httpx.Client(timeout=600.0) as client:
                r = client.post(url, headers=headers, json=payload)
            if r.status_code == 200:
                data = r.json()
                content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
                if not content or not content.strip():
                    raise ValueError("Respons LLM kosong.")
                return content.strip()
            last_err = f"HTTP {r.status_code}: {r.text[:300]}"
        except httpx.HTTPError as e:
            last_err = f"koneksi gagal: {e}"
        time.sleep(1.5)

    raise ConnectionError(
        f"AI tidak bisa dihubungi ({AI_MODEL} @ {AI_BASE_URL}): {last_err}. "
        "Pastikan 9router / router lokal berjalan."
    )


def _md_to_plain(text: str) -> str:
    """Strip markdown syntax ringan untuk file preview .txt."""
    t = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)      # heading
    t = re.sub(r"^\s*[-*]\s+", "- ", t, flags=re.MULTILINE)       # bullet
    t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.MULTILINE)        # numbered
    t = re.sub(r"\|", " | ", t)                                    # table pipes
    t = re.sub(r"^[\s|:-]+$", "", t, flags=re.MULTILINE)           # table separator
    t = re.sub(r"[*_`~]", "", t)                                   # inline
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)                 # links
    return t.strip()


def generate_notulen_docx(output_dir: str, callbacks: dict = None) -> dict:
    """Buat notulen AI dari transkrip di output_dir → simpan DOCX + TXT preview.

    Returns {"docx_path", "txt_path", "model", "chars_in", "duration_s", "truncated"}
    """
    cb = callbacks or {}

    def log(msg):
        if cb.get("on_log"):
            cb["on_log"](msg)

    def progress(pct, msg):
        if cb.get("on_progress"):
            cb["on_progress"](pct, msg)

    try:
        start = time.time()
        log("AI notulen: membaca transkrip...")
        full_text, meta = load_transcript(output_dir)
        log(f"AI notulen: {len(full_text):,} karakter dari {meta['source_name']}.")

        progress(15, "Menyusun prompt...")
        system, user = build_prompt(full_text, meta)
        truncated = "CATATAN: transkrip asli lebih panjang" in user

        progress(25, f"Memanggil AI ({AI_MODEL})...")
        log(f"AI notulen: memanggil {AI_MODEL} @ {AI_BASE_URL} — ini bisa memakan beberapa menit.")
        notulen_md = call_llm(system, user)
        log(f"AI notulen: respons diterima ({len(notulen_md):,} karakter).")

        progress(80, "Merender DOCX...")
        out = Path(output_dir)
        stem = meta["source_name"]
        m = re.match(r"^\d{2}_(.+)$", stem)
        if m:
            stem = m.group(1)
        stem = re.sub(r"[^\w\- ]", "", stem).strip()[:50] or "notulen"

        docx_path = out / f"NotulenAI_{stem}.docx"
        MdToDocx.from_text(notulen_md, str(docx_path))
        log(f"AI notulen: DOCX -> {docx_path}")

        txt_path = out / "notulen_ai.txt"
        plain = _md_to_plain(notulen_md)
        header = (
            f"NOTULEN AI — {meta['source_name']}\n"
            f"Dibuat: {datetime.now().strftime('%d %B %Y %H:%M')} | Model: {AI_MODEL}\n"
            f"Transkrip: {len(full_text):,} karakter | Ringkasan otomatis AI — review manual disarankan.\n"
            + "=" * 60 + "\n\n"
        )
        txt_path.write_text(header + plain + "\n", encoding="utf-8")

        duration_s = round(time.time() - start, 1)
        result = {
            "docx_path": str(docx_path),
            "txt_path": str(txt_path),
            "model": AI_MODEL,
            "chars_in": len(full_text),
            "duration_s": duration_s,
            "truncated": truncated,
        }
        progress(100, "Selesai.")
        log(f"AI notulen selesai dalam {duration_s}s.")
        if cb.get("on_finished"):
            cb["on_finished"](result)
        return result

    except Exception as e:  # noqa: BLE001
        if cb.get("on_error"):
            cb["on_error"](str(e))
        raise
