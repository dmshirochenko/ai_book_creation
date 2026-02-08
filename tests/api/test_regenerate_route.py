"""Tests for POST /api/v1/books/{job_id}/regenerate endpoint."""

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


def _make_failed_image(*, page_number=1, prompt="test prompt"):
    img = MagicMock()
    img.id = uuid.uuid4()
    img.page_number = page_number
    img.prompt = prompt
    img.retry_attempt = 0
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


class TestRegenerateBook:
    async def test_returns_202_with_failed_images(self, client):
        job_id = uuid.uuid4()
        job = _make_book_job(job_id=job_id, status="completed")
        failed_images = [
            _make_failed_image(page_number=2),
            _make_failed_image(page_number=5),
        ]

        with (
            patch(
                "src.api.routes.books.repo.get_book_job_for_user",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "src.api.routes.books.repo.get_failed_images_for_book",
                new_callable=AsyncMock,
                return_value=failed_images,
            ),
            patch(
                "src.api.routes.books.repo.update_book_job",
                new_callable=AsyncMock,
            ),
        ):
            resp = await client.post(f"/api/v1/books/{job_id}/regenerate")
            assert resp.status_code == 202
            data = resp.json()
            assert data["job_id"] == str(job_id)
            assert data["status"] == "pending"
            assert data["failed_image_count"] == 2

    async def test_404_for_nonexistent_job(self, client):
        job_id = uuid.uuid4()
        with patch(
            "src.api.routes.books.repo.get_book_job_for_user",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await client.post(f"/api/v1/books/{job_id}/regenerate")
            assert resp.status_code == 404

    async def test_400_for_pending_job(self, client):
        job_id = uuid.uuid4()
        job = _make_book_job(job_id=job_id, status="pending")
        with patch(
            "src.api.routes.books.repo.get_book_job_for_user",
            new_callable=AsyncMock,
            return_value=job,
        ):
            resp = await client.post(f"/api/v1/books/{job_id}/regenerate")
            assert resp.status_code == 400

    async def test_400_for_processing_job(self, client):
        job_id = uuid.uuid4()
        job = _make_book_job(job_id=job_id, status="processing")
        with patch(
            "src.api.routes.books.repo.get_book_job_for_user",
            new_callable=AsyncMock,
            return_value=job,
        ):
            resp = await client.post(f"/api/v1/books/{job_id}/regenerate")
            assert resp.status_code == 400

    async def test_200_when_no_failed_images(self, client):
        job_id = uuid.uuid4()
        job = _make_book_job(job_id=job_id, status="completed")
        with (
            patch(
                "src.api.routes.books.repo.get_book_job_for_user",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "src.api.routes.books.repo.get_failed_images_for_book",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            resp = await client.post(f"/api/v1/books/{job_id}/regenerate")
            assert resp.status_code == 200
            data = resp.json()
            assert data["failed_image_count"] == 0
            assert "no failed images" in data["message"].lower()
