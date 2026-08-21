"""Segment merging — grup segmen mentah menjadi chunk multi-kalimat.

Logika dipertahankan identik dengan transcribe.py v3:
chunk dianggap final saat >= 2 kalimat ATAU >= 250 karakter.
"""

import re


def merge_segments(raw_segments):
    """Group raw segments into multi-sentence chunks.

    Args:
      raw_segments: list of dict {start, end, text} (mentah dari model).

    Returns:
      list of dict {start, end, text} yang sudah di-merge.
    """
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

    return segments
