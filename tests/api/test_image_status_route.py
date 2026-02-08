"""Tests for GET /api/v1/books/{job_id}/images/status endpoint."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from src.api.app import app
from src.api.deps import get_db, get_current_user_id


_TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_book_job(*, job_id=None, status="completed"):
    job = MagicMock()
    job.id = job_id or uuid.uuid4()
    job.status = status
    job.user_id = _TEST_USER_ID
    return job


def _make_image(*, page_number=1, status="completed", error=None):
    img = MagicMock()
    img.id = uuid.uuid4()
    img.page_number = page_number
    img.status = status
    img.error = error
    return img


@pytest.fixture
async def client():
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


class TestGetImageStatus:
    async def test_returns_failed_images_detail(self, client):
        job_id = uuid.uuid4()
        job = _make_book_job(job_id=job_id, status="completed")
        all_images = [
            _make_image(page_number=1, status="completed"),
            _make_image(page_number=2, status="failed", error="API error: 503"),
            _make_image(page_number=3, status="completed"),
            _make_image(page_number=4, status="failed", error="timeout"),
        ]
        failed_images = [img for img in all_images if img.status == "failed"]

        with (
            patch(
                "src.api.routes.books.repo.get_book_job_for_user",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "src.api.routes.books.repo.get_images_for_book",
                new_callable=AsyncMock,
                return_value=all_images,
            ),
            patch(
                "src.api.routes.books.repo.get_failed_images_for_book",
                new_callable=AsyncMock,
                return_value=failed_images,
            ),
        ):
            resp = await client.get(f"/api/v1/books/{job_id}/images/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["job_id"] == str(job_id)
            assert data["total_images"] == 4
            assert data["failed_images"] == 2
            assert data["has_failed_images"] is True
            assert len(data["failed_pages"]) == 2
            assert data["failed_pages"][0]["page_number"] == 2
            assert data["failed_pages"][0]["error"] == "API error: 503"
            assert data["failed_pages"][1]["page_number"] == 4
            assert data["failed_pages"][1]["error"] == "timeout"

    async def test_returns_no_failed_images(self, client):
        job_id = uuid.uuid4()
        job = _make_book_job(job_id=job_id, status="completed")
        all_images = [
            _make_image(page_number=1, status="completed"),
            _make_image(page_number=2, status="completed"),
        ]

        with (
            patch(
                "src.api.routes.books.repo.get_book_job_for_user",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "src.api.routes.books.repo.get_images_for_book",
                new_callable=AsyncMock,
                return_value=all_images,
            ),
            patch(
                "src.api.routes.books.repo.get_failed_images_for_book",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            resp = await client.get(f"/api/v1/books/{job_id}/images/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_images"] == 2
            assert data["failed_images"] == 0
            assert data["has_failed_images"] is False
            assert data["failed_pages"] == []

    async def test_404_for_nonexistent_job(self, client):
        job_id = uuid.uuid4()
        with patch(
            "src.api.routes.books.repo.get_book_job_for_user",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await client.get(f"/api/v1/books/{job_id}/images/status")
            assert resp.status_code == 404

    async def test_400_for_pending_job(self, client):
        job_id = uuid.uuid4()
        job = _make_book_job(job_id=job_id, status="pending")
        with patch(
            "src.api.routes.books.repo.get_book_job_for_user",
            new_callable=AsyncMock,
            return_value=job,
        ):
            resp = await client.get(f"/api/v1/books/{job_id}/images/status")
            assert resp.status_code == 400

    async def test_400_for_processing_job(self, client):
        job_id = uuid.uuid4()
        job = _make_book_job(job_id=job_id, status="processing")
        with patch(
            "src.api.routes.books.repo.get_book_job_for_user",
            new_callable=AsyncMock,
            return_value=job,
        ):
            resp = await client.get(f"/api/v1/books/{job_id}/images/status")
            assert resp.status_code == 400

    async def test_works_for_failed_job(self, client):
        """A failed job should still allow checking image status."""
        job_id = uuid.uuid4()
        job = _make_book_job(job_id=job_id, status="failed")
        all_images = [
            _make_image(page_number=1, status="failed", error="generation failed"),
        ]

        with (
            patch(
                "src.api.routes.books.repo.get_book_job_for_user",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "src.api.routes.books.repo.get_images_for_book",
                new_callable=AsyncMock,
                return_value=all_images,
            ),
            patch(
                "src.api.routes.books.repo.get_failed_images_for_book",
                new_callable=AsyncMock,
                return_value=all_images,
            ),
        ):
            resp = await client.get(f"/api/v1/books/{job_id}/images/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["has_failed_images"] is True
