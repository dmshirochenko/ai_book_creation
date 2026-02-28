"""
Image Generator for Children's Book Pages.

This module handles AI image generation for each page of the book
using OpenRouter API.
"""

from __future__ import annotations

import io
import os
import asyncio
import httpx
import base64
import hashlib
import logging
from typing import Optional, List, Dict, Any, Callable, Awaitable, TYPE_CHECKING

from PIL import Image
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

from src.core.config import DEFAULT_IMAGE_MODEL
from src.core.retry import async_retry

if TYPE_CHECKING:
    from src.api.schemas import BookGenerateRequest
from src.core.prompts import (
    build_cover_image_prompt,
    build_end_page_image_prompt,
    build_content_page_image_prompt,
    StoryVisualContext,
)


class ImageGenerationError(Exception):
    """Raised when a single image generation attempt fails."""
    pass


@dataclass
class ImageConfig:
    """Configuration for image generation via OpenRouter."""

    api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    base_url: str = "https://openrouter.ai/api/v1/chat/completions"

    # Model settings - use a model that supports image output
    model: str = DEFAULT_IMAGE_MODEL  # OpenRouter image-capable model

    # Common settings
    image_style: str = "children's book illustration, soft watercolor style, gentle colors, simple shapes, cute and friendly"
    cache_dir: str = "image_cache"
    use_cache: bool = True
    text_on_image: bool = False  # If True, ask LLM to render text on the image

    def validate(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key or os.getenv("OPENROUTER_API_KEY", ""))

    def get_api_key(self) -> str:
        """Get the API key."""
        return self.api_key or os.getenv("OPENROUTER_API_KEY", "")


@dataclass
class GeneratedImage:
    """Result of image generation."""
    success: bool
    image_path: Optional[str] = None
    image_data: Optional[bytes] = None
    error: Optional[str] = None
    prompt_used: Optional[str] = None
    cached: bool = False


class ImagePromptBuilder:
    """Build effective prompts for children's book illustrations."""

    def __init__(
        self,
        style: str,
        book_title: str,
        target_age: tuple = (2, 4),
        text_on_image: bool = False,
        visual_context: Optional[StoryVisualContext] = None
    ):
        self.style = style
        self.book_title = book_title
        self.target_age = target_age
        self.text_on_image = text_on_image
        self.visual_context = visual_context

    def build_prompt(
        self,
        page_text: str,
        page_number: int,
        total_pages: int,
        story_context: str = "",
        is_cover: bool = False,
        is_end: bool = False
    ) -> str:
        """
        Build an image generation prompt for a specific page.

        Args:
            page_text: The text content of this page
            page_number: Current page number
            total_pages: Total number of pages
            story_context: Brief summary of the overall story
            is_cover: Whether this is the cover page
            is_end: Whether this is the end page
        """
        if is_cover:
            return build_cover_image_prompt(
                style=self.style,
                book_title=self.book_title,
                story_summary=story_context if story_context else page_text,
                target_age=self.target_age,
                text_on_image=self.text_on_image,
                visual_context=self.visual_context
            )
        elif is_end:
            return build_end_page_image_prompt(
                style=self.style,
                story_context=story_context,
                target_age=self.target_age,
                text_on_image=self.text_on_image,
                page_text=page_text,
                visual_context=self.visual_context
            )
        else:
            return build_content_page_image_prompt(
                style=self.style,
                page_text=page_text,
                page_number=page_number,
                story_context=story_context if story_context else self.book_title,
                target_age=self.target_age,
                text_on_image=self.text_on_image,
                visual_context=self.visual_context
            )


