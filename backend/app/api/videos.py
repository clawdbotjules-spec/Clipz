"""Video ingest endpoints: preview, upload, process (single + batch), listing."""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import Video, get_session
from ..errors import ClipForgeError
from ..jobqueue import queue
from ..pipeline.ingest import LOCAL_VIDEO_EXTS, fetch_metadata, parse_video_id, probe_duration

router = APIRouter(prefix="/api/videos", tags=["videos"])


class PreviewRequest(BaseModel):
    url: str


class ProcessRequest(BaseModel):
    url: str | None = None                # YouTube mode
    video_id: str | None = None           # uploaded-file mode
    start_minute: float | None = None     # time-range mode
    end_minute: float | None = None
    campaign_id: int | None = None
    blur_background: bool | None = None


class BatchRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=20)
    campaign_id: int | None = None
    blur_background: bool | None = None


@router.post("/preview")
async def preview(req: PreviewRequest):
    if not parse_video_id(req.url):
        raise HTTPException(400, "That doesn't look like a valid YouTube URL.")
    try:
        return await asyncio.to_thread(fetch_metadata, req.url)
    except ClipForgeError as e:
        raise HTTPException(400, e.user_message) from e


@router.post("/upload")
async def upload(file: UploadFile = File(...), db: Session = Depends(get_session)):
    """Ingest a video file from disk. Content-hashed so re-uploads hit all caches."""
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in LOCAL_VIDEO_EXTS:
        raise HTTPException(
            400, f"Unsupported file type '{suffix}' — use one of: {', '.join(LOCAL_VIDEO_EXTS)}"
        )

    settings = get_settings()
    tmp_path = settings.videos_dir / f".upload_{file.filename or 'tmp'}.part"
    sha = hashlib.sha1()
    try:
        with tmp_path.open("wb") as out:
            while chunk := await file.read(8 * 1024 * 1024):
                sha.update(chunk)
                out.write(chunk)
        video_id = f"local-{sha.hexdigest()[:12]}"
        dest = settings.videos_dir / f"{video_id}{suffix}"
        if dest.exists():
            tmp_path.unlink()
        else:
            tmp_path.replace(dest)
    finally:
        tmp_path.unlink(missing_ok=True)

    try:
        duration = await asyncio.to_thread(probe_duration, str(dest))
    except ClipForgeError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, e.user_message) from e

    title = Path(file.filename or video_id).stem
    video = db.get(Video, video_id)
    if video is None:
        video = Video(id=video_id, url="")
        db.add(video)
    video.title = title
    video.duration = duration
    video.file_path = str(dest)
    video.status = "ready"
    db.commit()

    too_long = duration > settings.max_video_hours * 3600
    return {
        "id": video_id,
        "title": title,
        "duration": duration,
        "too_long": too_long,
        "max_hours": settings.max_video_hours,
    }


@router.post("/process")
async def process(req: ProcessRequest):
    if not req.url and not req.video_id:
        raise HTTPException(400, "Provide a YouTube URL or an uploaded video_id.")
    if req.url and not parse_video_id(req.url):
        raise HTTPException(400, "That doesn't look like a valid YouTube URL.")
    time_range = None
    if req.start_minute is not None and req.end_minute is not None:
        if req.end_minute <= req.start_minute:
            raise HTTPException(400, "End minute must be after start minute.")
        time_range = (req.start_minute * 60, req.end_minute * 60)

    common = {
        "time_range": time_range,
        "campaign_id": req.campaign_id,
        "blur_background": req.blur_background,
    }
    if req.video_id:
        job = queue.submit("process_local", {"video_id": req.video_id, **common})
    else:
        job = queue.submit("process_video", {"url": req.url, **common})
    return {"job_id": job.id}


@router.post("/batch")
async def batch(req: BatchRequest):
    job_ids = []
    for url in req.urls:
        url = url.strip()
        if not url:
            continue
        if not parse_video_id(url):
            raise HTTPException(400, f"Not a valid YouTube URL: {url}")
        job = queue.submit(
            "process_video",
            {"url": url, "time_range": None,
             "campaign_id": req.campaign_id, "blur_background": req.blur_background},
        )
        job_ids.append(job.id)
    return {"job_ids": job_ids}


@router.get("")
async def list_videos(db: Session = Depends(get_session)):
    videos = db.query(Video).order_by(Video.created_at.desc()).all()
    return [
        {
            "id": v.id, "url": v.url, "title": v.title, "channel": v.channel,
            "duration": v.duration, "thumbnail": v.thumbnail, "status": v.status,
            "clip_count": len(v.clips),
        }
        for v in videos
    ]
