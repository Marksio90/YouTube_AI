from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import text, update
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

    async def atomic_revoke(
        self, *, jti: str, new_jti: str, device_fingerprint: str | None
    ) -> bool:
        result = await self.db.execute(
            text("""
                UPDATE refresh_token_sessions
                SET revoked_at = NOW(), replaced_by_jti = :new_jti
                WHERE jti = :jti
                  AND revoked_at IS NULL
                  AND expires_at > NOW()
                  AND (device_fingerprint IS NULL OR device_fingerprint = :fingerprint)
                RETURNING jti
            """),
            {"jti": jti, "new_jti": new_jti, "fingerprint": device_fingerprint},
        )
        return result.fetchone() is not None


    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        await self.db.execute(
            update(RefreshTokenSession)
            .where(
                RefreshTokenSession.user_id == user_id,
                RefreshTokenSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )


def build_device_fingerprint(request: Request) -> str | None:
    user_agent = request.headers.get("user-agent", "").strip()
    device_id = request.headers.get("x-device-id", "").strip()

    if not user_agent and not device_id:
        return None

    raw = f"{user_agent}|{device_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
