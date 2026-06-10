"""SQLite persistence layer (SQLAlchemy 2.0)."""
from __future__ import annotations

import json
import datetime as dt
from typing import Any

from sqlalchemy import (
    create_engine,
    String,
    Float,
    Integer,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # YouTube video id
    url: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String, default="")
    channel: Mapped[str] = mapped_column(String, default="")
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    thumbnail: Mapped[str] = mapped_column(String, default="")
    file_path: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="new")  # new|downloading|ready|failed
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    clips: Mapped[list["Clip"]] = relationship(back_populates="video", cascade="all, delete-orphan")


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"))
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)

    start: Mapped[float] = mapped_column(Float)
    end: Mapped[float] = mapped_column(Float)
    virality_score: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    hook: Mapped[str] = mapped_column(Text, default="")
    hook_variants_json: Mapped[str] = mapped_column(Text, default="[]")   # 3 A/B hook options
    captions_json: Mapped[str] = mapped_column(Text, default="[]")        # 3 caption+hashtag options
    scores_json: Mapped[str] = mapped_column(Text, default="{}")          # per-dimension scores

    blur_background: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|rendering|ready|failed|posted
    file_path: Mapped[str] = mapped_column(String, default="")
    base_path: Mapped[str] = mapped_column(String, default="")      # textless intermediate for fast re-render
    error: Mapped[str] = mapped_column(Text, default="")

    posted_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    post_url: Mapped[str] = mapped_column(String, default="")
    post_platform: Mapped[str] = mapped_column(String, default="")
    views: Mapped[int] = mapped_column(Integer, default=0)
    earnings: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    video: Mapped[Video] = relationship(back_populates="clips")

    # -- json helpers -------------------------------------------------
    @property
    def hook_variants(self) -> list[str]:
        return json.loads(self.hook_variants_json or "[]")

    @hook_variants.setter
    def hook_variants(self, v: list[str]) -> None:
        self.hook_variants_json = json.dumps(v)

    @property
    def captions(self) -> list[str]:
        return json.loads(self.captions_json or "[]")

    @captions.setter
    def captions(self, v: list[str]) -> None:
        self.captions_json = json.dumps(v)

    @property
    def scores(self) -> dict[str, Any]:
        return json.loads(self.scores_json or "{}")

    @scores.setter
    def scores(self, v: dict[str, Any]) -> None:
        self.scores_json = json.dumps(v)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String)
    required_hashtags_json: Mapped[str] = mapped_column(Text, default="[]")
    required_mentions_json: Mapped[str] = mapped_column(Text, default="[]")
    required_text_json: Mapped[str] = mapped_column(Text, default="[]")  # phrases the caption must contain
    banned_words_json: Mapped[str] = mapped_column(Text, default="[]")
    min_clip_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    max_clip_seconds: Mapped[float] = mapped_column(Float, default=0.0)  # 0 = no limit
    watermark_path: Mapped[str] = mapped_column(String, default="")
    watermark_position: Mapped[str] = mapped_column(String, default="bottom-right")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    @property
    def required_hashtags(self) -> list[str]:
        return json.loads(self.required_hashtags_json or "[]")

    @property
    def required_mentions(self) -> list[str]:
        return json.loads(self.required_mentions_json or "[]")

    @property
    def required_text(self) -> list[str]:
        return json.loads(self.required_text_json or "[]")

    @property
    def banned_words(self) -> list[str]:
        return json.loads(self.banned_words_json or "[]")


class TikTokAccount(Base):
    __tablename__ = "tiktok_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    open_id: Mapped[str] = mapped_column(String, unique=True)
    display_name: Mapped[str] = mapped_column(String, default="")
    access_token: Mapped[str] = mapped_column(Text, default="")
    refresh_token: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    scope: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class AppSetting(Base):
    """Key/value JSON store for UI-editable settings (caption style, defaults...)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, default="null")


_engine = None
SessionLocal: sessionmaker | None = None


def _migrate(engine) -> None:
    """Additive migrations for databases created by earlier versions."""
    from sqlalchemy import text

    added_columns = {
        "campaigns": [("required_text_json", "TEXT DEFAULT '[]'")],
    }
    with engine.connect() as conn:
        for table, columns in added_columns.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            for name, ddl in columns:
                if existing and name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        conn.commit()


def init_db():
    global _engine, SessionLocal
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            f"sqlite:///{settings.db_path}",
            connect_args={"check_same_thread": False},
        )
        SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
        Base.metadata.create_all(_engine)
        _migrate(_engine)
    return SessionLocal


def get_session():
    factory = init_db()
    db = factory()
    try:
        yield db
    finally:
        db.close()


DEFAULT_UI_SETTINGS: dict[str, Any] = {
    "caption_font": "Arial Black",
    "caption_font_size": 72,
    "caption_color": "#FFFFFF",
    "caption_highlight_color": "#FFE600",
    "caption_outline_color": "#000000",
    "default_hashtags": ["#fyp", "#viral"],
    "watermark_position": "bottom-right",
    "blur_background_default": False,
}


def get_ui_settings(db) -> dict[str, Any]:
    merged = dict(DEFAULT_UI_SETTINGS)
    for row in db.query(AppSetting).all():
        merged[row.key] = json.loads(row.value_json)
    return merged


def set_ui_settings(db, values: dict[str, Any]) -> None:
    for key, value in values.items():
        row = db.get(AppSetting, key)
        if row is None:
            row = AppSetting(key=key)
            db.add(row)
        row.value_json = json.dumps(value)
    db.commit()
