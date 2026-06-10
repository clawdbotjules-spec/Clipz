"""Campaign profile CRUD (Whop clipping rule presets)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import Campaign, get_session

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


class CampaignIn(BaseModel):
    name: str
    required_hashtags: list[str] = []
    required_mentions: list[str] = []
    required_text: list[str] = []
    banned_words: list[str] = []
    min_clip_seconds: float = 0.0
    max_clip_seconds: float = 0.0
    watermark_position: str = "bottom-right"
    is_active: bool = False


def _to_dict(c: Campaign) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "required_hashtags": c.required_hashtags,
        "required_mentions": c.required_mentions,
        "required_text": c.required_text,
        "banned_words": c.banned_words,
        "min_clip_seconds": c.min_clip_seconds,
        "max_clip_seconds": c.max_clip_seconds,
        "watermark_path": c.watermark_path,
        "watermark_position": c.watermark_position,
        "is_active": c.is_active,
    }


def _apply(c: Campaign, data: CampaignIn) -> None:
    c.name = data.name
    c.required_hashtags_json = json.dumps(data.required_hashtags)
    c.required_mentions_json = json.dumps(data.required_mentions)
    c.required_text_json = json.dumps(data.required_text)
    c.banned_words_json = json.dumps(data.banned_words)
    c.min_clip_seconds = data.min_clip_seconds
    c.max_clip_seconds = data.max_clip_seconds
    c.watermark_position = data.watermark_position
    c.is_active = data.is_active


@router.get("")
async def list_campaigns(db: Session = Depends(get_session)):
    return [_to_dict(c) for c in db.query(Campaign).order_by(Campaign.created_at.desc()).all()]


@router.post("")
async def create_campaign(data: CampaignIn, db: Session = Depends(get_session)):
    c = Campaign()
    _apply(c, data)
    if data.is_active:
        db.query(Campaign).update({Campaign.is_active: False})
    db.add(c)
    db.commit()
    return _to_dict(c)


@router.put("/{campaign_id}")
async def update_campaign(campaign_id: int, data: CampaignIn, db: Session = Depends(get_session)):
    c = db.get(Campaign, campaign_id)
    if c is None:
        raise HTTPException(404, "Campaign not found")
    if data.is_active:
        db.query(Campaign).filter(Campaign.id != campaign_id).update({Campaign.is_active: False})
    _apply(c, data)
    db.commit()
    return _to_dict(c)


@router.post("/{campaign_id}/watermark")
async def upload_watermark(campaign_id: int, file: UploadFile = File(...),
                           db: Session = Depends(get_session)):
    c = db.get(Campaign, campaign_id)
    if c is None:
        raise HTTPException(404, "Campaign not found")
    suffix = Path(file.filename or "wm.png").suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(400, "Watermark must be a PNG/JPG/WebP image.")
    dest = get_settings().watermarks_dir / f"campaign_{campaign_id}{suffix}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    c.watermark_path = str(dest)
    db.commit()
    return {"watermark_path": c.watermark_path}


@router.delete("/{campaign_id}")
async def delete_campaign(campaign_id: int, db: Session = Depends(get_session)):
    c = db.get(Campaign, campaign_id)
    if c is None:
        raise HTTPException(404, "Campaign not found")
    db.delete(c)
    db.commit()
    return {"ok": True}
