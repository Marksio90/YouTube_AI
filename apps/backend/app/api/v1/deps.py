from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenValidationError, decode_token
from app.db.models.user import User, UserRole
from app.db.session import get_db
from app.services.user import UserService

bearer_scheme = HTTPBearer(auto_error=False)

# ── Database ──────────────────────────────────────────────────────────────────
DB = Annotated[AsyncSession, Depends(get_db)]


# ── Auth ──────────────────────────────────────────────────────────────────────
async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: DB,
) -> User:
    token_data = getattr(request.state, "token_data", None)

    if token_data is None:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
            )
        try:
            token_data = decode_token(credentials.credentials, expected_type="access")
        except TokenValidationError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
            )

    if token_data.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user = await UserService(db).get_by_id(token_data["sub"])
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    token_org = token_data.get("org")
    if token_org and str(user.organization_id) != str(token_org):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token organization mismatch",
        )

    return user


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    async def _checker(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return current_user

    return _checker


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_roles(UserRole.admin))]
