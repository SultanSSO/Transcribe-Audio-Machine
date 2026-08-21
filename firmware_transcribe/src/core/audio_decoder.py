"""Audio decoding via system ffmpeg (WDAC-safe, no PyAV).

Menggantikan ``faster_whisper.audio.decode_audio`` yang bergantung PyAV
(terblokir kebijakan WDAC di mesin ini). Output float32 mono 16 kHz.
"""

import os
import subprocess

import numpy as np


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


def ffmpeg_available() -> bool:
    """Return True if system ffmpeg is on PATH."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, timeout=15
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
