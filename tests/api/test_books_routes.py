"""Tests for the GET /api/v1/books/generated endpoint."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from src.api.app import app
from src.api.deps import get_db, get_current_user_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_book_job(*, job_id=None, title="Test Book", status="completed"):
    """Return a mock BookJob row."""
    job = MagicMock()
    job.id = job_id or uuid.uuid4()
    job.title = title
    job.status = status
    job.created_at = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    job.booklet_filename = "test_booklet.pdf"
    job.review_filename = "test_review.pdf"
    return job


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

    with (
        patch("src.api.app.init_db", new_callable=AsyncMock),
        patch("src.api.app.close_db", new_callable=AsyncMock),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestListGeneratedBooks:
    """Tests for GET /api/v1/books/generated."""

    async def test_returns_completed_books(self, client):
        job = _make_book_job()
        with patch(
            "src.api.routes.books.repo.list_completed_books_for_user",
            new_callable=AsyncMock,
            return_value=[job],
        ), patch(
            "src.api.routes.books.repo.count_completed_books_for_user",
            new_callable=AsyncMock,
            return_value=1,
        ):
            resp = await client.get("/api/v1/books/generated")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            book = data["books"][0]
            assert book["job_id"] == str(job.id)
            assert book["title"] == "Test Book"
            assert "booklet" in book["booklet_url"]
            assert "review" in book["review_url"]
            assert book["created_at"] == "2024-06-15T12:00:00+00:00"

    async def test_empty_list(self, client):
        with patch(
            "src.api.routes.books.repo.list_completed_books_for_user",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "src.api.routes.books.repo.count_completed_books_for_user",
            new_callable=AsyncMock,
            return_value=0,
        ):
            resp = await client.get("/api/v1/books/generated")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 0
            assert data["books"] == []

    async def test_multiple_books(self, client):
        jobs = [
            _make_book_job(title="Book A"),
            _make_book_job(title="Book B"),
            _make_book_job(title="Book C"),
        ]
        with patch(
            "src.api.routes.books.repo.list_completed_books_for_user",
            new_callable=AsyncMock,
            return_value=jobs,
        ), patch(
            "src.api.routes.books.repo.count_completed_books_for_user",
            new_callable=AsyncMock,
            return_value=3,
        ):
            resp = await client.get("/api/v1/books/generated")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 3
            titles = [b["title"] for b in data["books"]]
            assert titles == ["Book A", "Book B", "Book C"]

    async def test_untitled_book_defaults(self, client):
        job = _make_book_job(title=None)
        with patch(
            "src.api.routes.books.repo.list_completed_books_for_user",
            new_callable=AsyncMock,
            return_value=[job],
        ), patch(
            "src.api.routes.books.repo.count_completed_books_for_user",
            new_callable=AsyncMock,
            return_value=1,
        ):
            resp = await client.get("/api/v1/books/generated")
            assert resp.status_code == 200
            assert resp.json()["books"][0]["title"] == "Untitled"

    async def test_download_urls_format(self, client):
        job_id = uuid.uuid4()
        job = _make_book_job(job_id=job_id)
        with patch(
            "src.api.routes.books.repo.list_completed_books_for_user",
            new_callable=AsyncMock,
            return_value=[job],
        ), patch(
            "src.api.routes.books.repo.count_completed_books_for_user",
            new_callable=AsyncMock,
            return_value=1,
        ):
            resp = await client.get("/api/v1/books/generated")
            book = resp.json()["books"][0]
            assert book["booklet_url"] == f"/api/v1/books/{job_id}/download/booklet"
            assert book["review_url"] == f"/api/v1/books/{job_id}/download/review"

    async def test_pagination_params_forwarded(self, client):
        mock_fn = AsyncMock(return_value=[])
        with patch(
            "src.api.routes.books.repo.list_completed_books_for_user",
            mock_fn,
        ), patch(
            "src.api.routes.books.repo.count_completed_books_for_user",
            new_callable=AsyncMock,
            return_value=0,
        ):
            await client.get(
                "/api/v1/books/generated", params={"limit": 10, "offset": 5}
            )
            mock_fn.assert_awaited_once()
            _, kwargs = mock_fn.call_args
            assert kwargs["limit"] == 10
            assert kwargs["offset"] == 5
