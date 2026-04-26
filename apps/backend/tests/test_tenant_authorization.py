from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.deps import get_current_user
from app.db.models.user import UserRole


@pytest.mark.asyncio
async def test_get_current_user_rejects_tenant_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    token_org = str(uuid4())
    user_org = uuid4()

    fake_request = SimpleNamespace(state=SimpleNamespace(token_data={"sub": "user-1", "type": "access", "org": token_org}))
    fake_user = SimpleNamespace(is_active=True, organization_id=user_org, role=UserRole.admin)

    mocked_get_by_id = AsyncMock(return_value=fake_user)
    monkeypatch.setattr("app.services.user.UserService.get_by_id", mocked_get_by_id)

    with pytest.raises(HTTPException) as exc:
        await get_current_user(fake_request, credentials=None, db=SimpleNamespace())

    assert exc.value.status_code == 403
    assert exc.value.detail == "Token organization mismatch"


@pytest.mark.asyncio
async def test_get_current_user_accepts_matching_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    org_id = uuid4()

    fake_request = SimpleNamespace(state=SimpleNamespace(token_data={"sub": "user-1", "type": "access", "org": str(org_id)}))
    fake_user = SimpleNamespace(is_active=True, organization_id=org_id, role=UserRole.user)

    mocked_get_by_id = AsyncMock(return_value=fake_user)
    monkeypatch.setattr("app.services.user.UserService.get_by_id", mocked_get_by_id)

    current_user = await get_current_user(fake_request, credentials=None, db=SimpleNamespace())

    assert current_user is fake_user
