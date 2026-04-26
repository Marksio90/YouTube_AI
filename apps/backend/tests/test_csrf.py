from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, csrf_middleware


def build_test_app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(csrf_middleware)

    @app.get("/api/v1/auth/csrf")
    async def csrf() -> dict[str, str]:
        return {"ok": "ok"}

    @app.post("/api/v1/auth/refresh")
    async def refresh() -> dict[str, str]:
        return {"ok": "ok"}

    @app.patch("/api/v1/resources/1")
    async def patch_resource() -> dict[str, str]:
        return {"ok": "ok"}

    return app


def test_mutating_auth_endpoint_rejects_missing_csrf_token() -> None:
    client = TestClient(build_test_app())

    response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 403
    assert response.json()["detail"] == "Missing CSRF token"


def test_mutating_resource_rejects_mismatched_csrf_token() -> None:
    client = TestClient(build_test_app())

    response = client.patch(
        "/api/v1/resources/1",
        cookies={CSRF_COOKIE_NAME: "cookie-token"},
        headers={CSRF_HEADER_NAME: "header-token"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid CSRF token"


def test_mutating_resource_accepts_matching_csrf_token() -> None:
    client = TestClient(build_test_app())

    response = client.patch(
        "/api/v1/resources/1",
        cookies={CSRF_COOKIE_NAME: "same-token"},
        headers={CSRF_HEADER_NAME: "same-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": "ok"}
