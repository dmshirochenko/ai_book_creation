"""Tests for API key validation middleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.middleware import ApiKeyMiddleware


def _make_app(secret: str | None) -> FastAPI:
    app = FastAPI()

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.add_middleware(ApiKeyMiddleware, api_key=secret, exempt_paths={"/health", "/"})
    return app


class TestApiKeyMiddleware:
    def test_rejects_missing_key(self):
        app = _make_app("my-secret")
        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 403
        assert response.json()["detail"] == "Invalid or missing API key"

    def test_rejects_wrong_key(self):
        app = _make_app("my-secret")
        client = TestClient(app)
        response = client.get("/test", headers={"X-Api-Key": "wrong"})
        assert response.status_code == 403

    def test_accepts_correct_key(self):
        app = _make_app("my-secret")
        client = TestClient(app)
        response = client.get("/test", headers={"X-Api-Key": "my-secret"})
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_exempt_paths_skip_validation(self):
        app = _make_app("my-secret")
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200

    def test_disabled_when_no_secret(self):
        app = _make_app(None)
        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 200

    def test_options_requests_pass_through(self):
        app = _make_app("my-secret")
        client = TestClient(app)
        response = client.options("/test")
        # Middleware lets OPTIONS through (no 403); FastAPI returns 405
        # because there is no OPTIONS handler defined on the test endpoint.
        assert response.status_code != 403
