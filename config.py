"""
Configuration settings for the Children's Book Generator.
"""

from dataclasses import dataclass, field
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass
class BookConfig:
    """Configuration for book generation."""
    
    # Target audience
    target_age_min: int = 2
    target_age_max: int = 4
    
    # Language settings
    language: str = "English"
    
    # Typography
    font_size: int = 24
    title_font_size: int = 36
    
    # Page settings
    max_sentences_per_page: int = 2
    max_characters_per_page: int = 100
    
    # PDF settings
    paper_size: str = "A4"  # A4 landscape for printing
    output_dpi: int = 300
    
    # Margins (in points, 72 points = 1 inch)
    margin_top: int = 50
    margin_bottom: int = 50
    margin_left: int = 40
    margin_right: int = 40
    
    # Cover settings
    cover_title: Optional[str] = None
    author_name: str = "A Bedtime Story"
    
    # End page text
    end_page_text: str = "The End"
    
    # Font configuration
    font_family: str = "DejaVuSans"  # Unicode-compatible font


@dataclass
class LLMConfig:
    """Configuration for OpenRouter LLM API."""
    
    api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "anthropic/claude-3-haiku"  # Cost-effective for text adaptation
    max_tokens: int = 2000
    temperature: float = 0.7
    
    # Rate limiting
    requests_per_minute: int = 20
    
    def validate(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)


@dataclass
class GeneratorConfig:
    """Main configuration combining all settings."""
    
    book: BookConfig = field(default_factory=BookConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    
    # Output settings
    output_dir: str = "output"
    debug_mode: bool = False
    
    def __post_init__(self):
        """Ensure output directory exists."""
        os.makedirs(self.output_dir, exist_ok=True)
