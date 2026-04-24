"""
YouTube Data API v3 + OAuth 2.0 integration.

Handles token exchange, channel metadata sync, and video uploads.
Token encryption/decryption uses Fernet symmetric encryption keyed
from settings.secret_key — swap for KMS in production.
"""

import base64
import hashlib

import httpx
import structlog
from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.exceptions import ExternalServiceError, UnauthorizedError

logger = structlog.get_logger(__name__)

YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


def _get_fernet() -> Fernet:
    key = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_token(token: str) -> str:
    return _get_fernet().encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    return _get_fernet().decrypt(encrypted.encode()).decode()


class YouTubeClient:
    def __init__(self, access_token: str) -> None:
        self._token = access_token
        self._http = httpx.AsyncClient(
            base_url=YOUTUBE_API_BASE,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )

    async def __aenter__(self) -> "YouTubeClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self._http.aclose()

    async def get_channel_info(self) -> dict:
        resp = await self._http.get(
            "/channels",
            params={"part": "snippet,statistics,status", "mine": "true"},
        )
        self._raise_for_status(resp)
        items = resp.json().get("items", [])
        if not items:
            raise ExternalServiceError("No YouTube channel found for this token")
        return items[0]

    async def get_video_stats(self, youtube_video_id: str) -> dict:
        resp = await self._http.get(
            "/videos",
            params={"part": "statistics,contentDetails", "id": youtube_video_id},
        )
        self._raise_for_status(resp)
        items = resp.json().get("items", [])
        if not items:
            raise ExternalServiceError(f"Video {youtube_video_id} not found")
        return items[0]

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code == 401:
            raise UnauthorizedError("YouTube token expired or revoked")
        if resp.status_code >= 400:
            raise ExternalServiceError(
                f"YouTube API error {resp.status_code}: {resp.text[:200]}"
            )


async def exchange_code_for_tokens(code: str, redirect_uri: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            YOUTUBE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.youtube_client_id,
                "client_secret": settings.youtube_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if resp.status_code >= 400:
            raise ExternalServiceError(
                f"Token exchange failed: {resp.status_code} {resp.text[:200]}"
            )
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            YOUTUBE_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.youtube_client_id,
                "client_secret": settings.youtube_client_secret,
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code >= 400:
            raise ExternalServiceError(
                f"Token refresh failed: {resp.status_code} {resp.text[:200]}"
            )
        return resp.json()
