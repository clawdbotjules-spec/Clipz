"""Common posting interface so YouTube Shorts / Instagram Reels slot in later."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class PostResult:
    platform: str
    status: str               # published | processing | draft | private
    post_url: str = ""
    publish_id: str = ""
    note: str = ""


class Poster(ABC):
    """One implementation per platform."""

    platform: str

    @abstractmethod
    def is_configured(self) -> bool:
        """Credentials present and an account is connected."""

    @abstractmethod
    def post(self, video_path: str, caption: str, **kwargs: Any) -> PostResult:
        """Upload and publish (or draft) the clip."""
