"""Integration tests for src/core/image_generator.py (mocked HTTP)."""

import json
import base64
import hashlib
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

import httpx

from src.core.config import BookConfig
from src.core.image_generator import (
    ImageConfig,
    ImagePromptBuilder,
    OpenRouterImageGenerator,
    BookImageGenerator,
    GeneratedImage,
)
from src.core.prompts import StoryVisualContext, Character


# Minimal valid 1x1 PNG for testing
MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
)
MINIMAL_PNG_B64 = base64.b64encode(MINIMAL_PNG).decode()


# =============================================================================
# ImageConfig
# =============================================================================


class TestImageConfig:
    def test_validate_with_key(self):
        config = ImageConfig(api_key="test-key")
        assert config.validate() is True

    def test_validate_without_key(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        config = ImageConfig(api_key="")
        assert config.validate() is False

    def test_get_api_key(self):
        config = ImageConfig(api_key="my-key")
        assert config.get_api_key() == "my-key"


# =============================================================================
# ImagePromptBuilder
# =============================================================================


class TestImagePromptBuilder:
    def test_cover_prompt(self):
        builder = ImagePromptBuilder(
            style="watercolor", book_title="My Book", target_age=(2, 4)
        )
        prompt = builder.build_prompt(
            page_text="Once upon a time",
            page_number=1,
            total_pages=8,
            is_cover=True,
        )
        assert "cover" in prompt.lower()
        assert "My Book" in prompt

    def test_end_prompt(self):
        builder = ImagePromptBuilder(
            style="watercolor", book_title="My Book", target_age=(2, 4)
        )
        prompt = builder.build_prompt(
            page_text="The End",
            page_number=8,
            total_pages=8,
            is_end=True,
        )
        assert "end" in prompt.lower() or "concluding" in prompt.lower()

    def test_content_prompt(self):
        builder = ImagePromptBuilder(
            style="watercolor", book_title="My Book", target_age=(2, 4)
        )
        prompt = builder.build_prompt(
            page_text="The fox ran.",
            page_number=3,
            total_pages=8,
        )
        assert "The fox ran." in prompt

    def test_with_visual_context(self, sample_visual_context):
        builder = ImagePromptBuilder(
            style="watercolor",
            book_title="My Book",
            target_age=(2, 4),
            visual_context=sample_visual_context,
        )
        prompt = builder.build_prompt(
            page_text="Text",
            page_number=2,
            total_pages=8,
        )
        assert "Ruby" in prompt


# =============================================================================
# OpenRouterImageGenerator
# =============================================================================


class TestOpenRouterImageGenerator:
    async def test_successful_generation(self):
        config = ImageConfig(api_key="test-key")
        gen = OpenRouterImageGenerator(config)

        response_data = {
            "choices": [{
                "message": {
                    "images": [{
                        "image_url": {
                            "url": f"data:image/png;base64,{MINIMAL_PNG_B64}"
                        }
                    }]
                }
            }]
        }
        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        with patch("src.core.image_generator.httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_instance

            result = await gen.generate("test prompt")
            assert result.success is True
            assert result.image_data is not None
            assert len(result.image_data) > 0

    async def test_no_image_in_response(self):
        config = ImageConfig(api_key="test-key")
        gen = OpenRouterImageGenerator(config)

        response_data = {"choices": [{"message": {}}]}
        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        with patch("src.core.image_generator.httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_instance

            result = await gen.generate("test prompt")
            assert result.success is False

    async def test_http_error(self):
        config = ImageConfig(api_key="test-key")
        gen = OpenRouterImageGenerator(config)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=mock_response
        )

        with patch("src.core.image_generator.httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_instance

            result = await gen.generate("test prompt")
            assert result.success is False
            assert "API error" in result.error


# =============================================================================
# BookImageGenerator
# =============================================================================


class TestBookImageGenerator:
    def test_prompt_hash_deterministic(self):
        h1 = BookImageGenerator.compute_prompt_hash("same prompt")
        h2 = BookImageGenerator.compute_prompt_hash("same prompt")
        assert h1 == h2

    def test_prompt_hash_different_for_different_prompts(self):
        h1 = BookImageGenerator.compute_prompt_hash("prompt A")
        h2 = BookImageGenerator.compute_prompt_hash("prompt B")
        assert h1 != h2

    async def test_check_cache_hit(self):
        """Cache hit: cache_check_fn returns a row, storage downloads and re-uploads."""
        config = ImageConfig(api_key="test", use_cache=True)

        mock_storage = AsyncMock()
        mock_storage.download_bytes = AsyncMock(return_value=MINIMAL_PNG)
        mock_storage.upload_bytes = AsyncMock()

        cached_row = MagicMock()
        cached_row.r2_key = "images/old-job/page_1.png"

        async def cache_fn(prompt_hash):
            return cached_row

        gen = BookImageGenerator(
            config,
            storage=mock_storage,
            book_job_id="new-job",
            cache_check_fn=cache_fn,
        )
        result = await gen._check_cache("test prompt", page_number=1)
        assert result is not None
        assert result.success is True
        assert result.cached is True
        assert result.image_data == MINIMAL_PNG
        mock_storage.upload_bytes.assert_called_once()

    async def test_check_cache_miss(self):
        """Cache miss: cache_check_fn returns None."""
        config = ImageConfig(api_key="test", use_cache=True)
        mock_storage = AsyncMock()

        async def cache_fn(prompt_hash):
            return None

        gen = BookImageGenerator(
            config,
            storage=mock_storage,
            book_job_id="job-id",
            cache_check_fn=cache_fn,
        )
        result = await gen._check_cache("test prompt", page_number=1)
        assert result is None

    async def test_check_cache_disabled(self):
        """Cache disabled: _check_cache returns None immediately."""
        config = ImageConfig(api_key="test", use_cache=False)
        gen = BookImageGenerator(config)
        result = await gen._check_cache("test prompt", page_number=1)
        assert result is None

    def test_set_visual_context(self, sample_visual_context):
        config = ImageConfig(api_key="test")
        gen = BookImageGenerator(config)
        assert gen.visual_context is None
        gen.set_visual_context(sample_visual_context)
        assert gen.visual_context is sample_visual_context

    async def test_generate_all_images_skips_blank(self):
        config = ImageConfig(api_key="test", use_cache=False)
        gen = BookImageGenerator(config)

        # Mock the generator to return success
        mock_result = GeneratedImage(success=True, image_data=MINIMAL_PNG)
        gen.generator = AsyncMock()
        gen.generator.generate = AsyncMock(return_value=mock_result)

        pages = [
            {"page_number": 1, "content": "Cover", "page_type": "cover"},
            {"page_number": 2, "content": "Text", "page_type": "content"},
            {"page_number": 3, "content": "", "page_type": "blank"},
        ]
        results = await gen.generate_all_images(pages)
        # Blank page should be skipped
        assert 3 not in results
        assert 1 in results
        assert 2 in results
