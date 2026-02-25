"""Tests for credit integration in POST /api/v1/stories/create."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from src.api.app import app
from src.api.deps import get_db, get_current_user_id
from src.api.rate_limit import limiter
from src.services.credit_service import InsufficientCreditsError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

_VALID_BODY = {
    "prompt": "A curious kitten discovers a magical garden in the backyard",
    "age_min": 2,
    "age_max": 4,
    "tone": "cheerful",
    "length": "medium",
    "language": "English",
}

_PRICING_SNAPSHOT = {"story_generation": Decimal("1.00")}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    """Async test client with DB and auth deps overridden."""
    mock_session = AsyncMock()

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
# Tests
# ---------------------------------------------------------------------------


class TestStoryCredits:
    """Tests for credit reserve/deduction in POST /api/v1/stories/create."""

    async def test_create_story_reserves_credits(self, client):
        """reserve() is called with the correct amount and job_type='story'."""
        usage_log_id = uuid.uuid4()

        with (
            patch(
                "src.api.routes.stories.CreditService.calculate_story_cost",
                new_callable=AsyncMock,
                return_value=Decimal("1.00"),
            ),
            patch(
                "src.api.routes.stories.CreditService.get_pricing",
                new_callable=AsyncMock,
                return_value=_PRICING_SNAPSHOT,
            ),
            patch(
                "src.api.routes.stories.CreditService.reserve",
                new_callable=AsyncMock,
                return_value=usage_log_id,
            ) as mock_reserve,
            patch(
                "src.api.routes.stories.repo.create_story_job",
                new_callable=AsyncMock,
            ),
        ):
            resp = await client.post("/api/v1/stories/create", json=_VALID_BODY)

            assert resp.status_code == 200
            mock_reserve.assert_called_once()
            call_kwargs = mock_reserve.call_args.kwargs
            assert call_kwargs["amount"] == Decimal("1.00")
            assert call_kwargs["job_type"] == "story"

    async def test_create_story_returns_402_on_insufficient_credits(self, client):
        """Returns 402 when user does not have enough credits."""
        with (
            patch(
                "src.api.routes.stories.CreditService.calculate_story_cost",
                new_callable=AsyncMock,
                return_value=Decimal("1.00"),
            ),
            patch(
                "src.api.routes.stories.CreditService.get_pricing",
                new_callable=AsyncMock,
                return_value=_PRICING_SNAPSHOT,
            ),
            patch(
                "src.api.routes.stories.CreditService.reserve",
                new_callable=AsyncMock,
                side_effect=InsufficientCreditsError(
                    balance=Decimal("0.50"), required=Decimal("1.00")
                ),
            ),
        ):
            resp = await client.post("/api/v1/stories/create", json=_VALID_BODY)
            assert resp.status_code == 402

    async def test_402_detail_format(self, client):
        """The 402 response body matches the expected detail structure."""
        with (
            patch(
                "src.api.routes.stories.CreditService.calculate_story_cost",
                new_callable=AsyncMock,
                return_value=Decimal("1.00"),
            ),
            patch(
                "src.api.routes.stories.CreditService.get_pricing",
                new_callable=AsyncMock,
                return_value=_PRICING_SNAPSHOT,
            ),
            patch(
                "src.api.routes.stories.CreditService.reserve",
                new_callable=AsyncMock,
                side_effect=InsufficientCreditsError(
                    balance=Decimal("0.50"), required=Decimal("1.00")
                ),
            ),
        ):
            resp = await client.post("/api/v1/stories/create", json=_VALID_BODY)
            assert resp.status_code == 402
            detail = resp.json()["detail"]
            assert detail == {"message": "Insufficient credits", "balance": 0.5, "required": 1.0}

    async def test_create_story_passes_usage_log_id_to_task(self, client):
        """The usage_log_id returned by reserve() is forwarded to the background task."""
        usage_log_id = uuid.uuid4()

        with (
            patch(
                "src.api.routes.stories.CreditService.calculate_story_cost",
                new_callable=AsyncMock,
                return_value=Decimal("1.00"),
            ),
            patch(
                "src.api.routes.stories.CreditService.get_pricing",
                new_callable=AsyncMock,
                return_value=_PRICING_SNAPSHOT,
            ),
            patch(
                "src.api.routes.stories.CreditService.reserve",
                new_callable=AsyncMock,
                return_value=usage_log_id,
            ),
            patch(
                "src.api.routes.stories.repo.create_story_job",
                new_callable=AsyncMock,
            ),
            patch(
                "src.api.routes.stories.BackgroundTasks.add_task",
            ) as mock_add_task,
        ):
            resp = await client.post("/api/v1/stories/create", json=_VALID_BODY)

            assert resp.status_code == 200
            mock_add_task.assert_called_once()
            # add_task(create_story_task, str(job_id), body, user_id, usage_log_id)
            positional_args = mock_add_task.call_args.args
            assert positional_args[4] == usage_log_id
