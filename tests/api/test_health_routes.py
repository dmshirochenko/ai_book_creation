"""Tests for health check endpoint."""

import pytest
from unittest.mock import patch


class TestHealthEndpoint:
    async def test_health_check(self, async_client):
        with patch("src.api.routes.health.get_session_factory", return_value=None):
            response = await async_client.get("/api/v1/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["version"] == "1.0.0"
            assert data["openrouter_configured"] is False
            assert data["database_configured"] is False


class TestRootEndpoint:
    async def test_root(self, async_client):
        response = await async_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "docs" in data
        assert "message" in data
