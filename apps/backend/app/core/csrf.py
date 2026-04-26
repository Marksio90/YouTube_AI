from __future__ import annotations

import hmac
import secrets

from fastapi import HTTPException, Request, Response, status

from app.core.config import settings

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_HEADER_NAME_LOWER = CSRF_HEADER_NAME.lower()
CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

_CSRF_COOKIE_OPTS: dict = {
    "httponly": False,
    "samesite": "lax",
    "secure": settings.is_production,
}


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        max_age=settings.refresh_token_expire_days * 86400,
        **_CSRF_COOKIE_OPTS,
    )


def clear_csrf_cookie(response: Response) -> None:
    response.delete_cookie(CSRF_COOKIE_NAME, **_CSRF_COOKIE_OPTS)


def validate_csrf(request: Request) -> None:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get(CSRF_HEADER_NAME)
    if not cookie_token or not header_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing CSRF token")

    if not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")


async def csrf_middleware(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
    if request.method in CSRF_SAFE_METHODS:
        return await call_next(request)

    if not request.url.path.startswith("/api/v1"):
        return await call_next(request)

    validate_csrf(request)
    return await call_next(request)
