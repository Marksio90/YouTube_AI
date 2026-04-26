from datetime import timedelta

import pytest

from app.core.security import (
    TokenValidationError,
    create_access_token,
    create_refresh_token,
    decode_token,
)



def test_access_token_roundtrip_contains_expected_claims() -> None:
    token = create_access_token(
        subject="user-123",
        organization_id="org-123",
        role="admin",
        expires_delta=timedelta(minutes=5),
    )

    payload = decode_token(token, expected_type="access")

    assert payload["sub"] == "user-123"
    assert payload["org"] == "org-123"
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


def test_refresh_token_roundtrip_and_type_enforcement() -> None:
    token, jti, _ = create_refresh_token(subject="user-456", organization_id="org-999")

    payload = decode_token(token, expected_type="refresh")

    assert payload["sub"] == "user-456"
    assert payload["org"] == "org-999"
    assert payload["type"] == "refresh"
    assert payload["jti"] == jti

    with pytest.raises(TokenValidationError):
        decode_token(token, expected_type="access")
