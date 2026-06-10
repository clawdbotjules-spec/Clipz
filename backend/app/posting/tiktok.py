"""TikTok Content Posting API (Direct Post) + OAuth 2 with PKCE.

Docs: https://developers.tiktok.com/doc/content-posting-api-get-started
Requires an app registered at developers.tiktok.com with the video.publish scope.

IMPORTANT: until your app passes TikTok's audit, Direct Post is restricted —
posts from unaudited apps can only be visible to the creator (SELF_ONLY) or land
as drafts. We detect this from creator_info and surface it in the UI rather than
failing.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from ..config import get_settings
from ..db import TikTokAccount
from ..errors import PostingError
from .base import Poster, PostResult

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
VIDEO_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
USERINFO_URL = "https://open.tiktokapis.com/v2/user/info/"

SCOPES = "user.info.basic,video.publish"

# in-memory PKCE verifiers keyed by state (single-user local app)
_pending_oauth: dict[str, str] = {}


def build_auth_url() -> str:
    settings = get_settings()
    if not settings.tiktok_client_key:
        raise PostingError(
            "TikTok app credentials are not configured. Register an app at "
            "developers.tiktok.com and set TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET in .env."
        )
    state = secrets.token_urlsafe(16)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    _pending_oauth[state] = verifier
    params = {
        "client_key": settings.tiktok_client_key,
        "response_type": "code",
        "scope": SCOPES,
        "redirect_uri": settings.tiktok_redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(db, code: str, state: str) -> TikTokAccount:
    settings = get_settings()
    verifier = _pending_oauth.pop(state, None)
    if verifier is None:
        raise PostingError("OAuth state mismatch — restart the TikTok login flow.")

    resp = httpx.post(
        TOKEN_URL,
        data={
            "client_key": settings.tiktok_client_key,
            "client_secret": settings.tiktok_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.tiktok_redirect_uri,
            "code_verifier": verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    data = resp.json()
    if "access_token" not in data:
        raise PostingError(
            "TikTok rejected the OAuth code exchange. Check your client key/secret "
            "and that the redirect URI matches your app settings exactly.",
            detail=str(data),
        )

    account = (
        db.query(TikTokAccount).filter(TikTokAccount.open_id == data["open_id"]).one_or_none()
    )
    if account is None:
        account = TikTokAccount(open_id=data["open_id"])
        db.add(account)
    account.access_token = data["access_token"]
    account.refresh_token = data.get("refresh_token", "")
    account.scope = data.get("scope", "")
    account.expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        seconds=int(data.get("expires_in", 86400))
    )

    # best-effort display name
    try:
        ui = httpx.get(
            USERINFO_URL,
            params={"fields": "display_name"},
            headers={"Authorization": f"Bearer {account.access_token}"},
            timeout=15,
        ).json()
        account.display_name = ui.get("data", {}).get("user", {}).get("display_name", "")
    except Exception:
        pass

    db.commit()
    return account


def _refresh_if_needed(db, account: TikTokAccount) -> TikTokAccount:
    settings = get_settings()
    expires = account.expires_at
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=dt.timezone.utc)
    if expires and expires > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5):
        return account
    if not account.refresh_token:
        raise PostingError("TikTok session expired — reconnect the account from Settings.")
    resp = httpx.post(
        TOKEN_URL,
        data={
            "client_key": settings.tiktok_client_key,
            "client_secret": settings.tiktok_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": account.refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    data = resp.json()
    if "access_token" not in data:
        raise PostingError("Failed to refresh the TikTok token — reconnect the account.",
                           detail=str(data))
    account.access_token = data["access_token"]
    account.refresh_token = data.get("refresh_token", account.refresh_token)
    account.expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        seconds=int(data.get("expires_in", 86400))
    )
    db.commit()
    return account


def query_creator_info(access_token: str) -> dict[str, Any]:
    resp = httpx.post(
        CREATOR_INFO_URL,
        headers={"Authorization": f"Bearer {access_token}",
                 "Content-Type": "application/json; charset=UTF-8"},
        timeout=30,
    )
    body = resp.json()
    err = body.get("error", {})
    if err.get("code") not in (None, "ok"):
        raise PostingError(
            "TikTok creator_info query failed — the account may lack video.publish "
            "permission or the app isn't approved for Direct Post.",
            detail=str(body),
        )
    return body.get("data", {})


class TikTokPoster(Poster):
    platform = "tiktok"

    def __init__(self, db, account: TikTokAccount):
        self.db = db
        self.account = account

    def is_configured(self) -> bool:
        return bool(get_settings().tiktok_client_key and self.account.access_token)

    def post(self, video_path: str, caption: str, **kwargs: Any) -> PostResult:
        account = _refresh_if_needed(self.db, self.account)
        token = account.access_token

        info = query_creator_info(token)
        allowed_privacy = info.get("privacy_level_options", [])
        wanted = kwargs.get("privacy_level", "PUBLIC_TO_EVERYONE")
        note = ""
        if wanted not in allowed_privacy:
            # Unaudited apps can only post privately/draft — degrade gracefully.
            fallback = "SELF_ONLY" if "SELF_ONLY" in allowed_privacy else (
                allowed_privacy[0] if allowed_privacy else "SELF_ONLY"
            )
            note = (
                f"App not approved for '{wanted}' yet — posted as {fallback}. "
                "Until your TikTok app passes audit, posts are private/draft only."
            )
            wanted = fallback

        size = Path(video_path).stat().st_size
        chunk_size = min(size, 64 * 1024 * 1024)
        total_chunks = -(-size // chunk_size)

        init_resp = httpx.post(
            VIDEO_INIT_URL,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json; charset=UTF-8"},
            json={
                "post_info": {
                    "title": caption[:2200],
                    "privacy_level": wanted,
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": size,
                    "chunk_size": chunk_size,
                    "total_chunk_count": total_chunks,
                },
            },
            timeout=30,
        )
        body = init_resp.json()
        if body.get("error", {}).get("code") not in (None, "ok"):
            raise PostingError("TikTok rejected the upload init request.", detail=str(body))
        data = body["data"]
        publish_id = data["publish_id"]
        upload_url = data["upload_url"]

        with open(video_path, "rb") as f:
            offset = 0
            while offset < size:
                chunk = f.read(chunk_size)
                end = offset + len(chunk) - 1
                up = httpx.put(
                    upload_url,
                    content=chunk,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Range": f"bytes {offset}-{end}/{size}",
                        "Content-Length": str(len(chunk)),
                    },
                    timeout=300,
                )
                if up.status_code not in (200, 201, 206):
                    raise PostingError("TikTok chunk upload failed.", detail=up.text[:500])
                offset += len(chunk)

        status_resp = httpx.post(
            STATUS_URL,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json; charset=UTF-8"},
            json={"publish_id": publish_id},
            timeout=30,
        )
        status = status_resp.json().get("data", {}).get("status", "PROCESSING")

        return PostResult(
            platform="tiktok",
            status="private" if wanted == "SELF_ONLY" else "processing",
            publish_id=publish_id,
            note=note or f"TikTok status: {status}. Processing can take a few minutes.",
        )
