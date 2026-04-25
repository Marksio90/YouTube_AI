"""
YouTube Analytics API v2 client.

Metrics collected
─────────────────
  Channel-level (daily):
    views, estimatedMinutesWatched, impressions, impressionClickThroughRate,
    subscribersGained, subscribersLost, estimatedRevenue, cpm, rpm,
    averageViewDuration

  Video-level (daily):
    views, estimatedMinutesWatched, impressions, impressionClickThroughRate,
    averageViewDuration, likes, comments, estimatedRevenue, rpm, cpm

Token lifecycle
───────────────
  Tokens are stored encrypted (Fernet) in channel.access_token_enc /
  refresh_token_enc.  On 401 the client calls _refresh() once, persists the
  new access_token to the DB, then retries.  If still 401 → raises
  YouTubeAuthError (caller should mark channel status=needs_reauth).

Usage (worker context — no DB session available directly)
──────────────────────────────────────────────────────────
  client = YouTubeAnalyticsClient.from_channel_row(channel_row, db_session)
  day_data = await client.channel_report(yt_channel_id, "2026-04-24")
  vid_data = await client.video_report(yt_video_id, "2026-04-24")

  async with YouTubeAnalyticsClient(...) as client:
      ...
"""
from __future__ import annotations

import base64
import hashlib
import logging
from datetime import date, datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceError, UnauthorizedError

log = logging.getLogger(__name__)

_ANALYTICS_BASE = "https://youtubeanalytics.googleapis.com/v2"
_TOKEN_URL = "https://oauth2.googleapis.com/token"

_CHANNEL_METRICS = (
    "views,"
    "estimatedMinutesWatched,"
    "impressions,"
    "impressionClickThroughRate,"
    "subscribersGained,"
    "subscribersLost,"
    "estimatedRevenue,"
    "cpm,"
    "rpm,"
    "averageViewDuration"
)

_VIDEO_METRICS = (
    "views,"
    "estimatedMinutesWatched,"
    "impressions,"
    "impressionClickThroughRate,"
    "averageViewDuration,"
    "likes,"
    "comments,"
    "estimatedRevenue,"
    "rpm,"
    "cpm"
)


class YouTubeAuthError(UnauthorizedError):
    """Token expired and could not be refreshed — channel needs reauth."""


def _fernet():
    from cryptography.fernet import Fernet
    key = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _decrypt(enc: str) -> str:
    return _fernet().decrypt(enc.encode()).decode()


def _encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


