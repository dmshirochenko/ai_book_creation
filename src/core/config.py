"""
Configuration settings for the Children's Book Generator.
"""

from dataclasses import dataclass, field
from typing import Optional
import os

# Default models
DEFAULT_IMAGE_MODEL = "google/gemini-2.5-flash-image"
DEFAULT_ANALYSIS_MODEL = "google/gemini-2.5-flash"  # Supports structured outputs

# TextProcessor defaults (used in routes and tasks)
DEFAULT_MAX_SENTENCES_PER_PAGE = 2
DEFAULT_MAX_CHARS_PER_PAGE = 100

from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMConfig:
    """Configuration for OpenRouter LLM API."""
    
    api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "anthropic/claude-3-haiku"  # Cost-effective for text adaptation
    analysis_model: str = DEFAULT_ANALYSIS_MODEL  # Model for structured outputs (story analysis)
    max_tokens: int = 2000
    temperature: float = 0.7
    
    # Rate limiting
    requests_per_minute: int = 20
    
    def validate(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)
