"""Jobs (poll + websocket), settings, and TikTok OAuth endpoints."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import TikTokAccount, get_session, get_ui_settings, set_ui_settings
from ..errors import ClipForgeError
from ..jobqueue import queue
from ..posting.tiktok import build_auth_url, exchange_code, query_creator_info

router = APIRouter(prefix="/api", tags=["misc"])


# --- jobs -------------------------------------------------------------
@router.get("/jobs")
async def list_jobs():
    return [j.to_dict() for j in queue.all()[:50]]


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job.to_dict()


ws_router = APIRouter()


@ws_router.websocket("/ws/jobs")
async def jobs_ws(ws: WebSocket):
    await ws.accept()
    sub = queue.subscribe()
    try:
        while True:
            update = await sub.get()
            await ws.send_json(update)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        queue.unsubscribe(sub)


# --- settings ----------------------------------------------------------
class SettingsPayload(BaseModel):
    values: dict


@router.get("/settings")
async def read_settings(db: Session = Depends(get_session)):
    s = get_settings()
    return {
        "ui": get_ui_settings(db),
        "env": {
            "anthropic_key_set": bool(s.anthropic_api_key),
            "anthropic_model": s.anthropic_model,
            "tiktok_configured": bool(s.tiktok_client_key and s.tiktok_client_secret),
            "whisper_model": s.whisper_model,
            "data_dir": str(s.data_dir),
        },
    }


@router.put("/settings")
async def write_settings(payload: SettingsPayload, db: Session = Depends(get_session)):
    set_ui_settings(db, payload.values)
    return {"ui": get_ui_settings(db)}


# --- TikTok OAuth ------------------------------------------------------
@router.get("/tiktok/auth-url")
async def tiktok_auth_url():
    try:
        return {"url": build_auth_url()}
    except ClipForgeError as e:
        raise HTTPException(400, e.user_message) from e


@router.get("/tiktok/callback")
async def tiktok_callback(code: str = "", state: str = "", error: str = "",
                          db: Session = Depends(get_session)):
    if error or not code:
        return HTMLResponse(
            f"<h2>TikTok login failed</h2><p>{error or 'No code returned.'}</p>", status_code=400
        )
    try:
        account = exchange_code(db, code, state)
    except ClipForgeError as e:
        return HTMLResponse(f"<h2>TikTok login failed</h2><p>{e.user_message}</p>", status_code=400)
    return HTMLResponse(
        f"<h2>Connected as {account.display_name or account.open_id}</h2>"
        "<p>You can close this tab and return to ClipForge.</p>"
    )


@router.get("/tiktok/accounts")
async def tiktok_accounts(db: Session = Depends(get_session)):
    out = []
    for a in db.query(TikTokAccount).all():
        status = "connected"
        privacy_options: list[str] = []
        try:
            info = query_creator_info(a.access_token)
            privacy_options = info.get("privacy_level_options", [])
            if "PUBLIC_TO_EVERYONE" not in privacy_options:
                status = "unaudited"  # app not approved: private/draft posting only
        except ClipForgeError:
            status = "needs_reauth"
        out.append({
            "id": a.id,
            "display_name": a.display_name,
            "open_id": a.open_id,
            "status": status,
            "privacy_options": privacy_options,
        })
    return out


@router.delete("/tiktok/accounts/{account_id}")
async def disconnect_tiktok(account_id: int, db: Session = Depends(get_session)):
    a = db.get(TikTokAccount, account_id)
    if a is None:
        raise HTTPException(404, "Account not found")
    db.delete(a)
    db.commit()
    return {"ok": True}
