"""Tests for image model selection during regeneration."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.image_generator import ImageConfig as RealImageConfig
from src.tasks.book_tasks import _regenerate_book_inner


_TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_TEST_JOB_ID = "00000000-0000-0000-0000-000000000099"


def _mock_session_factory():
    session = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock()
    factory.return_value = ctx
    return factory, session


def _make_failed_image(page_number: int, image_model: str | None = None):
    img = MagicMock()
    img.id = uuid.uuid4()
    img.page_number = page_number
    img.prompt = f"A bunny on page {page_number}"
    img.retry_attempt = 0
    img.image_model = image_model
    return img


class TestRegenerationUsesPerImageModel:
    @pytest.mark.asyncio
    async def test_uses_model_from_image_row(self):
        """Regeneration should use img.image_model, not the default."""
        failed_img = _make_failed_image(1, image_model="openai/gpt-4o")
        factory, session = _mock_session_factory()
        storage = AsyncMock()
        storage.upload_bytes = AsyncMock()
        storage.download_bytes = AsyncMock(return_value=b"fake-image")
        storage.delete = AsyncMock()
        storage.upload_file = AsyncMock(return_value=1024)

        # Mock the job for PDF regeneration
        mock_job = MagicMock()
        mock_job.request_params = {
            "story": "A bunny hops.",
            "title": "Test",
            "generate_images": True,
            "image_model": "openai/gpt-4o",
        }

        # Success result from generator
        gen_result = MagicMock()
        gen_result.success = True
        gen_result.image_data = b"fake-image-data"
        gen_result.error = None

        mock_generator = AsyncMock()
        mock_generator.generate = AsyncMock(return_value=gen_result)
        mock_generator.close = AsyncMock()

        # Capture the model passed to ImageConfig
        captured_models = []

        def capture_image_config(*args, **kwargs):
            config = RealImageConfig(*args, **kwargs)
            captured_models.append(config.model)
            return config

        with (
            patch("src.tasks.book_tasks.repo.update_book_job", new_callable=AsyncMock),
            patch("src.tasks.book_tasks.repo.reset_image_for_retry", new_callable=AsyncMock),
            patch("src.tasks.book_tasks.repo.update_generated_image", new_callable=AsyncMock),
            patch("src.tasks.book_tasks.repo.get_book_job", new_callable=AsyncMock, return_value=mock_job),
            patch("src.tasks.book_tasks.repo.get_images_for_book", new_callable=AsyncMock, return_value=[]),
            patch("src.tasks.book_tasks.repo.delete_pdfs_for_book", new_callable=AsyncMock, return_value=[]),
            patch("src.tasks.book_tasks.repo.create_generated_pdf", new_callable=AsyncMock),
            patch("src.tasks.book_tasks.generate_both_pdfs"),
            patch(
                "src.core.image_generator.ImageConfig",
                side_effect=capture_image_config,
            ),
            patch(
                "src.core.image_generator.OpenRouterImageGenerator",
                return_value=mock_generator,
            ),
        ):
            await _regenerate_book_inner(
                _TEST_JOB_ID, [failed_img], _TEST_USER_ID,
                session, factory, storage,
            )

        assert len(captured_models) >= 1
        assert captured_models[0] == "openai/gpt-4o"

    @pytest.mark.asyncio
    async def test_falls_back_to_default_when_image_model_is_none(self):
        """Old images with NULL image_model should use DEFAULT_IMAGE_MODEL."""
        failed_img = _make_failed_image(1, image_model=None)
        factory, session = _mock_session_factory()
        storage = AsyncMock()
        storage.upload_bytes = AsyncMock()
        storage.download_bytes = AsyncMock(return_value=b"fake-image")
        storage.delete = AsyncMock()
        storage.upload_file = AsyncMock(return_value=1024)

        mock_job = MagicMock()
        mock_job.request_params = {
            "story": "A bunny hops.",
            "title": "Test",
            "generate_images": True,
        }

        gen_result = MagicMock()
        gen_result.success = True
        gen_result.image_data = b"fake-image-data"
        gen_result.error = None

        mock_generator = AsyncMock()
        mock_generator.generate = AsyncMock(return_value=gen_result)
        mock_generator.close = AsyncMock()

        captured_models = []

        def capture_image_config(*args, **kwargs):
            config = RealImageConfig(*args, **kwargs)
            captured_models.append(config.model)
            return config

        with (
            patch("src.tasks.book_tasks.repo.update_book_job", new_callable=AsyncMock),
            patch("src.tasks.book_tasks.repo.reset_image_for_retry", new_callable=AsyncMock),
            patch("src.tasks.book_tasks.repo.update_generated_image", new_callable=AsyncMock),
            patch("src.tasks.book_tasks.repo.get_book_job", new_callable=AsyncMock, return_value=mock_job),
            patch("src.tasks.book_tasks.repo.get_images_for_book", new_callable=AsyncMock, return_value=[]),
            patch("src.tasks.book_tasks.repo.delete_pdfs_for_book", new_callable=AsyncMock, return_value=[]),
            patch("src.tasks.book_tasks.repo.create_generated_pdf", new_callable=AsyncMock),
            patch("src.tasks.book_tasks.generate_both_pdfs"),
            patch(
                "src.core.image_generator.ImageConfig",
                side_effect=capture_image_config,
            ),
            patch(
                "src.core.image_generator.OpenRouterImageGenerator",
                return_value=mock_generator,
            ),
        ):
            await _regenerate_book_inner(
                _TEST_JOB_ID, [failed_img], _TEST_USER_ID,
                session, factory, storage,
            )

        from src.core.config import DEFAULT_IMAGE_MODEL
        assert len(captured_models) >= 1
        assert captured_models[0] == DEFAULT_IMAGE_MODEL
