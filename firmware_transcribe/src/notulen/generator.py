"""Notulen MD generator — heuristik (identik dengan transcribe.py v3).

Bukan AI: ekstraksi peserta/topik/keputusan via keyword heuristic.
Selalu sarankan review manual.
"""

import os
import re
from datetime import date


def write_notulen_md(full_text, audio_name, model_name, lang, out_dir):
    """Generate structured Notulen_*.md dari teks transkripsi.

    Returns path file MD yang ditulis.
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
                    "dan", "yang", "ini", "itu", "ada", "untuk", "dengan",
                    "dalam", "pada",
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
