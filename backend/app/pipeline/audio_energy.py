"""Audio loudness analysis: find energy spikes (laughter, shouting) to boost clip scores."""
from __future__ import annotations

import subprocess

import numpy as np

from ..errors import RenderError

SAMPLE_RATE = 16000
WINDOW_SECONDS = 0.5


def compute_energy_profile(media_path: str) -> tuple[np.ndarray, float]:
    """Return (per-window RMS normalized to 0..1, window_seconds)."""
    cmd = [
        "ffmpeg", "-v", "error",
        "-i", media_path,
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-f", "s16le", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=True)
    except FileNotFoundError as e:
        raise RenderError("ffmpeg is not installed or not on PATH.", detail=str(e)) from e
    except subprocess.CalledProcessError as e:
        raise RenderError("Failed to decode audio for energy analysis.",
                          detail=e.stderr.decode(errors="replace")) from e

    samples = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    win = int(SAMPLE_RATE * WINDOW_SECONDS)
    if len(samples) < win:
        return np.zeros(1, dtype=np.float32), WINDOW_SECONDS

    n_windows = len(samples) // win
    trimmed = samples[: n_windows * win].reshape(n_windows, win)
    rms = np.sqrt((trimmed ** 2).mean(axis=1))
    peak = float(rms.max()) or 1.0
    return rms / peak, WINDOW_SECONDS


def energy_boost(energy: np.ndarray, window_seconds: float, start: float, end: float) -> float:
    """0..1 bonus signal for a [start, end] span.

    High when the span contains windows well above the video's median energy
    (laughter, shouting, crowd reaction).
    """
    i0 = int(start / window_seconds)
    i1 = max(i0 + 1, int(end / window_seconds))
    span = energy[i0:i1]
    if span.size == 0:
        return 0.0
    median = float(np.median(energy)) or 1e-6
    spike_ratio = float((span > 1.6 * median).mean())   # fraction of "loud" windows
    peak_rel = float(span.max()) / (float(energy.max()) or 1.0)
    return min(1.0, 0.6 * spike_ratio + 0.4 * peak_rel)
