"""ClipForge FastAPI application."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .jobqueue import Job, JobQueue, queue
from .pipeline.runner import process_local, process_video, rerender_clip
from .api import campaigns, clips, misc, videos


async def _handle_process_video(job: Job, q: JobQueue):
    p = job.params

    def progress(stage: str, frac: float, msg: str) -> None:
        q.update(job, stage=stage, progress=frac, message=msg)

    return await asyncio.to_thread(
        process_video,
        p["url"],
        time_range=tuple(p["time_range"]) if p.get("time_range") else None,
        campaign_id=p.get("campaign_id"),
        blur_background=p.get("blur_background"),
        progress=progress,
    )


async def _handle_process_local(job: Job, q: JobQueue):
    p = job.params

    def progress(stage: str, frac: float, msg: str) -> None:
        q.update(job, stage=stage, progress=frac, message=msg)

    return await asyncio.to_thread(
        process_local,
        p["video_id"],
        time_range=tuple(p["time_range"]) if p.get("time_range") else None,
        campaign_id=p.get("campaign_id"),
        blur_background=p.get("blur_background"),
        progress=progress,
    )


async def _handle_rerender_clip(job: Job, q: JobQueue):
    p = job.params

    def progress(stage: str, frac: float, msg: str) -> None:
        q.update(job, stage=stage, progress=frac, message=msg)

    return await asyncio.to_thread(
        rerender_clip, p["clip_id"], text_only=bool(p.get("text_only")), progress=progress
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    queue.register("process_video", _handle_process_video)
    queue.register("process_local", _handle_process_local)
    queue.register("rerender_clip", _handle_rerender_clip)
    await queue.start()
    yield
    await queue.stop()


app = FastAPI(title="ClipForge", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(videos.router)
app.include_router(clips.router)
app.include_router(campaigns.router)
app.include_router(misc.router)
app.include_router(misc.ws_router)


@app.get("/api/health")
async def health():
    return {"ok": True}


def run():
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=False)


if __name__ == "__main__":
    run()
