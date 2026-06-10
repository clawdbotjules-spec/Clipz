"""Transcription with faster-whisper, word-level timestamps, disk-cached by video id."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ..config import get_settings
from ..errors import TranscriptionError

_model = None
_model_key: tuple[str, str, str] | None = None


def _load_model():
    global _model, _model_key
    settings = get_settings()
    key = (settings.whisper_model, settings.whisper_device, settings.whisper_compute_type)
    if _model is None or _model_key != key:
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise TranscriptionError(
                "faster-whisper is not installed. Run: pip install faster-whisper",
                detail=str(e),
            ) from e
        _model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        _model_key = key
    return _model


def transcript_cache_path(video_id: str) -> Path:
    settings = get_settings()
    return settings.transcripts_dir / f"{video_id}.{settings.whisper_model}.json"


def transcribe(
    video_id: str,
    media_path: str,
    *,
    progress_cb: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """Return {"segments": [{start, end, text, words: [{start, end, word}]}], "duration": float}.

    Cached to disk so re-processing the same video is instant.
    """
    cache = transcript_cache_path(video_id)
    if cache.exists():
        if progress_cb:
            progress_cb(1.0, "Transcript loaded from cache")
        return json.loads(cache.read_text())

    model = _load_model()
    if progress_cb:
        progress_cb(0.0, "Transcribing (this can take a while on CPU)...")

    try:
        segments_iter, info = model.transcribe(
            media_path,
            word_timestamps=True,
            vad_filter=True,
        )
        duration = float(info.duration or 0)
        segments: list[dict[str, Any]] = []
        for seg in segments_iter:
            words = [
                {"start": float(w.start), "end": float(w.end), "word": w.word}
                for w in (seg.words or [])
            ]
            segments.append(
                {
                    "start": float(seg.start),
                    "end": float(seg.end),
                    "text": seg.text.strip(),
                    "words": words,
                }
            )
            if progress_cb and duration:
                progress_cb(
                    min(float(seg.end) / duration, 0.99),
                    f"Transcribing... {seg.end / duration * 100:.0f}%",
                )
    except TranscriptionError:
        raise
    except Exception as e:  # model load / decode failures
        raise TranscriptionError(
            "Transcription failed. If this is the first run, the Whisper model may still "
            "be downloading — check your connection and retry.",
            detail=str(e),
        ) from e

    result = {"segments": segments, "duration": duration, "language": info.language}
    cache.write_text(json.dumps(result))
    if progress_cb:
        progress_cb(1.0, "Transcription complete")
    return result


def words_in_range(transcript: dict[str, Any], start: float, end: float) -> list[dict[str, Any]]:
    """All whisper words whose midpoint falls inside [start, end]."""
    out = []
    for seg in transcript["segments"]:
        if seg["end"] < start or seg["start"] > end:
            continue
        for w in seg["words"]:
            mid = (w["start"] + w["end"]) / 2
            if start <= mid <= end:
                out.append(w)
    return out
