"""Human-readable error types surfaced to the UI."""
from __future__ import annotations


class ClipForgeError(Exception):
    """Base error carrying a message safe to show to the user."""

    def __init__(self, user_message: str, *, detail: str | None = None):
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail


class DownloadError(ClipForgeError):
    pass


class VideoUnavailableError(DownloadError):
    """Age-restricted, region-locked, private or removed videos."""


class VideoTooLongError(ClipForgeError):
    pass


class TranscriptionError(ClipForgeError):
    pass


class HighlightError(ClipForgeError):
    pass


class RenderError(ClipForgeError):
    pass


class PostingError(ClipForgeError):
    pass


def classify_ytdlp_error(msg: str) -> DownloadError:
    """Translate raw yt-dlp output into something a human can act on."""
    lowered = msg.lower()
    if "sign in to confirm your age" in lowered or "age-restricted" in lowered or "age restricted" in lowered:
        return VideoUnavailableError(
            "This video is age-restricted and can't be downloaded without authentication. "
            "Try exporting browser cookies for yt-dlp, or pick another video.",
            detail=msg,
        )
    if "not available in your country" in lowered or "geo restricted" in lowered or "georestricted" in lowered:
        return VideoUnavailableError(
            "This video is region-locked and not available from your location.", detail=msg
        )
    if "private video" in lowered:
        return VideoUnavailableError("This video is private.", detail=msg)
    if "video unavailable" in lowered or "removed" in lowered:
        return VideoUnavailableError("This video is unavailable (deleted or removed).", detail=msg)
    if "is not a valid url" in lowered or "unsupported url" in lowered:
        return DownloadError("That doesn't look like a valid YouTube URL.", detail=msg)
    return DownloadError(
        "Download failed. YouTube may be throttling or the URL may be wrong — try again in a minute.",
        detail=msg,
    )
