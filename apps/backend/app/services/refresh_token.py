from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.refresh_token_session import RefreshTokenSession


class RefreshTokenService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register(
        self,
        *,
        jti: str,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        expires_at: datetime,
        device_fingerprint: str | None,
    ) -> None:
        self.db.add(
            RefreshTokenSession(
                jti=jti,
                user_id=user_id,
                organization_id=organization_id,
                expires_at=expires_at,
                device_fingerprint=device_fingerprint,
            )
        )

    async def validate_active(self, *, jti: str, device_fingerprint: str | None) -> bool:
        session = await self.db.get(RefreshTokenSession, jti)
        if not session:
            return False
        if session.revoked_at is not None:
            return False
        if session.expires_at <= datetime.now(UTC):
            return False
        if session.device_fingerprint and session.device_fingerprint != device_fingerprint:
            return False
        return True

    async def revoke_and_rotate(self, *, old_jti: str, new_jti: str) -> bool:
        session = await self.db.get(RefreshTokenSession, old_jti)
        if not session or session.revoked_at is not None:
            return False
        session.revoked_at = datetime.now(UTC)
        session.replaced_by_jti = new_jti
        return True


def build_device_fingerprint(request: Request) -> str | None:
    user_agent = request.headers.get("user-agent", "").strip()
    device_id = request.headers.get("x-device-id", "").strip()

    if not user_agent and not device_id:
        return None

    raw = f"{user_agent}|{device_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
