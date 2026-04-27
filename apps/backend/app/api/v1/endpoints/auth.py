from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.v1.deps import CurrentUser, DB
from app.core.config import settings
from app.core.csrf import clear_csrf_cookie, generate_csrf_token, set_csrf_cookie
from app.core.rate_limit import limiter
from app.core.security import (
    TokenValidationError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.schemas.auth import TokenPair, TokenRefresh, UserCreate, UserLogin, UserRead
from app.services.refresh_token import RefreshTokenService, build_device_fingerprint
from app.services.user import UserService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

ACCESS_COOKIE_NAME = "access_token"
REFRESH_COOKIE_NAME = "refresh_token"
COOKIE_PATH = "/"

_COOKIE_SET_OPTS: dict[str, Any] = {
    "httponly": True,
    "samesite": "lax",
    "secure": settings.is_production,
    "path": COOKIE_PATH,
}

_COOKIE_DELETE_OPTS: dict[str, Any] = {
    "samesite": "lax",
    "secure": settings.is_production,
    "path": COOKIE_PATH,
}


def _set_auth_cookies(response: Response, *, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        access_token,
        max_age=settings.access_token_expire_minutes * 60,
        **_COOKIE_SET_OPTS,
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=settings.refresh_token_expire_days * 86400,
        **_COOKIE_SET_OPTS,
    )

    csrf_token = generate_csrf_token()
    set_csrf_cookie(response, csrf_token)


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE_NAME, **_COOKIE_DELETE_OPTS)
    response.delete_cookie(REFRESH_COOKIE_NAME, **_COOKIE_DELETE_OPTS)
    clear_csrf_cookie(response)


def _token_from_refresh_request(request: Request, payload: TokenRefresh | None) -> str | None:
    body_token = payload.refresh_token.strip() if payload and payload.refresh_token else None
    cookie_token = request.cookies.get(REFRESH_COOKIE_NAME)
    return body_token or cookie_token


@router.get("/csrf", status_code=status.HTTP_200_OK)
async def csrf(response: Response) -> dict[str, str]:
    token = generate_csrf_token()
    set_csrf_cookie(response, token)
    return {"csrf_token": token}


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, payload: UserCreate, db: DB) -> UserRead:
    user_service = UserService(db)

    existing_user = await user_service.get_by_email(payload.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    try:
        user = await user_service.create(payload)
        await db.commit()
        await db.refresh(user)
    except Exception:
        await db.rollback()
        logger.exception("auth.register_failed", email=str(payload.email).lower())
        raise

    logger.info(
        "auth.registered",
        user_id=str(user.id),
        organization_id=str(user.organization_id),
        email=user.email,
    )

    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenPair)
@limiter.limit("10/minute")
async def login(
    request: Request,
    payload: UserLogin,
    response: Response,
    db: DB,
) -> TokenPair:
    user_service = UserService(db)
    user = await user_service.authenticate(payload.email, payload.password)

    if not user or not user.is_active:
        logger.warning("auth.login_failed", email=str(payload.email).lower())
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    access_token = create_access_token(
        str(user.id),
        str(user.organization_id),
        user.role.value,
    )
    refresh_token, refresh_jti, refresh_exp = create_refresh_token(
        str(user.id),
        str(user.organization_id),
    )

    refresh_service = RefreshTokenService(db)
    device_fingerprint = build_device_fingerprint(request)

    try:
        await refresh_service.register(
            jti=refresh_jti,
            user_id=user.id,
            organization_id=user.organization_id,
            expires_at=refresh_exp,
            device_fingerprint=device_fingerprint,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("auth.login_refresh_session_failed", user_id=str(user.id))
        raise

    _set_auth_cookies(
        response,
        access_token=access_token,
        refresh_token=refresh_token,
    )

    logger.info(
        "auth.login_success",
        user_id=str(user.id),
        organization_id=str(user.organization_id),
        has_device_fingerprint=bool(device_fingerprint),
    )

    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPair)
@limiter.limit("20/minute")
async def refresh(
    request: Request,
    response: Response,
    db: DB,
    payload: TokenRefresh | None = None,
) -> TokenPair:
    token_str = _token_from_refresh_request(request, payload)
    if not token_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
        )

    try:
        data = decode_token(token_str, expected_type="refresh")
    except TokenValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from exc

    old_jti = data.get("jti")
    subject = data.get("sub")

    if not old_jti or not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user = await UserService(db).get_by_id(subject)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    device_fingerprint = build_device_fingerprint(request)
    refresh_service = RefreshTokenService(db)

    new_refresh_token, new_jti, new_exp = create_refresh_token(
        str(user.id),
        str(user.organization_id),
    )

    try:
        revoked = await refresh_service.atomic_revoke(
            jti=old_jti,
            new_jti=new_jti,
            device_fingerprint=device_fingerprint,
        )
        if not revoked:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token revoked",
            )

        await refresh_service.register(
            jti=new_jti,
            user_id=user.id,
            organization_id=user.organization_id,
            expires_at=new_exp,
            device_fingerprint=device_fingerprint,
        )
        await db.commit()
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("auth.refresh_failed", user_id=str(user.id))
        raise

    new_access_token = create_access_token(
        str(user.id),
        str(user.organization_id),
        user.role.value,
    )

    _set_auth_cookies(
        response,
        access_token=new_access_token,
        refresh_token=new_refresh_token,
    )

    logger.info(
        "auth.refresh_success",
        user_id=str(user.id),
        organization_id=str(user.organization_id),
        old_jti=old_jti,
        new_jti=new_jti,
        has_device_fingerprint=bool(device_fingerprint),
    )

    return TokenPair(access_token=new_access_token, refresh_token=new_refresh_token)


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    request: Request,
    response: Response,
    current_user: CurrentUser,
    db: DB,
) -> dict[str, str]:
    try:
        await RefreshTokenService(db).revoke_all_for_user(current_user.id)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("auth.logout_failed", user_id=str(current_user.id))
        raise

    _clear_auth_cookies(response)

    logger.info(
        "auth.logout_success",
        user_id=str(current_user.id),
        organization_id=str(current_user.organization_id),
    )

    return {"detail": "logged out"}


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)
