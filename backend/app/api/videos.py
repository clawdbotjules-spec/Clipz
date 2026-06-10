"""Video ingest endpoints: preview, process (single + batch), listing."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import Video, get_session
from ..errors import ClipForgeError
from ..jobqueue import queue
from ..pipeline.ingest import fetch_metadata, parse_video_id

router = APIRouter(prefix="/api/videos", tags=["videos"])


class PreviewRequest(BaseModel):
    url: str


class ProcessRequest(BaseModel):
    url: str
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


@router.post("/process")
async def process(req: ProcessRequest):
    if not parse_video_id(req.url):
        raise HTTPException(400, "That doesn't look like a valid YouTube URL.")
    time_range = None
    if req.start_minute is not None and req.end_minute is not None:
        if req.end_minute <= req.start_minute:
            raise HTTPException(400, "End minute must be after start minute.")
        time_range = (req.start_minute * 60, req.end_minute * 60)
    job = queue.submit(
        "process_video",
        {
            "url": req.url,
            "time_range": time_range,
            "campaign_id": req.campaign_id,
            "blur_background": req.blur_background,
        },
    )
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
