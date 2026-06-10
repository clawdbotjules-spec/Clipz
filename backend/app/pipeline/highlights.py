"""The moneymaker: Claude-powered viral moment detection.

Chunks the transcript, asks Claude to score candidate 20-60s segments on the
signals that make people stop scrolling, snaps boundaries to sentence edges,
blends in an audio-energy bonus, and returns the top clips ranked by score.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

import anthropic

from ..config import get_settings
from ..errors import HighlightError
from .audio_energy import compute_energy_profile, energy_boost

CHUNK_SECONDS = 15 * 60          # transcript chunk sent per request
CHUNK_OVERLAP_SECONDS = 60       # so moments at chunk edges aren't missed
CANDIDATES_PER_CHUNK = 6

SYSTEM_PROMPT = """\
You are an elite short-form video editor who has produced hundreds of TikToks with \
10M+ views for clipping campaigns. You are given a timestamped transcript chunk from \
a long YouTube video. Your job: find the moments a scroller would actually stop for.

Score every candidate moment on these signals (0-10 each):
- hook: would the FIRST 2 SECONDS stop a scroll? (a shocking claim, a question, \
mid-conflict, a number, a "wait, what?")
- emotion: emotional spikes — anger, joy, shock, vulnerability, hype
- controversy: hot takes, contrarian opinions, things people will argue about in comments
- storytelling: a payoff, twist, or satisfying conclusion contained IN the clip
- humor: genuinely funny lines, roasts, absurd moments
- quotable: lines people would caption, screenshot, or repeat

Rules:
- Each candidate must be a self-contained 20-60 second moment. It must make sense \
with ZERO outside context.
- start/end MUST land exactly on sentence boundaries from the transcript — never \
mid-sentence, never mid-word. Prefer starting ON the strongest line, not the setup \
before it (the hook line should be the first thing heard).
- overall_score (0-100) = how likely this clip is to go viral as a standalone TikTok. \
Be harsh: most of a podcast is filler. A 70+ means you would personally post it.
- hook_headline: a short punchy text overlay (max 9 words, no hashtags) that creates \
an information gap or bold claim. Write 3 distinct variants for A/B testing across \
accounts: one curiosity-gap, one bold-claim, one emotional/relatable.
- captions: 3 ready-to-post TikTok captions (with hashtags) in different styles: \
(1) curiosity bait, (2) controversial/engagement bait, (3) value/summary.

Only return candidates scoring 40+. Quality over quantity."""

HIGHLIGHT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number", "description": "clip start in seconds, on a sentence boundary"},
                    "end": {"type": "number", "description": "clip end in seconds, on a sentence boundary"},
                    "reason": {"type": "string", "description": "one line: why this would stop a scroll"},
                    "hook_headline": {"type": "string"},
                    "hook_variants": {
                        "type": "array", "items": {"type": "string"},
                        "description": "exactly 3 hook headline variants for A/B testing",
                    },
                    "captions": {
                        "type": "array", "items": {"type": "string"},
                        "description": "exactly 3 caption+hashtag options",
                    },
                    "scores": {
                        "type": "object",
                        "properties": {
                            "hook": {"type": "number"},
                            "emotion": {"type": "number"},
                            "controversy": {"type": "number"},
                            "storytelling": {"type": "number"},
                            "humor": {"type": "number"},
                            "quotable": {"type": "number"},
                        },
                        "required": ["hook", "emotion", "controversy", "storytelling", "humor", "quotable"],
                        "additionalProperties": False,
                    },
                    "overall_score": {"type": "number"},
                },
                "required": ["start", "end", "reason", "hook_headline", "hook_variants",
                             "captions", "scores", "overall_score"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["candidates"],
    "additionalProperties": False,
}


def _client() -> anthropic.Anthropic:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HighlightError(
            "ANTHROPIC_API_KEY is not set. Add it to your .env file (or the Settings page) "
            "— clip selection needs the Anthropic API."
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _format_chunk(segments: list[dict[str, Any]]) -> str:
    lines = [f"[{s['start']:.1f} -> {s['end']:.1f}] {s['text']}" for s in segments]
    return "\n".join(lines)


def _chunk_segments(segments: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not segments:
        return []
    chunks: list[list[dict[str, Any]]] = []
    chunk_start = segments[0]["start"]
    current: list[dict[str, Any]] = []
    for seg in segments:
        if seg["end"] - chunk_start > CHUNK_SECONDS and current:
            chunks.append(current)
            # back up for overlap so edge moments appear in both chunks
            overlap_from = seg["start"] - CHUNK_OVERLAP_SECONDS
            current = [s for s in current if s["end"] >= overlap_from]
            chunk_start = current[0]["start"] if current else seg["start"]
        current.append(seg)
    if current:
        chunks.append(current)
    return chunks


def _score_chunk(client: anthropic.Anthropic, model: str, segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prompt = (
        f"Here is a transcript chunk ({segments[0]['start']:.0f}s to {segments[-1]['end']:.0f}s). "
        f"Return your top candidates (at most {CANDIDATES_PER_CHUNK}).\n\n"
        + _format_chunk(segments)
    )
    try:
        response = client.messages.create(
            model=model,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": HIGHLIGHT_SCHEMA}},
        )
    except anthropic.AuthenticationError as e:
        raise HighlightError("Anthropic API key is invalid. Check ANTHROPIC_API_KEY.", detail=str(e)) from e
    except anthropic.APIError as e:
        raise HighlightError(f"Anthropic API error during clip scoring: {e.__class__.__name__}",
                             detail=str(e)) from e

    text = next((b.text for b in response.content if b.type == "text"), "{}")
    try:
        return json.loads(text).get("candidates", [])
    except json.JSONDecodeError as e:
        raise HighlightError("Claude returned malformed JSON while scoring clips.", detail=text[:500]) from e


def snap_to_sentences(segments: list[dict[str, Any]], start: float, end: float) -> tuple[float, float]:
    """Snap [start, end] to the nearest sentence (whisper segment) boundaries."""
    starts = [s["start"] for s in segments]
    ends = [s["end"] for s in segments]
    snapped_start = min(starts, key=lambda t: abs(t - start)) if starts else start
    snapped_end = min(ends, key=lambda t: abs(t - end)) if ends else end
    if snapped_end <= snapped_start:
        snapped_end = end
    return snapped_start, snapped_end


def _dedupe(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop overlapping candidates, keeping the higher-scoring one."""
    kept: list[dict[str, Any]] = []
    for cand in sorted(candidates, key=lambda c: c["overall_score"], reverse=True):
        overlaps = False
        for k in kept:
            inter = min(cand["end"], k["end"]) - max(cand["start"], k["start"])
            shorter = min(cand["end"] - cand["start"], k["end"] - k["start"])
            if shorter > 0 and inter / shorter > 0.5:
                overlaps = True
                break
        if not overlaps:
            kept.append(cand)
    return kept


