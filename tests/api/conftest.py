"""API-specific test fixtures."""

import pytest
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient, ASGITransport

from src.api.app import app


@pytest.fixture
async def async_client():
    """Async test client for FastAPI."""
    # Patch database initialization to avoid real DB connections
    with (
        patch("src.api.app.init_db", new_callable=AsyncMock),
        patch("src.api.app.close_db", new_callable=AsyncMock),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
