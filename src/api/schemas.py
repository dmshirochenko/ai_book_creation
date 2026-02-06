"""
Pydantic schemas for API request/response models.
"""

from typing import Optional, Literal, List
from pydantic import BaseModel, Field

from src.core.config import DEFAULT_IMAGE_MODEL


class BookGenerateRequest(BaseModel):
    """Request schema for book generation."""
    
    story: str = Field(..., description="Story text to convert into a book")
    title: Optional[str] = Field(None, description="Book title (extracted from story if not provided)")
    author: str = Field("A Bedtime Story", description="Author name for the cover")
    age_min: int = Field(2, ge=1, le=10, description="Minimum target age")
    age_max: int = Field(4, ge=1, le=10, description="Maximum target age")
    language: str = Field("English", description="Target language for the book")
    font_size: int = Field(24, ge=12, le=48, description="Content font size in points")
    title_font_size: int = Field(36, ge=18, le=72, description="Title font size in points")
    skip_adaptation: bool = Field(False, description="Skip LLM adaptation (use story as-is)")
    end_text: str = Field("The End", description="Text for the final page")
    generate_images: bool = Field(False, description="Generate AI illustrations for each page")
    image_model: str = Field(
        DEFAULT_IMAGE_MODEL,
        description="OpenRouter image model to use"
    )
    image_style: str = Field(
        "children's book illustration, soft watercolor style, gentle colors, simple shapes, cute and friendly",
        description="Style description for generated images"
    )
    use_image_cache: bool = Field(True, description="Use cached images if available")
    text_on_image: bool = Field(False, description="Render story text directly on images")
    background_color: Optional[str] = Field(None, description="PDF background color as hex (e.g., '#FFF8E7' for cream, '#F0F8FF' for light blue)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "story": "Once upon a time, there was a little bunny who loved to hop in the meadow.",
                    "title": "The Happy Bunny",
                    "author": "A Bedtime Story",
                    "age_min": 2,
                    "age_max": 4,
                    "language": "English",
                    "generate_images": False
                }
            ]
        }
    }


class JobStatus(BaseModel):
    """Status of a book generation job."""
    
    job_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    progress: Optional[str] = Field(None, description="Current progress message")
    title: Optional[str] = Field(None, description="Book title")
    total_pages: Optional[int] = Field(None, description="Total number of pages")
    booklet_filename: Optional[str] = Field(None, description="Booklet PDF filename")
    review_filename: Optional[str] = Field(None, description="Review PDF filename")
    error: Optional[str] = Field(None, description="Error message if failed")


class BookGenerateResponse(BaseModel):
    """Response schema for book generation request."""
    
    job_id: str = Field(..., description="Unique job identifier for tracking")
    message: str = Field(..., description="Status message")


class BookListItem(BaseModel):
    """Item in the list of generated books."""
    
    job_id: str
    title: str
    created_at: str
    status: Literal["pending", "processing", "completed", "failed"]


class BookListResponse(BaseModel):
    """Response schema for listing generated books."""
    
    books: List[BookListItem]
    total: int


class ErrorResponse(BaseModel):
    """Standard error response."""
    
    detail: str
    error_code: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str = "1.0.0"
    openrouter_configured: bool
    database_configured: bool = False


# =============================================================================
# STORY CREATION SCHEMAS
# =============================================================================

class StoryCreateRequest(BaseModel):
    """Request schema for story creation."""

    prompt: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Your story idea or prompt (10-500 characters)"
    )
    age_min: int = Field(2, ge=1, le=10, description="Minimum target age")
    age_max: int = Field(4, ge=1, le=10, description="Maximum target age")
    tone: Literal["cheerful", "calm", "adventurous", "silly"] = Field(
        "cheerful",
        description="Story tone and mood"
    )
    length: Literal["short", "medium", "long"] = Field(
        "medium",
        description="Story length (short=6-8 pages, medium=10-12, long=14-16)"
    )
    language: str = Field("English", description="Story language")
    author: str = Field("A Bedtime Story", description="Author name for book generation")
    generate_book: bool = Field(
        False,
        description="Automatically generate book PDF after story creation"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "prompt": "A curious kitten discovers a magical garden in the backyard",
                    "age_min": 2,
                    "age_max": 4,
                    "tone": "cheerful",
                    "length": "medium",
                    "language": "English",
                    "author": "A Bedtime Story",
                    "generate_book": False
                }
            ]
        }
    }


class StoryJobStatus(BaseModel):
    """Status of a story creation job."""

    job_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    progress: Optional[str] = Field(None, description="Current progress message")
    error: Optional[str] = Field(None, description="Error message if failed")

    # Story-specific fields
    generated_title: Optional[str] = Field(None, description="LLM-generated story title")
    generated_story: Optional[str] = Field(None, description="Full story text (formatted)")
    story_length: Optional[int] = Field(None, description="Number of pages/lines in story")
    tokens_used: Optional[int] = Field(None, description="Tokens used for generation")

    # If generate_book was requested
    book_job_id: Optional[str] = Field(None, description="Book generation job ID if requested")


class StoryCreateResponse(BaseModel):
    """Response schema for story creation request."""

    job_id: str = Field(..., description="Unique job identifier for tracking")
    message: str = Field(..., description="Status message")
