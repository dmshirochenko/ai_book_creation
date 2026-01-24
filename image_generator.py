"""
Image Generator for Children's Book Pages.

This module handles AI image generation for each page of the book
using OpenRouter API.
"""

import os
import httpx
import base64
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from config import BookConfig


@dataclass
class ImageConfig:
    """Configuration for image generation via OpenRouter."""
    
    api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    base_url: str = "https://openrouter.ai/api/v1/chat/completions"
    
    # Model settings - use a model that supports image output
    model: str = "google/gemini-3-pro-image-preview"  # OpenRouter image-capable model
    
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
    
    def __init__(self, style: str, book_title: str, target_age: tuple = (2, 4), text_on_image: bool = False):
        self.style = style
        self.book_title = book_title
        self.target_age = target_age
        self.text_on_image = text_on_image
    
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
        base_style = f"{self.style}, safe for children ages {self.target_age[0]}-{self.target_age[1]}"
        
        # Text overlay instructions
        if self.text_on_image:
            text_instruction = f'''\nIMPORTANT: Include the following text overlaid on the image in a clear, readable font suitable for children:
"{page_text}"
Place the text at the bottom of the image with a semi-transparent background for readability.'''
        else:
            text_instruction = "\nNo text or words in the image."
        
        if is_cover:
            if self.text_on_image:
                prompt = f"""Create a book cover illustration for a children's book.
Style: {base_style}
The image should be inviting, magical, and set the tone for the story.
Story summary: {story_context if story_context else page_text}

IMPORTANT: Include the title "{self.book_title}" prominently displayed on the cover in a fun, child-friendly font."""
            else:
                prompt = f"""Create a book cover illustration for a children's book titled "{self.book_title}".
Style: {base_style}
The image should be inviting, magical, and set the tone for the story.
Story summary: {story_context if story_context else page_text}
No text in the image."""
        
        elif is_end:
            prompt = f"""Create a peaceful, concluding illustration for a children's book.
Style: {base_style}
The scene should feel calm, complete, and satisfying - like a happy ending.
Context from the story: {story_context}{text_instruction}"""
        
        else:
            prompt = f"""Create an illustration for page {page_number} of a children's book.
Style: {base_style}
Scene to illustrate: {page_text}
Overall story context: {story_context if story_context else self.book_title}
The illustration should be simple, clear, and directly related to the text.{text_instruction}"""
        
        return prompt


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
    
    def generate(self, prompt: str) -> GeneratedImage:
        """Generate an image from prompt using chat completions with image modality."""
        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "user",
                    "content": f"Generate an image: {prompt}"
                }
            ],
            "modalities": ["image", "text"]
        }
        
        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(
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
                            
                            return GeneratedImage(
                                success=True,
                                image_data=image_bytes,
                                prompt_used=prompt
                            )
                
                return GeneratedImage(
                    success=False,
                    error="No image in response"
                )
                
        except httpx.HTTPStatusError as e:
            return GeneratedImage(
                success=False,
                error=f"API error: {e.response.status_code} - {e.response.text}"
            )
        except Exception as e:
            return GeneratedImage(
                success=False,
                error=f"Request failed: {str(e)}"
            )


class BookImageGenerator:
    """
    Main class for generating all images for a children's book.
    Handles caching and coordination of image generation.
    """
    
    def __init__(self, config: ImageConfig, book_config: Optional[BookConfig] = None):
        self.config = config
        self.book_config = book_config or BookConfig()
        self.cache_dir = Path(config.cache_dir)
        self.generator = OpenRouterImageGenerator(config)
        
        # Ensure cache directory exists
        if config.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
    
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
    
    def generate_image(
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
            text_on_image=self.config.text_on_image
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
        result = self.generator.generate(prompt)
        
        # Save to cache if successful
        if result.success and result.image_data and self.config.use_cache:
            cache_path = self._save_to_cache(prompt, result.image_data)
            result.image_path = cache_path
        
        return result
    
    def generate_all_images(
        self,
        pages: List[Dict[str, Any]],
        story_context: str = "",
        progress_callback: Optional[callable] = None
    ) -> Dict[int, GeneratedImage]:
        """
        Generate images for all pages.
        
        Args:
            pages: List of page dicts with 'page_number', 'content', 'page_type'
            story_context: Overall story summary
            progress_callback: Optional callback(current, total, page_num)
            
        Returns:
            Dict mapping page_number to GeneratedImage
        """
        results = {}
        total = len(pages)
        
        for i, page in enumerate(pages):
            page_num = page['page_number']
            page_type = page.get('page_type', 'content')
            content = page.get('content', '')
            
            # Skip blank pages
            if page_type == 'blank':
                continue
            
            if progress_callback:
                progress_callback(i + 1, total, page_num)
            
            result = self.generate_image(
                page_text=content,
                page_number=page_num,
                total_pages=total,
                story_context=story_context,
                is_cover=(page_type == 'cover'),
                is_end=(page_type == 'end')
            )
            
            results[page_num] = result
        
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
