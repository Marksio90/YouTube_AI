import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.db.models.organization import Organization, slugify
from app.db.models.user import User, UserRole
from app.schemas.auth import UserCreate


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: str | uuid.UUID) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def _unique_org_slug(self, base_name: str) -> str:
        base_slug = slugify(base_name)
        slug = base_slug
        index = 1

        while True:
            exists = await self.db.execute(select(Organization.id).where(Organization.slug == slug))
            if exists.scalar_one_or_none() is None:
                return slug
            index += 1
            slug = f"{base_slug}-{index}"

    async def create(self, payload: UserCreate) -> User:
        org_name = payload.organization_name or f"{payload.name} Workspace"
        organization = Organization(
            name=org_name,
            slug=await self._unique_org_slug(org_name),
        )
        self.db.add(organization)
        await self.db.flush()

        user = User(
            organization_id=organization.id,
            email=payload.email.lower(),
            name=payload.name,
            hashed_password=hash_password(payload.password),
            role=UserRole.admin,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def authenticate(self, email: str, password: str) -> User | None:
        user = await self.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            return None
        return user
