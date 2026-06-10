"""Whop campaign rule validation and duplicate-clip protection."""
from __future__ import annotations

import re
from typing import Any

from .db import Campaign, Clip


def validate_against_campaign(
    campaign: Campaign | None,
    *,
    clip_length: float,
    caption: str,
    transcript_text: str = "",
) -> list[str]:
    """Return human-readable warnings; empty list means the post is compliant."""
    if campaign is None:
        return []
    warnings: list[str] = []
    caption_lower = caption.lower()

    for tag in campaign.required_hashtags:
        tag_norm = tag if tag.startswith("#") else f"#{tag}"
        if tag_norm.lower() not in caption_lower:
            warnings.append(f"Missing required hashtag {tag_norm}")

    for mention in campaign.required_mentions:
        m_norm = mention if mention.startswith("@") else f"@{mention}"
        if m_norm.lower() not in caption_lower:
            warnings.append(f"Missing required mention {m_norm}")

    for phrase in campaign.required_text:
        if phrase.lower() not in caption_lower:
            warnings.append(f"Caption must include the text: \"{phrase}\"")

    haystack = f"{caption_lower} {transcript_text.lower()}"
    for word in campaign.banned_words:
        if re.search(rf"\b{re.escape(word.lower())}\b", haystack):
            warnings.append(f"Contains banned word '{word}'")

    if campaign.min_clip_seconds and clip_length < campaign.min_clip_seconds:
        warnings.append(
            f"Clip is {clip_length:.0f}s — campaign minimum is {campaign.min_clip_seconds:.0f}s"
        )
    if campaign.max_clip_seconds and clip_length > campaign.max_clip_seconds:
        warnings.append(
            f"Clip is {clip_length:.0f}s — campaign maximum is {campaign.max_clip_seconds:.0f}s"
        )
    return warnings


def find_duplicate_posts(db, clip: Clip, overlap_threshold: float = 0.5) -> list[dict[str, Any]]:
    """Posted clips of the same video whose time span overlaps this one."""
    others = (
        db.query(Clip)
        .filter(Clip.video_id == clip.video_id, Clip.id != clip.id, Clip.posted_at.isnot(None))
        .all()
    )
    duplicates = []
    for other in others:
        inter = min(clip.end, other.end) - max(clip.start, other.start)
        shorter = min(clip.end - clip.start, other.end - other.start)
        if shorter > 0 and inter / shorter >= overlap_threshold:
            duplicates.append(
                {
                    "clip_id": other.id,
                    "start": other.start,
                    "end": other.end,
                    "overlap_pct": round(inter / shorter * 100),
                    "post_url": other.post_url,
                    "posted_at": other.posted_at.isoformat() if other.posted_at else None,
                }
            )
    return duplicates
