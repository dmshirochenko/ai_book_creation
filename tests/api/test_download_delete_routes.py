"""Tests for download and delete book endpoints (R2-backed)."""

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
_TEST_JOB_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _make_book_job(
    *,
    job_id=None,
    title="Test Book",
    status="completed",
    booklet_filename="test_booklet.pdf",
    review_filename="test_review.pdf",
):
    job = MagicMock()
    job.id = job_id or _TEST_JOB_ID
    job.title = title
    job.status = status
    job.booklet_filename = booklet_filename
    job.review_filename = review_filename
    job.created_at = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
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
        async with AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as c:
            yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests: download_book
# ---------------------------------------------------------------------------


class TestDownloadBook:
    """Tests for GET /api/v1/books/{job_id}/download/{pdf_type}."""

    async def test_booklet_redirects_to_presigned_url(self, client):
        job = _make_book_job()
        mock_storage = AsyncMock()
        mock_storage.generate_presigned_url = AsyncMock(
            return_value="https://r2.example.com/presigned-booklet"
        )

        with (
            patch(
                "src.api.routes.books.repo.get_book_job_for_user",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch("src.api.routes.books.get_storage", return_value=mock_storage),
        ):
            resp = await client.get(
                f"/api/v1/books/{_TEST_JOB_ID}/download/booklet"
            )
            assert resp.status_code == 307
            assert resp.headers["location"] == "https://r2.example.com/presigned-booklet"

    async def test_review_redirects_to_presigned_url(self, client):
        job = _make_book_job()
        mock_storage = AsyncMock()
        mock_storage.generate_presigned_url = AsyncMock(
            return_value="https://r2.example.com/presigned-review"
        )

        with (
            patch(
                "src.api.routes.books.repo.get_book_job_for_user",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch("src.api.routes.books.get_storage", return_value=mock_storage),
        ):
            resp = await client.get(
                f"/api/v1/books/{_TEST_JOB_ID}/download/review"
            )
            assert resp.status_code == 307
            assert resp.headers["location"] == "https://r2.example.com/presigned-review"

    async def test_presigned_url_includes_correct_r2_key(self, client):
        job = _make_book_job(booklet_filename="My_Book_booklet.pdf")
        mock_storage = AsyncMock()
        mock_storage.generate_presigned_url = AsyncMock(return_value="https://url")

        with (
            patch(
                "src.api.routes.books.repo.get_book_job_for_user",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch("src.api.routes.books.get_storage", return_value=mock_storage),
        ):
            await client.get(
                f"/api/v1/books/{_TEST_JOB_ID}/download/booklet"
            )
            call_args = mock_storage.generate_presigned_url.call_args
            r2_key = call_args.args[0]
            assert r2_key == f"pdfs/{_TEST_JOB_ID}/My_Book_booklet.pdf"
            assert call_args.kwargs["response_filename"] == "My_Book_booklet.pdf"

    async def test_job_not_found_returns_404(self, client):
        with patch(
            "src.api.routes.books.repo.get_book_job_for_user",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await client.get(
                f"/api/v1/books/{_TEST_JOB_ID}/download/booklet"
            )
            assert resp.status_code == 404

    async def test_job_not_completed_returns_400(self, client):
        job = _make_book_job(status="processing")
        with patch(
            "src.api.routes.books.repo.get_book_job_for_user",
            new_callable=AsyncMock,
            return_value=job,
        ):
            resp = await client.get(
                f"/api/v1/books/{_TEST_JOB_ID}/download/booklet"
            )
            assert resp.status_code == 400
            assert "not ready" in resp.json()["detail"].lower()

    async def test_invalid_pdf_type_returns_400(self, client):
        job = _make_book_job()
        with patch(
            "src.api.routes.books.repo.get_book_job_for_user",
            new_callable=AsyncMock,
            return_value=job,
        ):
            resp = await client.get(
                f"/api/v1/books/{_TEST_JOB_ID}/download/invalid"
            )
            assert resp.status_code == 400
            assert "Invalid pdf_type" in resp.json()["detail"]

    async def test_missing_filename_returns_404(self, client):
        job = _make_book_job(booklet_filename=None)
        with patch(
            "src.api.routes.books.repo.get_book_job_for_user",
            new_callable=AsyncMock,
            return_value=job,
        ):
            resp = await client.get(
                f"/api/v1/books/{_TEST_JOB_ID}/download/booklet"
            )
            assert resp.status_code == 404
            assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Tests: delete_job
# ---------------------------------------------------------------------------


class TestDeleteJob:
    """Tests for DELETE /api/v1/books/{job_id}."""

    async def test_deletes_r2_objects_and_db_row(self, client):
        job = _make_book_job()
        mock_storage = AsyncMock()
        mock_storage.delete_prefix = AsyncMock(return_value=3)
        mock_delete_job = AsyncMock()

        with (
            patch(
                "src.api.routes.books.repo.get_book_job_for_user",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch("src.api.routes.books.get_storage", return_value=mock_storage),
            patch(
                "src.api.routes.books.repo.delete_book_job",
                mock_delete_job,
            ),
        ):
            resp = await client.delete(f"/api/v1/books/{_TEST_JOB_ID}")
            assert resp.status_code == 200
            assert "deleted" in resp.json()["message"].lower()

            # Verify R2 prefixes were cleaned
            calls = mock_storage.delete_prefix.call_args_list
            prefixes = [c.args[0] for c in calls]
            assert f"images/{_TEST_JOB_ID}/" in prefixes
            assert f"pdfs/{_TEST_JOB_ID}/" in prefixes

            # Verify DB deletion
            mock_delete_job.assert_awaited_once()

    async def test_job_not_found_returns_404(self, client):
        with patch(
            "src.api.routes.books.repo.get_book_job_for_user",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await client.delete(f"/api/v1/books/{_TEST_JOB_ID}")
            assert resp.status_code == 404