def _normalize_image_bytes(raw: bytes) -> bytes:
    """Validate image bytes with PIL and re-encode as PNG.

    AI models may return WebP, JPEG, or other formats regardless of what the
    data-URL header claims.  Re-encoding through PIL guarantees that
    downstream consumers (reportlab / ImageReader) always receive a valid PNG.
    """
    img = Image.open(io.BytesIO(raw))
    img.load()  # force full decode — raises early on corrupt data
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class OpenRouterImageGenerator:
    """Generate images using OpenRouter API with chat completions endpoint.

    Reuses a single httpx.AsyncClient across all requests to avoid
    TCP+TLS handshake overhead per image (~100ms each).
    Call ``close()`` when done generating images.
    """

    def __init__(self, config: ImageConfig):
        self.config = config
        self.headers = {
            "Authorization": f"Bearer {config.get_api_key()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/book-generator",
            "X-Title": "Children's Book Generator"
        }
        self._client = httpx.AsyncClient(timeout=120.0)
        self._closed = False

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        self._closed = True
        await self._client.aclose()

    async def generate(self, prompt: str) -> GeneratedImage:
        """Generate an image from prompt using chat completions with image modality."""
        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "user",
                    "content": f"Generate an image: {prompt}"
                }
            ],
            "modalities": ["image"],
            # Request portrait aspect ratio for A5 page format
            "image_generation": {
                "aspect_ratio": "3:4"  # Close to A5 (1:1.41), minimizes white space
            }
        }

        if self._closed:
            return GeneratedImage(
                success=False,
                error="HTTP client has been closed; create a new OpenRouterImageGenerator",
            )

        try:
            response = await self._client.post(
                self.config.base_url,
                headers=self.headers,
                json=payload
            )
            response.raise_for_status()

            data = response.json()

            # Extract image from the response
            if data.get("choices"):
                message = data["choices"][0].get("message", {})
                images = message.get("images", [])

                if images:
                    # Get the first image's base64 data URL
                    image_url = images[0].get("image_url", {}).get("url", "")

                    if image_url and "," in image_url:
                        # Parse data URL: "data:image/png;base64,ENCODED_DATA"
                        header, encoded = image_url.split(",", 1)
                        image_bytes = base64.b64decode(encoded)

                        # Validate & re-encode as PNG so reportlab can always read it
                        try:
                            image_bytes = _normalize_image_bytes(image_bytes)
                        except Exception as e:
                            logger.error(f"Image validation failed: {e}")
                            return GeneratedImage(
                                success=False,
                                error=f"Image validation failed: {e}",
                            )

                        return GeneratedImage(
                            success=True,
                            image_data=image_bytes,
                            prompt_used=prompt
                        )
                    else:
                        logger.warning(f"Invalid image URL format: {image_url[:100] if image_url else 'empty'}")

            msg_keys = list(data["choices"][0].get("message", {}).keys()) if data.get("choices") else "N/A"
            logger.warning(f"No image in response. Message keys: {msg_keys}")
            return GeneratedImage(
                success=False,
                error="No image in response"
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"API HTTP error: {e.response.status_code} - {e.response.text[:500]}")
            return GeneratedImage(
                success=False,
                error=f"API error: {e.response.status_code} - {e.response.text}"
            )
        except Exception as e:
            logger.error(f"Request exception: {str(e)}", exc_info=True)
            return GeneratedImage(
                success=False,
                error=f"Request failed: {str(e)}"
            )


