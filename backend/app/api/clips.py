"""Clip review endpoints: list, edit hook/trim, re-render, download, export, post."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..campaigns import find_duplicate_posts, validate_against_campaign
from ..db import Campaign, Clip, TikTokAccount, Video, get_session
from ..errors import ClipForgeError
from ..jobqueue import queue
from ..posting.stubs import InstagramReelsPoster, YouTubeShortsPoster
from ..posting.tiktok import TikTokPoster

router = APIRouter(prefix="/api/clips", tags=["clips"])


def _clip_dict(c: Clip, db: Session) -> dict:
    return {
        "id": c.id,
        "video_id": c.video_id,
        "campaign_id": c.campaign_id,
        "start": c.start,
        "end": c.end,
        "duration": round(c.end - c.start, 1),
        "virality_score": c.virality_score,
        "reason": c.reason,
        "hook": c.hook,
        "hook_variants": c.hook_variants,
        "captions": c.captions,
        "scores": c.scores,
        "blur_background": c.blur_background,
        "status": c.status,
        "error": c.error,
        "has_file": bool(c.file_path),
        "posted_at": c.posted_at.isoformat() if c.posted_at else None,
        "post_url": c.post_url,
        "post_platform": c.post_platform,
        "views": c.views,
        "earnings": c.earnings,
        "duplicates": find_duplicate_posts(db, c),
    }


@router.get("")
async def list_clips(video_id: str | None = None, db: Session = Depends(get_session)):
    q = db.query(Clip).order_by(Clip.virality_score.desc())
    if video_id:
        q = q.filter(Clip.video_id == video_id)
    return [_clip_dict(c, db) for c in q.all()]


@router.get("/{clip_id}")
async def get_clip(clip_id: int, db: Session = Depends(get_session)):
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(404, "Clip not found")
    return _clip_dict(clip, db)


class ClipPatch(BaseModel):
    hook: str | None = None
    campaign_id: int | None = None
    blur_background: bool | None = None
    views: int | None = None
    earnings: float | None = None
    post_url: str | None = None


@router.patch("/{clip_id}")
async def patch_clip(clip_id: int, patch: ClipPatch, db: Session = Depends(get_session)):
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(404, "Clip not found")
    for field in ("hook", "campaign_id", "blur_background", "views", "earnings", "post_url"):
        value = getattr(patch, field)
        if value is not None:
            setattr(clip, field, value)
    db.commit()
    return _clip_dict(clip, db)


class TrimRequest(BaseModel):
    delta_start: float = 0.0  # ±1s nudges from the UI
    delta_end: float = 0.0


@router.post("/{clip_id}/trim")
async def trim_clip(clip_id: int, req: TrimRequest, db: Session = Depends(get_session)):
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(404, "Clip not found")
    video = db.get(Video, clip.video_id)
    new_start = max(0.0, clip.start + req.delta_start)
    new_end = min(video.duration or clip.end + req.delta_end, clip.end + req.delta_end)
    if new_end - new_start < 3:
        raise HTTPException(400, "Clip would be shorter than 3 seconds.")
    clip.start, clip.end = new_start, new_end
    clip.status = "pending"  # boundaries changed: base render is stale
    db.commit()
    job = queue.submit("rerender_clip", {"clip_id": clip.id, "text_only": False})
    return {"job_id": job.id, "start": clip.start, "end": clip.end}


@router.post("/{clip_id}/rerender")
async def rerender(clip_id: int, text_only: bool = False, db: Session = Depends(get_session)):
    if db.get(Clip, clip_id) is None:
        raise HTTPException(404, "Clip not found")
    job = queue.submit("rerender_clip", {"clip_id": clip_id, "text_only": text_only})
    return {"job_id": job.id}


@router.post("/{clip_id}/regenerate-captions")
async def regenerate_captions(clip_id: int, db: Session = Depends(get_session)):
    """Re-burn captions from the cached base (fast path, same as text-only rerender)."""
    if db.get(Clip, clip_id) is None:
        raise HTTPException(404, "Clip not found")
    job = queue.submit("rerender_clip", {"clip_id": clip_id, "text_only": True})
    return {"job_id": job.id}


@router.get("/{clip_id}/file")
async def clip_file(clip_id: int, db: Session = Depends(get_session)):
    clip = db.get(Clip, clip_id)
    if clip is None or not clip.file_path:
        raise HTTPException(404, "Clip file not found — render it first.")
    return FileResponse(clip.file_path, media_type="video/mp4",
                        filename=f"clipforge_{clip.video_id}_{clip.id}.mp4")


@router.get("/{clip_id}/export")
async def export_clip(clip_id: int, caption_index: int = 0, db: Session = Depends(get_session)):
    """Export flow: returns caption text; the UI copies it and triggers the file download."""
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(404, "Clip not found")
    captions = clip.captions
    caption = captions[caption_index] if captions and caption_index < len(captions) else ""
    campaign = db.get(Campaign, clip.campaign_id) if clip.campaign_id else None
    warnings = validate_against_campaign(
        campaign, clip_length=clip.end - clip.start, caption=caption
    )
    return {
        "caption": caption,
        "download_url": f"/api/clips/{clip.id}/file",
        "warnings": warnings,
        "duplicates": find_duplicate_posts(db, clip),
    }


class PostRequest(BaseModel):
    platform: str = "tiktok"
    caption: str
    account_id: int | None = None
    ignore_warnings: bool = False


@router.post("/{clip_id}/post")
async def post_clip(clip_id: int, req: PostRequest, db: Session = Depends(get_session)):
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(404, "Clip not found")
    if clip.status != "ready" or not clip.file_path:
        raise HTTPException(400, "Clip isn't rendered yet.")

    campaign = db.get(Campaign, clip.campaign_id) if clip.campaign_id else None
    warnings = validate_against_campaign(
        campaign, clip_length=clip.end - clip.start, caption=req.caption
    )
    duplicates = find_duplicate_posts(db, clip)
    if (warnings or duplicates) and not req.ignore_warnings:
        return {"blocked": True, "warnings": warnings, "duplicates": duplicates}

    if req.platform == "tiktok":
        account = (
            db.get(TikTokAccount, req.account_id)
            if req.account_id
            else db.query(TikTokAccount).first()
        )
        if account is None:
            raise HTTPException(400, "No TikTok account connected — connect one in Settings.")
        poster = TikTokPoster(db, account)
    elif req.platform == "youtube_shorts":
        poster = YouTubeShortsPoster()
    elif req.platform == "instagram_reels":
        poster = InstagramReelsPoster()
    else:
        raise HTTPException(400, f"Unknown platform '{req.platform}'")

    try:
        result = poster.post(clip.file_path, req.caption)
    except ClipForgeError as e:
        raise HTTPException(400, e.user_message) from e

    clip.posted_at = dt.datetime.now(dt.timezone.utc)
    clip.post_platform = req.platform
    if result.post_url:
        clip.post_url = result.post_url
    clip.status = "posted"
    db.commit()
    return {"blocked": False, "status": result.status, "note": result.note,
            "publish_id": result.publish_id}


@router.delete("/{clip_id}")
async def delete_clip(clip_id: int, db: Session = Depends(get_session)):
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(404, "Clip not found")
    db.delete(clip)
    db.commit()
    return {"ok": True}
