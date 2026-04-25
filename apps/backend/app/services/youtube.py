from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.exceptions import ExternalServiceError, NotFoundError, UnauthorizedError
from app.db.models.channel import Channel, ChannelStatus
from app.integrations.youtube import (
    YOUTUBE_API_BASE,
    YOUTUBE_TOKEN_URL,
    decrypt_token,
    encrypt_token,
)

logger = structlog.get_logger(__name__)

YOUTUBE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


class YouTubeService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def build_state_token(self, *, channel_id: str, user_id: str, org_id: str) -> str:
        payload = {
            "type": "youtube_oauth_state",
            "channel_id": channel_id,
            "sub": user_id,
            "org": org_id,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        }
        return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

    def build_connect_url(self, *, state: str, redirect_uri: str) -> str:
        query = urlencode(
            {
                "client_id": settings.youtube_client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "access_type": "offline",
                "prompt": "consent",
                "scope": " ".join(YOUTUBE_SCOPES),
                "state": state,
                "include_granted_scopes": "true",
            }
        )
        return f"{YOUTUBE_AUTH_URL}?{query}"

    async def get_owned_channel(self, *, channel_id: str, owner_id: str, org_id: str) -> Channel:
        result = await self.db.execute(
            select(Channel).where(
                Channel.id == channel_id,
                Channel.owner_id == owner_id,
                Channel.organization_id == org_id,
            )
        )
        channel = result.scalar_one_or_none()
        if not channel:
            raise NotFoundError("Channel not found")
        return channel

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, ExternalServiceError)),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.request(method, url, **kwargs)

        if response.status_code == 401:
            raise UnauthorizedError("YouTube token expired or unauthorized")
        if response.status_code >= 500:
            raise ExternalServiceError(f"YouTube temporary error {response.status_code}")
        if response.status_code >= 400:
            raise ExternalServiceError(f"YouTube API error {response.status_code}: {response.text[:200]}")
        return response

    async def connect_channel_with_code(
        self,
        *,
        channel: Channel,
        code: str,
        redirect_uri: str,
    ) -> Channel:
        token_resp = await self._request(
            "POST",
            YOUTUBE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.youtube_client_id,
                "client_secret": settings.youtube_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_data = token_resp.json()

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = int(token_data.get("expires_in", 3600))
        if not access_token or not refresh_token:
            raise ExternalServiceError("YouTube OAuth token payload missing access/refresh token")

        channel_info = await self._request(
            "GET",
            f"{YOUTUBE_API_BASE}/channels",
            params={"part": "id,snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        items = channel_info.json().get("items", [])
        if not items:
            raise ExternalServiceError("No YouTube channel returned for OAuth account")

        channel.youtube_channel_id = items[0]["id"]
        channel.access_token_enc = encrypt_token(access_token)
        channel.refresh_token_enc = encrypt_token(refresh_token)
        channel.token_expiry = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
        channel.status = ChannelStatus.active

        await self.db.flush()
        await self.db.refresh(channel)
        logger.info("youtube.connect.success", channel_id=str(channel.id), youtube_channel_id=channel.youtube_channel_id)
        return channel

    async def _ensure_access_token(self, channel: Channel) -> str:
        if not channel.access_token_enc:
            raise UnauthorizedError("YouTube channel not connected")

        expiry = None
        if channel.token_expiry:
            try:
                expiry = datetime.fromisoformat(channel.token_expiry)
            except ValueError:
                expiry = None

        if expiry and expiry > datetime.now(timezone.utc) + timedelta(seconds=60):
            return decrypt_token(channel.access_token_enc)

        if not channel.refresh_token_enc:
            raise UnauthorizedError("Missing refresh token for YouTube channel")

        refresh_token = decrypt_token(channel.refresh_token_enc)
        refresh_resp = await self._request(
            "POST",
            YOUTUBE_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.youtube_client_id,
                "client_secret": settings.youtube_client_secret,
                "grant_type": "refresh_token",
            },
        )
        refresh_data = refresh_resp.json()
        new_access = refresh_data.get("access_token")
        if not new_access:
            raise ExternalServiceError("Missing access_token in refresh response")

        expires_in = int(refresh_data.get("expires_in", 3600))
        channel.access_token_enc = encrypt_token(new_access)
        channel.token_expiry = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
        await self.db.flush()
        return new_access

    async def upload_video(self, *, channel: Channel, payload: dict[str, Any]) -> dict[str, Any]:
        access_token = await self._ensure_access_token(channel)

        media_resp = await self._request("GET", str(payload["media_url"]))
        media_bytes = media_resp.content
        media_type = media_resp.headers.get("content-type", "video/mp4")

        metadata = {
            "snippet": {
                "title": payload["title"],
                "description": payload.get("description") or "",
                "tags": payload.get("tags") or [],
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": payload.get("visibility", "private"),
                "selfDeclaredMadeForKids": False,
            },
        }

        init_resp = await self._request(
            "POST",
            YOUTUBE_UPLOAD_URL,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Length": str(len(media_bytes)),
                "X-Upload-Content-Type": media_type,
            },
            content=json.dumps(metadata),
        )

        upload_url = init_resp.headers.get("Location")
        if not upload_url:
            raise ExternalServiceError("YouTube upload URL missing in resumable init response")

        final_resp = await self._request(
            "PUT",
            upload_url,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": media_type},
            content=media_bytes,
        )
        data = final_resp.json()

        video_id = data.get("id")
        if not video_id:
            raise ExternalServiceError("YouTube upload succeeded but no video id was returned")

        return {
            "youtube_video_id": video_id,
            "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
        }

    async def update_metadata(
        self,
        *,
        channel: Channel,
        youtube_video_id: str,
        title: str | None,
        description: str | None,
        tags: list[str] | None,
        visibility: str | None,
    ) -> None:
        access_token = await self._ensure_access_token(channel)

        current = await self._request(
            "GET",
            f"{YOUTUBE_API_BASE}/videos",
            params={"part": "snippet,status", "id": youtube_video_id},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        items = current.json().get("items", [])
        if not items:
            raise NotFoundError("YouTube video not found")

        snippet = items[0].get("snippet", {})
        status = items[0].get("status", {})

        body = {
            "id": youtube_video_id,
            "snippet": {
                "title": title or snippet.get("title", ""),
                "description": description if description is not None else snippet.get("description", ""),
                "tags": tags if tags is not None else snippet.get("tags", []),
                "categoryId": snippet.get("categoryId", "22"),
            },
            "status": {
                "privacyStatus": visibility or status.get("privacyStatus", "private"),
                "selfDeclaredMadeForKids": status.get("selfDeclaredMadeForKids", False),
            },
        }

        await self._request(
            "PUT",
            f"{YOUTUBE_API_BASE}/videos",
            params={"part": "snippet,status"},
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            content=json.dumps(body),
        )

    async def get_video_stats(self, *, channel: Channel, youtube_video_id: str) -> dict[str, Any]:
        access_token = await self._ensure_access_token(channel)
        resp = await self._request(
            "GET",
            f"{YOUTUBE_API_BASE}/videos",
            params={"part": "statistics", "id": youtube_video_id},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        items = resp.json().get("items", [])
        if not items:
            raise NotFoundError("YouTube video not found")
        stats = items[0].get("statistics", {})
        return {
            "youtube_video_id": youtube_video_id,
            "view_count": int(stats.get("viewCount", 0)),
            "like_count": int(stats.get("likeCount", 0)),
            "comment_count": int(stats.get("commentCount", 0)),
            "favorite_count": int(stats.get("favoriteCount", 0)),
            "fetched_at": datetime.now(timezone.utc),
        }
