"""Tests for credit management endpoints (GET /api/v1/credits/*)."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from src.api.app import app
from src.api.deps import get_db, get_current_user_id
from src.api.rate_limit import limiter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_pricing_row(*, operation="story_generation", cost="2.00", description="Generate a story",
                      display_name=None, is_image_model=False, display_order=0):
    """Return a mock CreditPricing row."""
    row = MagicMock()
    row.operation = operation
    row.credit_cost = Decimal(cost)
    row.description = description
    row.display_name = display_name
    row.is_image_model = is_image_model
    row.display_order = display_order
    row.is_active = True
    return row


def _make_usage_log(*, log_id=None, job_id=None, job_type="story",
                    credits_used="1.50", status="completed",
                    description="Story generation"):
    """Return a mock CreditUsageLog row."""
    log = MagicMock()
    log.id = log_id or uuid.uuid4()
    log.job_id = job_id or uuid.uuid4()
    log.job_type = job_type
    log.credits_used = Decimal(credits_used)
    log.status = status
    log.description = description
    log.user_id = _TEST_USER_ID
    log.created_at = datetime(2024, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
    return log


def _mock_db_with_scalars(rows):
    """Create a mock AsyncSession whose execute returns the given rows via scalars().all()."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = rows
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_result
    return mock_session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    """Async test client with DB and auth deps overridden."""
    mock_session = _mock_db_with_scalars([])

    async def _override_db():
        return mock_session

    async def _override_user():
        return _TEST_USER_ID

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user_id] = _override_user

    # Disable the rate limiter so tests don't hit 429
    limiter.enabled = False

    with (
        patch("src.api.app.init_db", new_callable=AsyncMock),
        patch("src.api.app.close_db", new_callable=AsyncMock),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    limiter.enabled = True
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/credits/pricing
# ---------------------------------------------------------------------------


class TestGetPricing:
    """Tests for GET /api/v1/credits/pricing."""

    async def test_returns_active_pricing(self, client):
        rows = [
            _make_pricing_row(operation="story_generation", cost="2.00", description="Generate a story"),
            _make_pricing_row(operation="image_generation", cost="0.50", description="Generate an image"),
        ]
        mock_session = _mock_db_with_scalars(rows)

        async def _override_db():
            return mock_session

        app.dependency_overrides[get_db] = _override_db

        resp = await client.get("/api/v1/credits/pricing")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["pricing"]) == 2
        assert data["pricing"][0]["operation"] == "story_generation"
        assert data["pricing"][0]["credit_cost"] == 2.0
        assert data["pricing"][0]["description"] == "Generate a story"
        assert data["pricing"][1]["operation"] == "image_generation"
        assert data["pricing"][1]["credit_cost"] == 0.5

    async def test_empty_when_no_active_pricing(self, client):
        mock_session = _mock_db_with_scalars([])

        async def _override_db():
            return mock_session

        app.dependency_overrides[get_db] = _override_db

        resp = await client.get("/api/v1/credits/pricing")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pricing"] == []


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/credits/balance
# ---------------------------------------------------------------------------


class TestGetBalance:
    """Tests for GET /api/v1/credits/balance."""

    async def test_returns_balance_as_float(self, client):
        with patch(
            "src.api.routes.credits.CreditService"
        ) as MockCreditService:
            mock_service = AsyncMock()
            mock_service.get_balance.return_value = Decimal("15.50")
            MockCreditService.return_value = mock_service

            resp = await client.get("/api/v1/credits/balance")
            assert resp.status_code == 200
            data = resp.json()
            assert data["balance"] == 15.5

    async def test_requires_auth_when_db_configured(self, monkeypatch):
        """When DATABASE_URL is set and no X-User-Id header, should return 401."""
        # Remove the user-id override so the real dependency runs
        app.dependency_overrides.pop(get_current_user_id, None)
        monkeypatch.setenv("DATABASE_URL", "postgresql://fake:fake@localhost/fake")

        with (
            patch("src.api.app.init_db", new_callable=AsyncMock),
            patch("src.api.app.close_db", new_callable=AsyncMock),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get("/api/v1/credits/balance")

        app.dependency_overrides.clear()
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/credits/usage
# ---------------------------------------------------------------------------


class TestGetUsage:
    """Tests for GET /api/v1/credits/usage."""

    async def test_returns_usage_list(self, client):
        logs = [
            _make_usage_log(job_type="story", credits_used="2.00", status="completed"),
            _make_usage_log(job_type="book", credits_used="3.50", status="completed"),
        ]
        mock_session = _mock_db_with_scalars(logs)

        async def _override_db():
            return mock_session

        app.dependency_overrides[get_db] = _override_db

        resp = await client.get("/api/v1/credits/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["usage"]) == 2
        assert data["usage"][0]["job_type"] == "story"
        assert data["usage"][0]["credits_used"] == 2.0
        assert data["usage"][0]["status"] == "completed"
        assert data["usage"][0]["created_at"] == "2024-07-01T10:00:00+00:00"
        assert data["usage"][1]["job_type"] == "book"
        assert data["usage"][1]["credits_used"] == 3.5

    async def test_empty_when_no_usage(self, client):
        mock_session = _mock_db_with_scalars([])

        async def _override_db():
            return mock_session

        app.dependency_overrides[get_db] = _override_db

        resp = await client.get("/api/v1/credits/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["usage"] == []

    async def test_limit_clamped_to_range(self, client):
        logs = [_make_usage_log()]
        mock_session = _mock_db_with_scalars(logs)

        async def _override_db():
            return mock_session

        app.dependency_overrides[get_db] = _override_db

        # limit=0 should be clamped to 1 (server clamps: max(1, min(limit, 100)))
        resp = await client.get("/api/v1/credits/usage", params={"limit": 0})
        assert resp.status_code == 200
        # Verify clamped limit=1 was passed in the SQL query
        query_0 = mock_session.execute.call_args_list[-1].args[0]
        assert query_0._limit_clause.value == 1

        # limit=999 should be clamped to 100
        resp = await client.get("/api/v1/credits/usage", params={"limit": 999})
        assert resp.status_code == 200
        query_999 = mock_session.execute.call_args_list[-1].args[0]
        assert query_999._limit_clause.value == 100
