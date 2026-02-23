"""Tests for credit integration in POST /api/v1/books/generate."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from src.api.app import app
from src.api.deps import get_db, get_current_user_id
from src.api.rate_limit import limiter
from src.services.credit_service import InsufficientCreditsError


# ---------------------------------------------------------------------------
# Helpers / test data
# ---------------------------------------------------------------------------

_TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

_STRUCTURED_STORY = {
    "title": "Test Story",
    "pages": [{"text": f"Page {i} text."} for i in range(1, 9)],  # 8 pages
}

_VALID_BOOK_BODY = {
    "story": "Once upon a time there was a little bunny.",
    "story_structured": _STRUCTURED_STORY,
    "title": "Test Story",
    "generate_images": True,
}

_PRICING_SNAPSHOT = {
    "page_with_images": Decimal("2.00"),
    "page_without_images": Decimal("1.00"),
    "story_generation": Decimal("1.00"),
}


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


class TestBookCredits:
    """Tests for credit reserve/deduction in POST /api/v1/books/generate."""

    async def test_generate_book_reserves_credits(self, client):
        """reserve() is called with amount=16.00 and job_type='book' for an 8-page structured story with images."""
        usage_log_id = uuid.uuid4()

        with (
            patch(
                "src.api.routes.books.CreditService.calculate_book_cost",
                new_callable=AsyncMock,
                return_value=Decimal("16.00"),
            ),
            patch(
                "src.api.routes.books.CreditService.get_pricing",
                new_callable=AsyncMock,
                return_value=_PRICING_SNAPSHOT,
            ),
            patch(
                "src.api.routes.books.CreditService.reserve",
                new_callable=AsyncMock,
                return_value=usage_log_id,
            ) as mock_reserve,
            patch(
                "src.api.routes.books.repo.create_book_job",
                new_callable=AsyncMock,
            ),
        ):
            resp = await client.post("/api/v1/books/generate", json=_VALID_BOOK_BODY)

            assert resp.status_code == 200
            mock_reserve.assert_called_once()
            call_kwargs = mock_reserve.call_args.kwargs
            assert call_kwargs["amount"] == Decimal("16.00")
            assert call_kwargs["job_type"] == "book"

    async def test_generate_book_cost_with_images(self, client):
        """calculate_book_cost is called with pages=8, with_images=True when generate_images=True."""
        usage_log_id = uuid.uuid4()

        with (
            patch(
                "src.api.routes.books.CreditService.calculate_book_cost",
                new_callable=AsyncMock,
                return_value=Decimal("16.00"),
            ) as mock_calc,
            patch(
                "src.api.routes.books.CreditService.get_pricing",
                new_callable=AsyncMock,
                return_value=_PRICING_SNAPSHOT,
            ),
            patch(
                "src.api.routes.books.CreditService.reserve",
                new_callable=AsyncMock,
                return_value=usage_log_id,
            ),
            patch(
                "src.api.routes.books.repo.create_book_job",
                new_callable=AsyncMock,
            ),
        ):
            resp = await client.post("/api/v1/books/generate", json=_VALID_BOOK_BODY)

            assert resp.status_code == 200
            mock_calc.assert_called_once()
            call_kwargs = mock_calc.call_args.kwargs
            assert call_kwargs["pages"] == 8
            assert call_kwargs["with_images"] is True

    async def test_generate_book_cost_without_images(self, client):
        """calculate_book_cost is called with pages=8, with_images=False when generate_images=False."""
        usage_log_id = uuid.uuid4()
        body = {**_VALID_BOOK_BODY, "generate_images": False}

        with (
            patch(
                "src.api.routes.books.CreditService.calculate_book_cost",
                new_callable=AsyncMock,
                return_value=Decimal("8.00"),
            ) as mock_calc,
            patch(
                "src.api.routes.books.CreditService.get_pricing",
                new_callable=AsyncMock,
                return_value=_PRICING_SNAPSHOT,
            ),
            patch(
                "src.api.routes.books.CreditService.reserve",
                new_callable=AsyncMock,
                return_value=usage_log_id,
            ),
            patch(
                "src.api.routes.books.repo.create_book_job",
                new_callable=AsyncMock,
            ),
        ):
            resp = await client.post("/api/v1/books/generate", json=body)

            assert resp.status_code == 200
            mock_calc.assert_called_once()
            call_kwargs = mock_calc.call_args.kwargs
            assert call_kwargs["pages"] == 8
            assert call_kwargs["with_images"] is False

    async def test_generate_book_returns_402_insufficient(self, client):
        """Returns 402 with correct detail when reserve raises InsufficientCreditsError."""
        with (
            patch(
                "src.api.routes.books.CreditService.calculate_book_cost",
                new_callable=AsyncMock,
                return_value=Decimal("16.00"),
            ),
            patch(
                "src.api.routes.books.CreditService.get_pricing",
                new_callable=AsyncMock,
                return_value=_PRICING_SNAPSHOT,
            ),
            patch(
                "src.api.routes.books.CreditService.reserve",
                new_callable=AsyncMock,
                side_effect=InsufficientCreditsError(
                    balance=Decimal("5.00"), required=Decimal("16.00"),
                ),
            ),
        ):
            resp = await client.post("/api/v1/books/generate", json=_VALID_BOOK_BODY)

            assert resp.status_code == 402
            detail = resp.json()["detail"]
            assert detail == {"message": "Insufficient credits", "required": 16.0}

    async def test_structured_pages_count_used(self, client):
        """When story_structured with 8 pages is provided, calculate_book_cost receives pages=8."""
        usage_log_id = uuid.uuid4()

        with (
            patch(
                "src.api.routes.books.CreditService.calculate_book_cost",
                new_callable=AsyncMock,
                return_value=Decimal("16.00"),
            ) as mock_calc,
            patch(
                "src.api.routes.books.CreditService.get_pricing",
                new_callable=AsyncMock,
                return_value=_PRICING_SNAPSHOT,
            ),
            patch(
                "src.api.routes.books.CreditService.reserve",
                new_callable=AsyncMock,
                return_value=usage_log_id,
            ),
            patch(
                "src.api.routes.books.repo.create_book_job",
                new_callable=AsyncMock,
            ),
        ):
            resp = await client.post("/api/v1/books/generate", json=_VALID_BOOK_BODY)

            assert resp.status_code == 200
            call_kwargs = mock_calc.call_args.kwargs
            assert call_kwargs["pages"] == 8

    async def test_raw_text_uses_text_processor_page_count(self, client):
        """When story_structured is absent, TextProcessor determines the page count (> 0)."""
        usage_log_id = uuid.uuid4()
        body_no_structured = {
            "story": "Once upon a time there was a little bunny. The bunny hopped around. The bunny found a carrot. The end.",
            "title": "Bunny Story",
            "generate_images": True,
        }

        with (
            patch(
                "src.api.routes.books.CreditService.calculate_book_cost",
                new_callable=AsyncMock,
                return_value=Decimal("4.00"),
            ) as mock_calc,
            patch(
                "src.api.routes.books.CreditService.get_pricing",
                new_callable=AsyncMock,
                return_value=_PRICING_SNAPSHOT,
            ),
            patch(
                "src.api.routes.books.CreditService.reserve",
                new_callable=AsyncMock,
                return_value=usage_log_id,
            ),
            patch(
                "src.api.routes.books.repo.create_book_job",
                new_callable=AsyncMock,
            ),
        ):
            resp = await client.post("/api/v1/books/generate", json=body_no_structured)

            assert resp.status_code == 200
            mock_calc.assert_called_once()
            call_kwargs = mock_calc.call_args.kwargs
            assert call_kwargs["pages"] > 0

    async def test_passes_usage_log_id_to_task(self, client):
        """The usage_log_id returned by reserve() is forwarded as the 5th positional arg to add_task."""
        usage_log_id = uuid.uuid4()

        with (
            patch(
                "src.api.routes.books.CreditService.calculate_book_cost",
                new_callable=AsyncMock,
                return_value=Decimal("16.00"),
            ),
            patch(
                "src.api.routes.books.CreditService.get_pricing",
                new_callable=AsyncMock,
                return_value=_PRICING_SNAPSHOT,
            ),
            patch(
                "src.api.routes.books.CreditService.reserve",
                new_callable=AsyncMock,
                return_value=usage_log_id,
            ),
            patch(
                "src.api.routes.books.repo.create_book_job",
                new_callable=AsyncMock,
            ),
            patch(
                "src.api.routes.books.BackgroundTasks.add_task",
            ) as mock_add_task,
        ):
            resp = await client.post("/api/v1/books/generate", json=_VALID_BOOK_BODY)

            assert resp.status_code == 200
            mock_add_task.assert_called_once()
            # add_task(generate_book_task, str(job_id), body, user_id, usage_log_id)
            positional_args = mock_add_task.call_args.args
            assert positional_args[4] == usage_log_id
