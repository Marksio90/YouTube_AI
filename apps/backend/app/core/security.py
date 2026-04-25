import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenValidationError(ValueError):
    pass


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _base_claims(*, subject: str | Any, organization_id: str, token_type: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "sub": str(subject),
        "org": organization_id,
        "type": token_type,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": str(uuid.uuid4()),
        "iat": now,
    }


def create_access_token(
    subject: str | Any,
    organization_id: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    claims = _base_claims(subject=subject, organization_id=organization_id, token_type="access")
    claims.update({"role": role, "exp": expire})
    return jwt.encode(
        claims,
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(subject: str | Any, organization_id: str) -> tuple[str, str, datetime]:
    expire = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    claims = _base_claims(subject=subject, organization_id=organization_id, token_type="refresh")
    claims.update({"exp": expire})
    token = jwt.encode(
        claims,
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, claims["jti"], expire


def decode_token(token: str, *, expected_type: str | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"verify_aud": True, "verify_iss": True},
        )
    except JWTError as exc:
        raise TokenValidationError("Invalid token") from exc

    token_type = payload.get("type")
    if expected_type and token_type != expected_type:
        raise TokenValidationError("Invalid token type")

    return payload