class BookImageGenerator:
    """
    Main class for generating all images for a children's book.
    Handles R2 storage and DB-backed caching of generated images.
    """

    def __init__(
        self,
        config: ImageConfig,
        book_config: Optional[BookGenerateRequest] = None,
        visual_context: Optional[StoryVisualContext] = None,
        storage: Optional[Any] = None,
        book_job_id: Optional[str] = None,
        cache_check_fn: Optional[Callable[[str], Awaitable[Any]]] = None,
    ):
        self.config = config
        if book_config is None:
            from src.api.schemas import BookGenerateRequest as _BGReq
            book_config = _BGReq(story="")
        self.book_config = book_config
        self.visual_context = visual_context
        self.storage = storage
        self.book_job_id = book_job_id
        self.cache_check_fn = cache_check_fn
        self.generator = OpenRouterImageGenerator(config)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        await self.generator.close()

    def set_visual_context(self, visual_context: StoryVisualContext) -> None:
        """Set the visual context for consistent illustrations."""
        self.visual_context = visual_context

    @staticmethod
    def compute_prompt_hash(prompt: str) -> str:
        """Compute MD5 hash of a prompt for cache lookup."""
        return hashlib.md5(prompt.encode()).hexdigest()

    async def _check_cache(self, prompt: str, page_number: int) -> Optional[GeneratedImage]:
        """Check DB + R2 for a cached image with the same prompt hash.

        Returns the cached image data (needed for PDF generation) and
        reuses the existing R2 key to avoid a redundant re-upload.
        On any error, returns None (treat as cache miss).
        """
        if not self.config.use_cache or not self.cache_check_fn or not self.storage:
            return None

        try:
            prompt_hash = self.compute_prompt_hash(prompt)
            cached_row = await self.cache_check_fn(prompt_hash)
            if cached_row is None or not cached_row.r2_key:
                return None

            # Download cached image (needed for PDF generation)
            image_data = await self.storage.download_bytes(cached_row.r2_key)
            if image_data is None:
                return None

            # Reuse existing R2 key — skip redundant re-upload
            return GeneratedImage(
                success=True,
                image_path=cached_row.r2_key,
                image_data=image_data,
                prompt_used=prompt,
                cached=True,
            )
        except Exception as e:
            logger.warning(f"Cache check failed for page {page_number}, will regenerate: {e}")
            return None

    async def _upload_image(self, image_data: bytes, page_number: int) -> Optional[str]:
        """Upload image bytes to R2 and return the R2 key.

        Returns None on failure (image_data is still usable in memory for PDF).
        """
        key = f"images/{self.book_job_id}/page_{page_number}.png"
        try:
            await self.storage.upload_bytes(image_data, key, "image/png")
            return key
        except Exception as e:
            logger.error(f"R2 upload failed for page {page_number}: {e}")
            return None

    @async_retry(max_attempts=3, backoff_base=2.0)
    async def _generate_with_retry(self, prompt: str) -> GeneratedImage:
        """Generate a single image, raising on failure so @async_retry can retry."""
        result = await self.generator.generate(prompt)
        if not result.success:
            raise ImageGenerationError(result.error or "Unknown image generation error")
        return result

    def _build_page_prompt(
        self,
        page_text: str,
        page_number: int,
        total_pages: int,
        story_context: str = "",
        is_cover: bool = False,
        is_end: bool = False,
    ) -> str:
        """Build an image-generation prompt for a single page."""
        builder = ImagePromptBuilder(
            style=self.config.image_style,
            book_title=self.book_config.title or "Story Book",
            target_age=(self.book_config.age_min, self.book_config.age_max),
            text_on_image=self.config.text_on_image,
            visual_context=self.visual_context,
        )
        return builder.build_prompt(
            page_text=page_text,
            page_number=page_number,
            total_pages=total_pages,
            story_context=story_context,
            is_cover=is_cover,
            is_end=is_end,
        )

    async def generate_image(
        self,
        page_text: str,
        page_number: int,
        total_pages: int,
        story_context: str = "",
        is_cover: bool = False,
        is_end: bool = False
    ) -> GeneratedImage:
        """Generate an image for a single page."""
        prompt = self._build_page_prompt(
            page_text=page_text,
            page_number=page_number,
            total_pages=total_pages,
            story_context=story_context,
            is_cover=is_cover,
            is_end=is_end,
        )

        # Check cache (DB + R2)
        cached = await self._check_cache(prompt, page_number)
        if cached:
            return cached

        # Generate new image (with automatic retry)
        try:
            result = await self._generate_with_retry(prompt)
        except ImageGenerationError as e:
            result = GeneratedImage(success=False, error=str(e), prompt_used=prompt)

        # Upload to R2 if successful and storage is configured
        if result.success and result.image_data and self.storage and self.book_job_id:
            r2_key = await self._upload_image(result.image_data, page_number)
            result.image_path = r2_key

        return result

    async def generate_all_images(
        self,
        pages: List[Dict[str, Any]],
        story_context: str = "",
        progress_callback: Optional[callable] = None,
        max_concurrent: int = 5,
    ) -> Dict[int, GeneratedImage]:
        """Generate images for all pages with controlled concurrency.

        Args:
            pages: List of page dicts with page_number, content, page_type.
            story_context: Brief story summary for prompt context.
            progress_callback: Optional callback(current, total, page_num).
            max_concurrent: Max simultaneous API requests (prevents rate-limiting).
        """
        results = {}
        total = len(pages)
        semaphore = asyncio.Semaphore(max_concurrent)

        logger.info(f"Starting image generation for {total} pages (max {max_concurrent} concurrent)")

        # Filter out blank pages and build task list
        tasks_to_run = []
        for i, page in enumerate(pages):
            page_num = page['page_number']
            page_type = page.get('page_type', 'content')

            if page_type == 'blank':
                logger.info(f"Skipping blank page {page_num}")
                continue

            tasks_to_run.append((i, page))

        async def _generate_one(index: int, page: Dict[str, Any]) -> tuple[int, GeneratedImage]:
            page_num = page.get('page_number', index)
            try:
                page_type = page.get('page_type', 'content')
                content = page.get('content', '')

                logger.info(f"Processing page {page_num}/{total}: type={page_type}, content_len={len(content)}")

                if progress_callback:
                    progress_callback(index + 1, total, page_num)

                # Build prompt and check cache WITHOUT holding a semaphore slot
                # (cache checks are DB+R2 I/O, not OpenRouter API calls)
                prompt = self._build_page_prompt(
                    page_text=content,
                    page_number=page_num,
                    total_pages=total,
                    story_context=story_context,
                    is_cover=(page_type == 'cover'),
                    is_end=(page_type == 'end'),
                )

                cached = await self._check_cache(prompt, page_num)
                if cached:
                    logger.info(f"Page {page_num}: Cache hit")
                    return page_num, cached

                # Only acquire semaphore for actual API calls
                # NOTE: semaphore stays held during retries (up to 3 × 120s + backoff).
                # Acceptable because the 1200s global task timeout in book_tasks.py
                # will cancel the whole job before this becomes a problem.
                async with semaphore:
                    try:
                        result = await self._generate_with_retry(prompt)
                    except ImageGenerationError as e:
                        result = GeneratedImage(success=False, error=str(e), prompt_used=prompt)

                # Upload to R2 outside semaphore (network I/O, not rate-limited)
                if result.success and result.image_data and self.storage and self.book_job_id:
                    r2_key = await self._upload_image(result.image_data, page_num)
                    result.image_path = r2_key

                if result.success:
                    logger.info(f"Page {page_num}: Image generated successfully")
                else:
                    logger.warning(f"Page {page_num}: Image generation failed: {result.error}")

                return page_num, result

            except Exception as exc:
                logger.error(f"Page {page_num}: Unexpected error: {exc}", exc_info=True)
                return page_num, GeneratedImage(success=False, error=f"Unexpected: {exc}")

        try:
            gathered = await asyncio.gather(
                *[_generate_one(i, page) for i, page in tasks_to_run]
            )

            for page_num, result in gathered:
                results[page_num] = result
        finally:
            await self.generator.close()

        logger.info(f"Image generation complete: {sum(1 for r in results.values() if r.success)}/{len(results)} successful")
        return results
