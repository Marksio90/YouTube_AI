from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.v1.deps import DB, CurrentUser
from app.core.config import settings
from app.core.security import (
    TokenValidationError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.schemas.auth import TokenPair, TokenRefresh, UserCreate, UserLogin, UserRead
from app.services.refresh_token import RefreshTokenService, build_device_fingerprint
from app.services.user import UserService

router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_OPTS: dict = {
    "httponly": True,
    "samesite": "lax",
    "secure": settings.is_production,
}


def _set_auth_cookies(response: Response, *, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        "access_token",
        access_token,
        max_age=settings.access_token_expire_minutes * 60,
        **_COOKIE_OPTS,
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        max_age=settings.refresh_token_expire_days * 86400,
        **_COOKIE_OPTS,
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", **_COOKIE_OPTS)
    response.delete_cookie("refresh_token", **_COOKIE_OPTS)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: DB) -> UserRead:
    svc = UserService(db)
    if await svc.get_by_email(payload.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = await svc.create(payload)
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenPair)
async def login(payload: UserLogin, request: Request, response: Response, db: DB) -> TokenPair:
    svc = UserService(db)
    user = await svc.authenticate(payload.email, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    access_token = create_access_token(str(user.id), str(user.organization_id), user.role.value)
    refresh_token, refresh_jti, refresh_exp = create_refresh_token(
        str(user.id), str(user.organization_id)
    )
    await RefreshTokenService(db).register(
        jti=refresh_jti,
        user_id=user.id,
        organization_id=user.organization_id,
        expires_at=refresh_exp,
        device_fingerprint=build_device_fingerprint(request),
    )

    _set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPair)
async def refresh(request: Request, response: Response, db: DB, payload: TokenRefresh | None = None) -> TokenPair:
    token_str = (payload.refresh_token if payload else None) or request.cookies.get("refresh_token")
    if not token_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")

    try:
        data = decode_token(token_str, expected_type="refresh")
    except TokenValidationError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    refresh_svc = RefreshTokenService(db)
    old_jti = data.get("jti")
    if not old_jti:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    device_fingerprint = build_device_fingerprint(request)
    is_active = await refresh_svc.validate_active(jti=old_jti, device_fingerprint=device_fingerprint)
    if not is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")

    user = await UserService(db).get_by_id(data["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    new_refresh_token, new_jti, new_exp = create_refresh_token(str(user.id), str(user.organization_id))
    rotated = await refresh_svc.revoke_and_rotate(old_jti=old_jti, new_jti=new_jti)
    if not rotated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")

    await refresh_svc.register(
        jti=new_jti,
        user_id=user.id,
        organization_id=user.organization_id,
        expires_at=new_exp,
        device_fingerprint=device_fingerprint,
    )

    new_access_token = create_access_token(str(user.id), str(user.organization_id), user.role.value)
    _set_auth_cookies(response, access_token=new_access_token, refresh_token=new_refresh_token)
    return TokenPair(access_token=new_access_token, refresh_token=new_refresh_token)


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(request: Request, response: Response, current_user: CurrentUser, db: DB) -> dict:
    await RefreshTokenService(db).revoke_all_for_user(current_user.id)
    _clear_auth_cookies(response)
    return {"detail": "logged out"}


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)
