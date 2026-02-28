"""Tests for configuration endpoints (GET /api/v1/config/...)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport

from src.api.app import app
from src.api.deps import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_illustration_style(
    *,
    slug="watercolor",
    prompt_string="children's book illustration, soft watercolor style",
    icon_name="droplets",
    display_order=1,
    preview_image_url=None,
):
    """Return a mock IllustrationStyle row."""
    style = MagicMock()
    style.slug = slug
    style.prompt_string = prompt_string
    style.icon_name = icon_name
    style.display_order = display_order
    style.preview_image_url = preview_image_url
    return style


@pytest.fixture
async def client():
    """Async test client with DB dep overridden."""
    mock_session = AsyncMock()

    async def _override_db():
        return mock_session

    app.dependency_overrides[get_db] = _override_db

    with (
        patch("src.api.app.init_db", new_callable=AsyncMock),
        patch("src.api.app.close_db", new_callable=AsyncMock),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests — GET /config/illustration-styles
# ---------------------------------------------------------------------------


class TestGetIllustrationStyles:
    """Tests for GET /api/v1/config/illustration-styles."""

    async def test_returns_active_styles(self, client):
        styles = [
            _make_illustration_style(slug="watercolor", display_order=1),
            _make_illustration_style(
                slug="2d-cartoon",
                prompt_string="children's book illustration, 2D cartoon style",
                icon_name="film",
                display_order=2,
            ),
        ]
        with patch(
            "src.api.routes.config.repo.list_active_illustration_styles",
            new_callable=AsyncMock,
            return_value=styles,
        ):
            resp = await client.get("/api/v1/config/illustration-styles")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["styles"]) == 2
            assert data["styles"][0]["slug"] == "watercolor"
            assert data["styles"][0]["icon_name"] == "droplets"
            assert "prompt_string" not in data["styles"][0]
            assert data["styles"][1]["slug"] == "2d-cartoon"
            assert data["styles"][1]["display_order"] == 2

    async def test_returns_empty_when_no_styles(self, client):
        with patch(
            "src.api.routes.config.repo.list_active_illustration_styles",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await client.get("/api/v1/config/illustration-styles")
            assert resp.status_code == 200
            assert resp.json()["styles"] == []

    async def test_includes_preview_image_url(self, client):
        style = _make_illustration_style(
            preview_image_url="https://example.com/preview.png",
        )
        with patch(
            "src.api.routes.config.repo.list_active_illustration_styles",
            new_callable=AsyncMock,
            return_value=[style],
        ):
            resp = await client.get("/api/v1/config/illustration-styles")
            assert resp.status_code == 200
            data = resp.json()
            assert data["styles"][0]["preview_image_url"] == "https://example.com/preview.png"

    async def test_preview_image_url_null_by_default(self, client):
        style = _make_illustration_style()
        with patch(
            "src.api.routes.config.repo.list_active_illustration_styles",
            new_callable=AsyncMock,
            return_value=[style],
        ):
            resp = await client.get("/api/v1/config/illustration-styles")
            assert resp.status_code == 200
            assert resp.json()["styles"][0]["preview_image_url"] is None


# ---------------------------------------------------------------------------
# Tests — GET /config/text-on-image-languages (existing, verify not broken)
# ---------------------------------------------------------------------------


class TestGetTextOnImageLanguages:
    """Existing endpoint — verify it still works."""

    async def test_returns_supported_languages(self, client):
        resp = await client.get("/api/v1/config/text-on-image-languages")
        assert resp.status_code == 200
        data = resp.json()
        assert "supported_languages" in data
        assert isinstance(data["supported_languages"], list)
