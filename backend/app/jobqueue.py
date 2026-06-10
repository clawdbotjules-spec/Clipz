"""In-process asyncio job queue with progress reporting.

Zero extra services: jobs are tracked in memory, executed by asyncio workers,
and heavy/blocking pipeline work runs in a thread via asyncio.to_thread.
Progress is exposed both through polling (GET /api/jobs/{id}) and a
websocket broadcast (/ws/jobs).
"""
from __future__ import annotations

import asyncio
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .errors import ClipForgeError


@dataclass
class Job:
    id: str
    kind: str
    params: dict[str, Any] = field(default_factory=dict)
    status: str = "queued"  # queued | running | done | failed
    stage: str = ""
    progress: float = 0.0   # 0..1 within the current stage
    message: str = ""
    error: str = ""
    result: Any = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "params": self.params,
            "status": self.status,
            "stage": self.stage,
            "progress": round(self.progress, 4),
            "message": self.message,
            "error": self.error,
            "result": self.result,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


JobHandler = Callable[[Job, "JobQueue"], Awaitable[Any]]


class JobQueue:
    def __init__(self, workers: int = 1):
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._jobs: dict[str, Job] = {}
        self._handlers: dict[str, JobHandler] = {}
        self._workers = workers
        self._tasks: list[asyncio.Task] = []
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    # -- registration / lifecycle ------------------------------------
    def register(self, kind: str, handler: JobHandler) -> None:
        self._handlers[kind] = handler

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        for _ in range(self._workers):
            self._tasks.append(asyncio.create_task(self._worker()))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()

    # -- submission / inspection -------------------------------------
    def submit(self, kind: str, params: dict[str, Any] | None = None) -> Job:
        if kind not in self._handlers:
            raise ValueError(f"No handler registered for job kind '{kind}'")
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, params=params or {})
        self._jobs[job.id] = job
        self._queue.put_nowait(job)
        self._broadcast(job)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def all(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    # -- progress reporting (thread-safe) -----------------------------
    def update(self, job: Job, *, stage: str | None = None, progress: float | None = None,
               message: str | None = None) -> None:
        if stage is not None:
            job.stage = stage
        if progress is not None:
            job.progress = max(0.0, min(1.0, progress))
        if message is not None:
            job.message = message
        self._broadcast_threadsafe(job)

    # -- websocket fanout ---------------------------------------------
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def _broadcast(self, job: Job) -> None:
        payload = job.to_dict()
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def _broadcast_threadsafe(self, job: Job) -> None:
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._broadcast, job)
        else:
            self._broadcast(job)

    # -- worker loop ----------------------------------------------------
    async def _worker(self) -> None:
        while True:
            job = await self._queue.get()
            handler = self._handlers[job.kind]
            job.status = "running"
            self._broadcast(job)
            try:
                job.result = await handler(job, self)
                job.status = "done"
                job.progress = 1.0
            except ClipForgeError as e:
                job.status = "failed"
                job.error = e.user_message
            except Exception as e:  # noqa: BLE001 - surface anything to the UI
                job.status = "failed"
                job.error = f"Unexpected error: {e}"
                traceback.print_exc()
            finally:
                job.finished_at = time.time()
                self._broadcast(job)
                self._queue.task_done()


queue = JobQueue()
