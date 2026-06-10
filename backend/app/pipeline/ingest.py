"""YouTube ingest: validation, metadata preview, and cached downloads via yt-dlp."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import yt_dlp

from ..config import get_settings
from ..errors import VideoTooLongError, classify_ytdlp_error

YOUTUBE_URL_RE = re.compile(
    r"""^https?://
        (?:www\.|m\.|music\.)?
        (?:youtube\.com/(?:watch\?.*v=|shorts/|live/|embed/)|youtu\.be/)
        (?P<id>[A-Za-z0-9_-]{11})""",
    re.VERBOSE,
)


def parse_video_id(url: str) -> str | None:
    m = YOUTUBE_URL_RE.match(url.strip())
    return m.group("id") if m else None


def fetch_metadata(url: str) -> dict[str, Any]:
    """Fetch title/duration/thumbnail without downloading. Raises ClipForgeError."""
    video_id = parse_video_id(url)
    if not video_id:
        raise classify_ytdlp_error(f"{url} is not a valid URL")
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise classify_ytdlp_error(str(e)) from e

    duration = float(info.get("duration") or 0)
    settings = get_settings()
    return {
        "id": info.get("id", video_id),
        "url": url,
        "title": info.get("title", ""),
        "channel": info.get("channel") or info.get("uploader", ""),
        "duration": duration,
        "thumbnail": info.get("thumbnail", ""),
        "too_long": duration > settings.max_video_hours * 3600,
        "max_hours": settings.max_video_hours,
    }


def download_video(
    url: str,
    *,
    allow_long: bool = False,
    progress_cb: Callable[[float, str], None] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Download best-quality video, cached by video id.

    Returns (file_path, metadata). Never re-downloads an existing file.
    """
    settings = get_settings()
    meta = fetch_metadata(url)
    video_id = meta["id"]

    if meta["too_long"] and not allow_long:
        raise VideoTooLongError(
            f"This video is {meta['duration'] / 3600:.1f} hours long "
            f"(limit {settings.max_video_hours:.0f}h). Use time-range mode to process "
            "just the minutes you care about."
        )

    existing = sorted(settings.videos_dir.glob(f"{video_id}.*"))
    for p in existing:
        if p.suffix in (".mp4", ".mkv", ".webm") and p.stat().st_size > 0:
            if progress_cb:
                progress_cb(1.0, "Already downloaded (cache hit)")
            return str(p), meta

    def hook(d: dict[str, Any]) -> None:
        if progress_cb is None:
            return
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            frac = done / total if total else 0.0
            speed = d.get("_speed_str", "").strip()
            progress_cb(frac, f"Downloading {frac * 100:.0f}% ({speed})")
        elif d.get("status") == "finished":
            progress_cb(1.0, "Download finished, merging streams...")

    out_tmpl = str(settings.videos_dir / f"{video_id}.%(ext)s")
    opts = {
        "outtmpl": out_tmpl,
        # best video+audio, prefer mp4/h264 so ffmpeg cuts are fast and compatible
        "format": "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as e:
        raise classify_ytdlp_error(str(e)) from e

    candidates = sorted(settings.videos_dir.glob(f"{video_id}.*"))
    files = [p for p in candidates if p.suffix in (".mp4", ".mkv", ".webm")]
    if not files:
        raise classify_ytdlp_error("Download finished but no output file was produced.")
    return str(files[0]), meta
