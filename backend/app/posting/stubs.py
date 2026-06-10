"""YouTube Shorts / Instagram Reels posting stubs behind the same Poster interface.

Wire in real implementations later without touching the API layer:
  - YouTube: Data API v3 videos.insert with the #Shorts tag
  - Instagram: Graph API /me/media with media_type=REELS
"""
from __future__ import annotations

from typing import Any

from ..errors import PostingError
from .base import Poster, PostResult


class YouTubeShortsPoster(Poster):
    platform = "youtube_shorts"

    def is_configured(self) -> bool:
        return False

    def post(self, video_path: str, caption: str, **kwargs: Any) -> PostResult:
        raise PostingError(
            "YouTube Shorts posting isn't wired up yet — use 'Export for posting' "
            "and upload manually for now."
        )


class InstagramReelsPoster(Poster):
    platform = "instagram_reels"

    def is_configured(self) -> bool:
        return False

    def post(self, video_path: str, caption: str, **kwargs: Any) -> PostResult:
        raise PostingError(
            "Instagram Reels posting isn't wired up yet — use 'Export for posting' "
            "and upload manually for now."
        )
