"""
Image Generator for Children's Book Pages.

This module handles AI image generation for each page of the book
using OpenRouter API.
"""

import os
import asyncio
import httpx
import base64
import hashlib
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

from src.core.config import BookConfig, DEFAULT_IMAGE_MODEL
from src.core.prompts import (
    build_cover_image_prompt,
    build_end_page_image_prompt,
    build_content_page_image_prompt,
    StoryVisualContext,
)


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


class OpenRouterImageGenerator:
    """Generate images using OpenRouter API with chat completions endpoint."""

    def __init__(self, config: ImageConfig):
        self.config = config
        self.headers = {
            "Authorization": f"Bearer {config.get_api_key()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/book-generator",
            "X-Title": "Children's Book Generator"
        }

    async def generate(self, prompt: str) -> GeneratedImage:
        """Generate an image from prompt using chat completions with image modality."""
        logger.debug(f"Generating image with model: {self.config.model}")
        logger.debug(f"Prompt length: {len(prompt)} chars")

        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "user",
                    "content": f"Generate an image: {prompt}"
                }
            ],
            "modalities": ["image", "text"],
            # Request portrait aspect ratio for A5 page format
            "image_generation": {
                "aspect_ratio": "3:4"  # Close to A5 (1:1.41), minimizes white space
            }
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                logger.debug(f"Sending request to {self.config.base_url}")
                response = await client.post(
                    self.config.base_url,
                    headers=self.headers,
                    json=payload
                )
                response.raise_for_status()

                data = response.json()
                logger.debug(f"Response keys: {data.keys()}")

                # Extract image from the response
                if data.get("choices"):
                    message = data["choices"][0].get("message", {})
                    images = message.get("images", [])
                    logger.debug(f"Found {len(images)} images in response")

                    if images:
                        # Get the first image's base64 data URL
                        image_url = images[0].get("image_url", {}).get("url", "")

                        if image_url and "," in image_url:
                            # Parse data URL: "data:image/png;base64,ENCODED_DATA"
                            header, encoded = image_url.split(",", 1)
                            image_bytes = base64.b64decode(encoded)
                            logger.debug(f"Successfully decoded image: {len(image_bytes)} bytes")

                            return GeneratedImage(
                                success=True,
                                image_data=image_bytes,
                                prompt_used=prompt
                            )
                        else:
                            logger.warning(f"Invalid image URL format: {image_url[:100] if image_url else 'empty'}")

                logger.warning(f"No image in response. Message keys: {message.keys() if 'message' in dir() else 'N/A'}")
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
    Handles caching and coordination of image generation.
    """

    def __init__(
        self,
        config: ImageConfig,
        book_config: Optional[BookConfig] = None,
        visual_context: Optional[StoryVisualContext] = None
    ):
        self.config = config
        self.book_config = book_config or BookConfig()
        self.visual_context = visual_context
        self.cache_dir = Path(config.cache_dir)
        self.generator = OpenRouterImageGenerator(config)

        # Ensure cache directory exists
        if config.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def set_visual_context(self, visual_context: StoryVisualContext) -> None:
        """Set the visual context for consistent illustrations."""
        self.visual_context = visual_context

    def _get_cache_path(self, prompt: str) -> Path:
        """Generate cache file path from prompt hash."""
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:16]
        return self.cache_dir / f"img_{prompt_hash}.png"

    def _load_from_cache(self, prompt: str) -> Optional[GeneratedImage]:
        """Try to load image from cache."""
        if not self.config.use_cache:
            return None

        cache_path = self._get_cache_path(prompt)
        if cache_path.exists():
            try:
                image_data = cache_path.read_bytes()
                return GeneratedImage(
                    success=True,
                    image_path=str(cache_path),
                    image_data=image_data,
                    prompt_used=prompt,
                    cached=True
                )
            except Exception:
                return None
        return None

    def _save_to_cache(self, prompt: str, image_data: bytes) -> str:
        """Save image to cache and return path."""
        cache_path = self._get_cache_path(prompt)
        cache_path.write_bytes(image_data)
        return str(cache_path)

    async def generate_image(
        self,
        page_text: str,
        page_number: int,
        total_pages: int,
        story_context: str = "",
        is_cover: bool = False,
        is_end: bool = False
    ) -> GeneratedImage:
        """
        Generate an image for a single page.

        Args:
            page_text: Text content of the page
            page_number: Page number
            total_pages: Total pages in book
            story_context: Overall story summary
            is_cover: Whether this is the cover
            is_end: Whether this is the end page

        Returns:
            GeneratedImage with result
        """
        # Build prompt
        prompt_builder = ImagePromptBuilder(
            style=self.config.image_style,
            book_title=self.book_config.cover_title or "Story Book",
            target_age=(self.book_config.target_age_min, self.book_config.target_age_max),
            text_on_image=self.config.text_on_image,
            visual_context=self.visual_context
        )

        prompt = prompt_builder.build_prompt(
            page_text=page_text,
            page_number=page_number,
            total_pages=total_pages,
            story_context=story_context,
            is_cover=is_cover,
            is_end=is_end
        )

        # Check cache
        cached = self._load_from_cache(prompt)
        if cached:
            return cached

        # Generate new image
        result = await self.generator.generate(prompt)

        # Save to cache if successful
        if result.success and result.image_data and self.config.use_cache:
            cache_path = self._save_to_cache(prompt, result.image_data)
            result.image_path = cache_path

        return result

    async def generate_all_images(
        self,
        pages: List[Dict[str, Any]],
        story_context: str = "",
        progress_callback: Optional[callable] = None,
    ) -> Dict[int, GeneratedImage]:
        """
        Generate images for all pages in parallel.

        Args:
            pages: List of page dicts with 'page_number', 'content', 'page_type'
            story_context: Overall story summary
            progress_callback: Optional callback(current, total, page_num)

        Returns:
            Dict mapping page_number to GeneratedImage
        """
        results = {}
        total = len(pages)

        logger.info(f"Starting parallel image generation for {total} pages")
        logger.debug(f"Pages to process: {[(p.get('page_number'), p.get('page_type')) for p in pages]}")

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
            page_num = page['page_number']
            page_type = page.get('page_type', 'content')
            content = page.get('content', '')

            logger.info(f"Processing page {page_num}/{total}: type={page_type}, content_len={len(content)}")

            if progress_callback:
                progress_callback(index + 1, total, page_num)

            result = await self.generate_image(
                page_text=content,
                page_number=page_num,
                total_pages=total,
                story_context=story_context,
                is_cover=(page_type == 'cover'),
                is_end=(page_type == 'end')
            )

            if result.success:
                logger.info(f"Page {page_num}: Image generated successfully (cached={result.cached})")
            else:
                logger.warning(f"Page {page_num}: Image generation failed: {result.error}")

            return page_num, result

        # Run all image generations concurrently — no limit
        gathered = await asyncio.gather(
            *[_generate_one(i, page) for i, page in tasks_to_run]
        )

        for page_num, result in gathered:
            results[page_num] = result

        logger.info(f"Image generation complete: {sum(1 for r in results.values() if r.success)}/{len(results)} successful")
        return results


def create_image_generator(
    api_key: Optional[str] = None,
    book_config: Optional[BookConfig] = None,
    **kwargs
) -> BookImageGenerator:
    """
    Factory function to create an image generator.

    Args:
        api_key: OpenRouter API key (or use environment variable)
        book_config: Book configuration
        **kwargs: Additional config options

    Returns:
        Configured BookImageGenerator
    """
    config = ImageConfig(
        api_key=api_key or "",
        **kwargs
    )

    return BookImageGenerator(config, book_config)
