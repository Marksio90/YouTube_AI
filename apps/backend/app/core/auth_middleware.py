from __future__ import annotations

from fastapi import HTTPException, Request, Response, status

from app.core.security import decode_token

PUBLIC_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/health",
    "/version",
    "/metrics",
}


async def auth_middleware(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
    path = request.url.path

    if not path.startswith("/api/v1") or path in PUBLIC_PATHS:
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = auth_header.removeprefix("Bearer ").strip()
    try:
        token_data = decode_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    if token_data.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    request.state.token_data = token_data
    return await call_next(request)
