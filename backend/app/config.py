"""Application configuration loaded from environment / .env file."""
from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Both locations work; backend/.env (listed last) wins on conflicts.
        env_file=(str(PROJECT_ROOT / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Anthropic ---
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"

    # --- TikTok Content Posting API ---
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_redirect_uri: str = "http://localhost:8000/api/tiktok/callback"

    # --- Storage ---
    data_dir: Path = PROJECT_ROOT / "data"

    # --- Transcription ---
    whisper_model: str = "small"          # tiny | base | small | medium | large-v3
    whisper_device: str = "auto"          # auto | cpu | cuda
    whisper_compute_type: str = "auto"    # auto | int8 | float16 | float32

    # --- Pipeline limits ---
    max_video_hours: float = 3.0
    max_clip_count: int = 10
    min_clip_seconds: float = 20.0
    max_clip_seconds: float = 60.0
    max_output_mb: int = 287              # TikTok upload ceiling

    # --- Server ---
    host: str = "127.0.0.1"
    port: int = 8000
    job_workers: int = 1                  # video pipelines are heavy; keep serial by default

    @property
    def videos_dir(self) -> Path:
        return self.data_dir / "videos"

    @property
    def clips_dir(self) -> Path:
        return self.data_dir / "clips"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def transcripts_dir(self) -> Path:
        return self.cache_dir / "transcripts"

    @property
    def highlights_dir(self) -> Path:
        return self.cache_dir / "highlights"

    @property
    def watermarks_dir(self) -> Path:
        return self.data_dir / "watermarks"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "clipforge.db"

    def ensure_dirs(self) -> None:
        for d in (
            self.videos_dir,
            self.clips_dir,
            self.transcripts_dir,
            self.highlights_dir,
            self.watermarks_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