class YouTubeAnalyticsClient:
    """
    Async context-manager wrapping YouTube Analytics API v2.

    Handles token refresh automatically — pass a db_session so the refreshed
    access token is persisted back to the channel row.
    """

    def __init__(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        channel_db_id: str,
        db_session=None,
    ) -> None:
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._channel_db_id = channel_db_id
        self._db = db_session
        self._http: httpx.AsyncClient | None = None

    @classmethod
    def from_channel_row(
        cls,
        channel: dict[str, Any],
        db_session=None,
    ) -> "YouTubeAnalyticsClient":
        """Build client from a raw DB channel row (mapping with enc fields)."""
        enc_access = channel.get("access_token_enc")
        enc_refresh = channel.get("refresh_token_enc")
        if not enc_access:
            raise YouTubeAuthError("Channel has no OAuth token — needs reauth")
        return cls(
            access_token=_decrypt(enc_access),
            refresh_token=_decrypt(enc_refresh) if enc_refresh else None,
            channel_db_id=str(channel["id"]),
            db_session=db_session,
        )

    async def __aenter__(self) -> "YouTubeAnalyticsClient":
        self._http = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, *_) -> None:
        if self._http:
            await self._http.aclose()

    # ── Public API ────────────────────────────────────────────────────────────

    async def channel_report(
        self,
        youtube_channel_id: str,
        snapshot_date: str | date,
    ) -> dict[str, Any]:
        """
        Returns a dict with keys matching AnalyticsSnapshot columns.

        snapshot_date: ISO "YYYY-MM-DD"
        """
        d = snapshot_date if isinstance(snapshot_date, str) else snapshot_date.isoformat()
        params = {
            "ids": f"channel=={youtube_channel_id}",
            "startDate": d,
            "endDate": d,
            "metrics": _CHANNEL_METRICS,
            "dimensions": "day",
        }
        rows = await self._query(params)
        if not rows:
            return _empty_channel_metrics()
        r = rows[0]
        # row order: day, views, estimatedMinutesWatched, impressions, ctr,
        #            subGained, subLost, revenue, cpm, rpm, avgViewDuration
        return {
            "views":                    int(r[1]),
            "watch_time_hours":         round(float(r[2]) / 60, 4),
            "impressions":              int(r[3]),
            "ctr":                      round(float(r[4]), 6),
            "subscribers_gained":       int(r[5]),
            "subscribers_lost":         int(r[6]),
            "revenue_usd":              round(float(r[7]), 4),
            "cpm":                      round(float(r[8]), 4),
            "rpm":                      round(float(r[9]), 4),
            "avg_view_duration_seconds": round(float(r[10]), 1),
            "like_count":               0,
            "comment_count":            0,
        }

    async def video_report(
        self,
        youtube_video_id: str,
        snapshot_date: str | date,
        youtube_channel_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Per-video analytics for a single day.

        youtube_channel_id: required by the YouTube Analytics API for the
        `ids` filter — if not supplied, uses "channel==MINE" which works
        when the OAuth token belongs to that channel.
        """
        d = snapshot_date if isinstance(snapshot_date, str) else snapshot_date.isoformat()
        channel_filter = (
            f"channel=={youtube_channel_id}" if youtube_channel_id else "channel==MINE"
        )
        params = {
            "ids": channel_filter,
            "startDate": d,
            "endDate": d,
            "metrics": _VIDEO_METRICS,
            "dimensions": "day",
            "filters": f"video=={youtube_video_id}",
        }
        rows = await self._query(params)
        if not rows:
            return _empty_video_metrics()
        r = rows[0]
        # row order: day, views, minutesWatched, impressions, ctr,
        #            avgViewDuration, likes, comments, revenue, rpm, cpm
        return {
            "views":                    int(r[1]),
            "watch_time_hours":         round(float(r[2]) / 60, 4),
            "impressions":              int(r[3]),
            "ctr":                      round(float(r[4]), 6),
            "avg_view_duration_seconds": round(float(r[5]), 1),
            "like_count":               int(r[6]),
            "comment_count":            int(r[7]),
            "revenue_usd":              round(float(r[8]), 4),
            "rpm":                      round(float(r[9]), 4),
            "cpm":                      round(float(r[10]), 4),
            "subscribers_gained":       0,
            "subscribers_lost":         0,
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _query(self, params: dict) -> list[list]:
        """Execute Analytics API query; auto-refresh token on 401."""
        assert self._http, "Use as async context manager"
        resp = await self._http.get(
            f"{_ANALYTICS_BASE}/reports",
            params=params,
            headers={"Authorization": f"Bearer {self._access_token}"},
        )
        if resp.status_code == 401:
            await self._refresh()
            resp = await self._http.get(
                f"{_ANALYTICS_BASE}/reports",
                params=params,
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
        if resp.status_code == 401:
            raise YouTubeAuthError(
                f"YouTube Analytics 401 after token refresh — channel {self._channel_db_id} needs reauth"
            )
        if resp.status_code >= 400:
            raise ExternalServiceError(
                f"YouTube Analytics API {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json().get("rows", [])

    async def _refresh(self) -> None:
        """Exchange refresh_token → new access_token; persist to DB."""
        if not self._refresh_token:
            raise YouTubeAuthError(
                f"No refresh token for channel {self._channel_db_id}"
            )
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.post(
                _TOKEN_URL,
                data={
                    "refresh_token": self._refresh_token,
                    "client_id": settings.youtube_client_id,
                    "client_secret": settings.youtube_client_secret,
                    "grant_type": "refresh_token",
                },
            )
        if resp.status_code >= 400:
            raise YouTubeAuthError(
                f"Token refresh failed {resp.status_code}: {resp.text[:200]}"
            )
        new_token = resp.json()["access_token"]
        self._access_token = new_token
        log.info("youtube_analytics.token_refreshed", channel_id=self._channel_db_id)

        # Persist encrypted token back to DB if session available
        if self._db is not None:
            from sqlalchemy import text
            await self._db.execute(
                text(
                    "UPDATE channels SET access_token_enc=:enc, updated_at=NOW() WHERE id=:id"
                ),
                {"enc": _encrypt(new_token), "id": self._channel_db_id},
            )


# ── Empty metric dicts (no data for that day) ─────────────────────────────────

def _empty_channel_metrics() -> dict[str, Any]:
    return {
        "views": 0,
        "watch_time_hours": 0.0,
        "impressions": 0,
        "ctr": 0.0,
        "subscribers_gained": 0,
        "subscribers_lost": 0,
        "revenue_usd": 0.0,
        "cpm": 0.0,
        "rpm": 0.0,
        "avg_view_duration_seconds": 0.0,
        "like_count": 0,
        "comment_count": 0,
    }


def _empty_video_metrics() -> dict[str, Any]:
    return {
        "views": 0,
        "watch_time_hours": 0.0,
        "impressions": 0,
        "ctr": 0.0,
        "avg_view_duration_seconds": 0.0,
        "like_count": 0,
        "comment_count": 0,
        "revenue_usd": 0.0,
        "rpm": 0.0,
        "cpm": 0.0,
        "subscribers_gained": 0,
        "subscribers_lost": 0,
    }
