from __future__ import annotations

import json

from fastapi import Request, Response, status

from app.core.security import TokenValidationError, decode_token

PUBLIC_PATHS = {
    "/api/v1/auth/csrf",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/api/v1/youtube/callback",
    "/api/v1/auth/youtube/callback",
    "/health",
    "/version",
    "/metrics",
}

_UNAUTHORIZED = Response(
    content=json.dumps({"detail": "Missing bearer token"}),
    status_code=status.HTTP_401_UNAUTHORIZED,
    media_type="application/json",
)
_INVALID_TOKEN = Response(
    content=json.dumps({"detail": "Invalid token"}),
    status_code=status.HTTP_401_UNAUTHORIZED,
    media_type="application/json",
)


async def auth_middleware(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
    path = request.url.path

    if not path.startswith("/api/v1") or path in PUBLIC_PATHS:
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
    else:
        token = request.cookies.get("access_token")

    if not token:
        return _UNAUTHORIZED
    try:
        token_data = decode_token(token, expected_type="access")
    except TokenValidationError:
        return _INVALID_TOKEN

    request.state.token_data = token_data
    return await call_next(request)
