"""End-to-end pipeline orchestration: URL or local file -> transcribed -> scored -> rendered clips."""
from __future__ import annotations

from typing import Any, Callable

from ..config import get_settings
from ..db import Campaign, Clip, Video, get_ui_settings, init_db
from ..errors import VideoTooLongError
from .highlights import find_highlights
from .ingest import download_video
from .render import render_clip
from .transcribe import transcribe, words_in_range

ProgressCb = Callable[[str, float, str], None]  # (stage, fraction, message)

STAGES = ("download", "transcribe", "analyze", "render")


def _run_pipeline(
    db,
    video: Video,
    *,
    time_range: tuple[float, float] | None,
    campaign_id: int | None,
    blur_background: bool | None,
    report: Callable[[str, float, str], None],
) -> dict[str, Any]:
    """Shared stages 2-4: transcribe -> analyze -> render. Assumes video.file_path exists."""
    ui = get_ui_settings(db)
    if blur_background is None:
        blur_background = bool(ui.get("blur_background_default", False))

    transcript = transcribe(video.id, video.file_path,
                            progress_cb=lambda f, m: report("transcribe", f, m))

    candidates = find_highlights(
        video.id, video.file_path, transcript,
        time_range=time_range,
        progress_cb=lambda f, m: report("analyze", f, m),
    )

    campaign = db.get(Campaign, campaign_id) if campaign_id else None

    clip_ids: list[int] = []
    n = len(candidates)
    for i, cand in enumerate(candidates):
        clip = Clip(
            video_id=video.id,
            campaign_id=campaign.id if campaign else None,
            start=cand["start"],
            end=cand["end"],
            virality_score=cand["overall_score"],
            reason=cand["reason"],
            hook=cand["hook_headline"],
            blur_background=blur_background,
            status="rendering",
        )
        clip.hook_variants = cand.get("hook_variants", [])[:3]
        clip.captions = cand.get("captions", [])[:3]
        clip.scores = cand.get("scores", {})
        db.add(clip)
        db.commit()

        words = words_in_range(transcript, clip.start, clip.end)
        try:
            final_path, base_path = render_clip(
                video.file_path, clip.id, clip.start, clip.end, words, clip.hook, ui,
                blur_background=blur_background,
                watermark_path=campaign.watermark_path if campaign else None,
                watermark_position=campaign.watermark_position if campaign else "bottom-right",
                progress_cb=lambda f, m, _i=i: report("render", (_i + f) / n, f"Clip {_i + 1}/{n}: {m}"),
            )
            clip.file_path = final_path
            clip.base_path = base_path
            clip.status = "ready"
        except Exception as e:
            clip.status = "failed"
            clip.error = getattr(e, "user_message", str(e))
        db.commit()
        clip_ids.append(clip.id)

    report("render", 1.0, f"Done — {len(clip_ids)} clips")
    return {"video_id": video.id, "clip_ids": clip_ids}


def process_video(
    url: str,
    *,
    time_range: tuple[float, float] | None = None,
    campaign_id: int | None = None,
    blur_background: bool | None = None,
    progress: ProgressCb | None = None,
) -> dict[str, Any]:
    """Run the full pipeline for one YouTube URL. Returns {"video_id", "clip_ids"}."""

    def report(stage: str, frac: float, msg: str) -> None:
        if progress:
            progress(stage, frac, msg)

    factory = init_db()
    db = factory()
    try:
        path, meta = download_video(
            url,
            allow_long=time_range is not None,
            progress_cb=lambda f, m: report("download", f, m),
        )
        video = db.get(Video, meta["id"])
        if video is None:
            video = Video(id=meta["id"], url=url)
            db.add(video)
        video.title = meta["title"]
        video.channel = meta["channel"]
        video.duration = meta["duration"]
        video.thumbnail = meta["thumbnail"]
        video.file_path = path
        video.status = "ready"
        db.commit()

        return _run_pipeline(
            db, video,
            time_range=time_range, campaign_id=campaign_id,
            blur_background=blur_background, report=report,
        )
    finally:
        db.close()


def process_local(
    video_id: str,
    *,
    time_range: tuple[float, float] | None = None,
    campaign_id: int | None = None,
    blur_background: bool | None = None,
    progress: ProgressCb | None = None,
) -> dict[str, Any]:
    """Run the pipeline for an already-uploaded local file (no download stage)."""

    def report(stage: str, frac: float, msg: str) -> None:
        if progress:
            progress(stage, frac, msg)

    settings = get_settings()
    factory = init_db()
    db = factory()
    try:
        video = db.get(Video, video_id)
        if video is None or not video.file_path:
            raise ValueError(f"Uploaded video {video_id} not found — upload it again.")
        if video.duration > settings.max_video_hours * 3600 and time_range is None:
            raise VideoTooLongError(
                f"This file is {video.duration / 3600:.1f} hours long "
                f"(limit {settings.max_video_hours:.0f}h). Use time-range mode."
            )
        report("download", 1.0, "Local file — no download needed")
        return _run_pipeline(
            db, video,
            time_range=time_range, campaign_id=campaign_id,
            blur_background=blur_background, report=report,
        )
    finally:
        db.close()


def rerender_clip(clip_id: int, *, text_only: bool = False,
                  progress: ProgressCb | None = None) -> dict[str, Any]:
    """Re-render one clip. text_only reuses the cached base for instant hook edits."""

    def report(stage: str, frac: float, msg: str) -> None:
        if progress:
            progress(stage, frac, msg)

    factory = init_db()
    db = factory()
    try:
        clip = db.get(Clip, clip_id)
        if clip is None:
            raise ValueError(f"Clip {clip_id} not found")
        video = db.get(Video, clip.video_id)
        ui = get_ui_settings(db)
        campaign = db.get(Campaign, clip.campaign_id) if clip.campaign_id else None

        transcript = transcribe(video.id, video.file_path,
                                progress_cb=lambda f, m: report("transcribe", f, m))
        words = words_in_range(transcript, clip.start, clip.end)

        clip.status = "rendering"
        db.commit()
        try:
            final_path, base_path = render_clip(
                video.file_path, clip.id, clip.start, clip.end, words, clip.hook, ui,
                blur_background=clip.blur_background,
                watermark_path=campaign.watermark_path if campaign else None,
                watermark_position=campaign.watermark_position if campaign else "bottom-right",
                reuse_base=clip.base_path if text_only else None,
                progress_cb=lambda f, m: report("render", f, m),
            )
            clip.file_path = final_path
            clip.base_path = base_path
            clip.status = "ready"
            clip.error = ""
        except Exception as e:
            clip.status = "failed"
            clip.error = getattr(e, "user_message", str(e))
            db.commit()
            raise
        db.commit()
        return {"clip_id": clip.id, "file_path": clip.file_path}
    finally:
        db.close()
