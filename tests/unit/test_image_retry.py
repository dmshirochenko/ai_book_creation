"""Tests for image generation retry behavior."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.core.image_generator import (
    ImageConfig,
    BookImageGenerator,
    OpenRouterImageGenerator,
    GeneratedImage,
    ImageGenerationError,
)


@pytest.fixture
def image_config():
    return ImageConfig(api_key="test-key", use_cache=False)


class TestImageGenerationRetry:
    """Verify that image generation retries on transient failures."""

    async def test_succeeds_after_transient_failure(self, image_config):
        """Image generation should retry and succeed after a transient error."""
        gen = OpenRouterImageGenerator(image_config)

        call_count = 0

        async def flaky_generate(prompt):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return GeneratedImage(success=False, error="API error: 503")
            return GeneratedImage(
                success=True, image_data=b"png-data", prompt_used=prompt
            )

        from src.api.schemas import BookGenerateRequest

        book_gen = BookImageGenerator(
            config=image_config,
            book_config=BookGenerateRequest(story="test"),
        )
        book_gen.generator = MagicMock()
        book_gen.generator.generate = AsyncMock(side_effect=flaky_generate)

        result = await book_gen.generate_image(
            page_text="A bunny hops.",
            page_number=1,
            total_pages=3,
        )
        assert result.success is True
        assert call_count == 2

    async def test_returns_failed_after_all_retries_exhausted(self, image_config):
        """After max retries, generate_image should return a failed GeneratedImage."""
        from src.api.schemas import BookGenerateRequest

        book_gen = BookImageGenerator(
            config=image_config,
            book_config=BookGenerateRequest(story="test"),
        )
        book_gen.generator = MagicMock()
        book_gen.generator.generate = AsyncMock(
            return_value=GeneratedImage(success=False, error="API error: 500")
        )

        result = await book_gen.generate_image(
            page_text="A bunny hops.",
            page_number=1,
            total_pages=3,
        )
        assert result.success is False
        assert result.error is not None
        # 3 total attempts (1 initial + 2 retries)
        assert book_gen.generator.generate.call_count == 3

    async def test_no_retry_on_success(self, image_config):
        """Successful generation on first try should not retry."""
        from src.api.schemas import BookGenerateRequest

        book_gen = BookImageGenerator(
            config=image_config,
            book_config=BookGenerateRequest(story="test"),
        )
        book_gen.generator = MagicMock()
        book_gen.generator.generate = AsyncMock(
            return_value=GeneratedImage(
                success=True, image_data=b"png-data", prompt_used="prompt"
            )
        )

        result = await book_gen.generate_image(
            page_text="A bunny hops.",
            page_number=1,
            total_pages=3,
        )
        assert result.success is True
        assert book_gen.generator.generate.call_count == 1