def highlights_cache_path(video_id: str, time_range: tuple[float, float] | None):
    settings = get_settings()
    range_key = f"{time_range[0]:.0f}-{time_range[1]:.0f}" if time_range else "full"
    sig = hashlib.sha1(f"{settings.anthropic_model}|{SYSTEM_PROMPT}".encode()).hexdigest()[:8]
    return settings.highlights_dir / f"{video_id}.{range_key}.{sig}.json"


def find_highlights(
    video_id: str,
    media_path: str,
    transcript: dict[str, Any],
    *,
    time_range: tuple[float, float] | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
) -> list[dict[str, Any]]:
    """Return ranked clip candidates with snapped boundaries and blended scores."""
    settings = get_settings()

    cache = highlights_cache_path(video_id, time_range)
    if cache.exists():
        if progress_cb:
            progress_cb(1.0, "Highlights loaded from cache")
        return json.loads(cache.read_text())

    segments = transcript["segments"]
    if time_range:
        segments = [s for s in segments if s["end"] > time_range[0] and s["start"] < time_range[1]]
    if not segments:
        raise HighlightError("No speech found in the selected range — nothing to clip.")

    client = _client()
    chunks = _chunk_segments(segments)
    all_candidates: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks):
        if progress_cb:
            progress_cb(i / max(len(chunks), 1), f"Scoring transcript chunk {i + 1}/{len(chunks)} with Claude...")
        all_candidates.extend(_score_chunk(client, settings.anthropic_model, chunk))

    if progress_cb:
        progress_cb(0.9, "Blending audio-energy signal and ranking...")

    # Audio energy bonus: boost moments where loudness spikes agree with the transcript score
    try:
        energy, win = compute_energy_profile(media_path)
    except Exception:
        energy, win = None, 0.5  # energy is a bonus signal; never fail the pipeline over it

    results: list[dict[str, Any]] = []
    for cand in all_candidates:
        start, end = snap_to_sentences(segments, float(cand["start"]), float(cand["end"]))
        length = end - start
        if length < settings.min_clip_seconds * 0.7 or length > settings.max_clip_seconds * 1.3:
            continue
        score = float(cand["overall_score"])
        if energy is not None:
            bonus = energy_boost(energy, win, start, end)
            # audio agreement is worth up to +10, weighted by how good the clip already is
            score = min(100.0, score + 10.0 * bonus * (score / 100.0))
            cand["scores"]["audio_energy"] = round(bonus * 10, 1)
        cand.update({"start": start, "end": end, "overall_score": round(score, 1)})
        results.append(cand)

    results = _dedupe(results)
    results.sort(key=lambda c: c["overall_score"], reverse=True)
    top = results[: settings.max_clip_count]
    if not top:
        raise HighlightError(
            "Claude didn't find any clip-worthy moments (score 40+) in this video. "
            "Try a different time range or a more dynamic source video."
        )
    cache.write_text(json.dumps(top))
    if progress_cb:
        progress_cb(1.0, f"Found {len(top)} clip candidates")
    return top
