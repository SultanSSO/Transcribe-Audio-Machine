"""Output writer — TXT + JSON, kompatibel dengan struktur v3."""

import json
import os
import textwrap


def write_txt(out_dir, full_text):
    """Write line-wrapped plain text to transkrip.txt."""
    out_txt = os.path.join(out_dir, "transkrip.txt")
    wrapped = textwrap.fill(full_text, width=100)
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(wrapped)
    return out_txt


def write_json(out_dir, source, model, language, language_probability,
               elapsed, segments):
    """Write full metadata to transkrip.json."""
    out_json = os.path.join(out_dir, "transkrip.json")
    output = {
        "source": source,
        "model": model,
        "language": language,
        "language_probability": round(language_probability, 4),
        "duration_s": round(elapsed, 1),
        "segments": segments,
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    return out_json
