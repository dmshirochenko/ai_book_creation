"""
Pydantic schemas for API request/response models.
"""

from typing import Optional, Literal, List
from pydantic import BaseModel, Field, model_validator

from src.core.config import DEFAULT_IMAGE_MODEL


class StoryPageItem(BaseModel):
    """A single page in a structured story input."""
    text: str = Field(..., max_length=5000, description="Text content for this page")


class StoryStructuredInput(BaseModel):
    """Validated structure for story_structured field."""
    title: Optional[str] = Field(None, max_length=200, description="Story title")
    pages: List[StoryPageItem] = Field(..., min_length=1, max_length=50, description="Story pages")


SUPPORTED_LANGUAGES = {
    "en": "English",
    "ru": "Russian",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
}

TEXT_ON_IMAGE_SUPPORTED_LANGUAGES = ["en"]

END_TEXT_BY_LANGUAGE = {
    "en": "The End",
    "ru": "Конец",
    "es": "Fin",
    "fr": "Fin",
    "de": "Ende",
    "it": "Fine",
    "pt": "Fim",
    "zh": "终",
    "ja": "おしまい",
    "ko": "끝",
}


class BookGenerateRequest(BaseModel):
    """Request schema for book generation."""

    story: str = Field(..., max_length=50000, description="Story text to convert into a book")
    story_structured: Optional[StoryStructuredInput] = Field(None, description="Structured story JSON from story generation: {title, pages: [{text}]}")
    title: Optional[str] = Field(None, description="Book title (extracted from story if not provided)")
    author: str = Field("TaleHop Stories", description="Author name for the cover")
    age_min: int = Field(2, ge=1, le=10, description="Minimum target age")
    age_max: int = Field(4, ge=1, le=10, description="Maximum target age")
    language: str = Field("English", description="Target language for the book")
    font_size: int = Field(24, ge=12, le=48, description="Content font size in points")
    title_font_size: int = Field(36, ge=18, le=72, description="Title font size in points")
    end_text: Optional[str] = Field(None, description="Text for the final page (auto-localized from language if not set)")
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
    font_family: str = Field("DejaVuSans", description="Font family for PDF text (Unicode-compatible)")
    margin_top: int = Field(50, ge=10, le=150, description="Top margin in points (72 points = 1 inch)")
    margin_left: int = Field(40, ge=10, le=150, description="Left margin in points")
    margin_right: int = Field(40, ge=10, le=150, description="Right margin in points")

    @model_validator(mode="after")
    def set_end_text_from_language(self):
        if self.end_text is None:
            lang_key = self.language.lower().strip()
            # Try as ISO code first, then try mapping full name to code
            if lang_key in END_TEXT_BY_LANGUAGE:
                self.end_text = END_TEXT_BY_LANGUAGE[lang_key]
            else:
                # Map full name to code: "english" -> "en"
                name_to_code = {v.lower(): k for k, v in SUPPORTED_LANGUAGES.items()}
                code = name_to_code.get(lang_key)
                self.end_text = END_TEXT_BY_LANGUAGE.get(code, "The End") if code else "The End"
        return self

    @model_validator(mode="after")
    def validate_text_on_image_language(self):
        if self.text_on_image:
            lang_key = self.language.lower().strip()
            # Check if it's a code or full name
            name_to_code = {v.lower(): k for k, v in SUPPORTED_LANGUAGES.items()}
            code = lang_key if lang_key in SUPPORTED_LANGUAGES else name_to_code.get(lang_key)
            if code and code not in TEXT_ON_IMAGE_SUPPORTED_LANGUAGES:
                raise ValueError(
                    f"Text on image is not supported for language '{self.language}'. "
                    f"Supported languages: {', '.join(TEXT_ON_IMAGE_SUPPORTED_LANGUAGES)}"
                )
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "story": "Once upon a time, there was a little bunny who loved to hop in the meadow.",
                    "title": "The Happy Bunny",
                    "author": "TaleHop Stories",
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


class BookRegenerateResponse(BaseModel):
    """Response schema for book regeneration request."""

    job_id: str = Field(..., description="Book job identifier")
    status: str = Field(..., description="New job status")
    failed_image_count: int = Field(..., description="Number of failed images to retry")
    message: str = Field(..., description="Status message")


class FailedImageItem(BaseModel):
    """A single failed image in the status response."""

    page_number: int = Field(..., description="Page number of the failed image")
    error: Optional[str] = Field(None, description="Error message from generation")


class BookImageStatusResponse(BaseModel):
    """Response schema for checking book image health."""

    job_id: str = Field(..., description="Book job identifier")
    total_images: int = Field(..., description="Total number of images for this book")
    failed_images: int = Field(..., description="Number of failed images")
    has_failed_images: bool = Field(..., description="Whether the book has any failed images")
    failed_pages: List[FailedImageItem] = Field(default_factory=list, description="Details of failed images")


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


class GeneratedBookItem(BaseModel):
    """A completed book with download links."""

    job_id: str
    title: str
    booklet_url: str
    review_url: str
    created_at: str


class GeneratedBookListResponse(BaseModel):
    """Response for listing generated books."""

    books: List[GeneratedBookItem]
    total: int


class BatchImageStatusRequest(BaseModel):
    """Request schema for batch image status check."""

    job_ids: List[str] = Field(..., description="List of book job IDs to check", max_length=100)


class BatchImageStatusItem(BaseModel):
    """Image status for a single book in a batch response."""

    job_id: str
    total_images: int
    failed_images: int
    has_failed_images: bool


class BatchImageStatusResponse(BaseModel):
    """Response schema for batch image status check."""

    statuses: List[BatchImageStatusItem]


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
    author: str = Field("TaleHop Stories", description="Author name for book generation")

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
                    "author": "TaleHop Stories"
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

    # Safety fields
    safety_status: Optional[str] = Field(None, description="Safety classification: 'safe' or 'unsafe'")
    safety_reasoning: Optional[str] = Field(None, description="If unsafe, explains why the story was rejected")

    # Story-specific fields
    generated_title: Optional[str] = Field(None, description="LLM-generated story title")
    generated_story: Optional[str] = Field(None, description="Full story text (formatted)")
    generated_story_json: Optional[dict] = Field(None, description="Structured story data: {title, pages: [{text}]}")
    story_length: Optional[int] = Field(None, description="Number of pages/lines in story")
    tokens_used: Optional[int] = Field(None, description="Tokens used for generation")
    language_code: Optional[str] = Field(None, description="ISO 639-1 code of the language the story was generated in")


class StoryCreateResponse(BaseModel):
    """Response schema for story creation request."""

    job_id: str = Field(..., description="Unique job identifier for tracking")
    message: str = Field(..., description="Status message")


class StoryValidateRequest(BaseModel):
    """Request schema for story validation."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Story title to validate"
    )
    story_text: str = Field(
        ...,
        min_length=10,
        max_length=10000,
        description="Full story text to validate"
    )
    age_min: int = Field(2, ge=1, le=10, description="Minimum target age")
    age_max: int = Field(4, ge=1, le=10, description="Maximum target age")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "title": "The Happy Bunny",
                    "story_text": "A bunny hops in the garden.\nThe bunny finds a flower.\nThe bunny is happy.",
                    "age_min": 2,
                    "age_max": 4,
                }
            ]
        }
    }


class StoryValidateResponse(BaseModel):
    """Response schema for story validation."""

    status: Literal["pass", "fail"] = Field(
        ...,
        description="Validation result: 'pass' if the story is appropriate, 'fail' if not"
    )
    reasoning: str = Field(
        "",
        description="If status is 'fail', explains why the story did not pass validation"
    )
    language_code: Optional[str] = Field(None, description="ISO 639-1 code detected from the story text")


# =============================================================================
# STORY RE-SPLIT SCHEMAS
# =============================================================================

class StoryResplitRequest(BaseModel):
    """Request schema for story re-splitting."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Story title"
    )
    story_text: str = Field(
        ...,
        min_length=10,
        max_length=10000,
        description="Full story text to split into pages"
    )
    age_min: int = Field(2, ge=1, le=10, description="Minimum target age")
    age_max: int = Field(4, ge=1, le=10, description="Maximum target age")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "title": "The Happy Bunny",
                    "story_text": "A bunny hops in the garden. The bunny finds a flower. The bunny smells the flower. It smells wonderful! The bunny picks the flower. The bunny brings it home. Mama bunny loves the flower. They put it in a vase. What a lovely day!",
                    "age_min": 2,
                    "age_max": 4,
                }
            ]
        }
    }


class StoryResplitPageItem(BaseModel):
    """A single page in the re-split response."""
    text: str = Field(..., description="Text content for this page")


class StoryResplitResponse(BaseModel):
    """Response schema for story re-splitting."""

    title: str = Field(..., description="Story title (echoed back)")
    pages: List[StoryResplitPageItem] = Field(
        ...,
        description="Story text split into pages with narrative-aware breaks"
    )
    language_code: Optional[str] = Field(None, description="ISO 639-1 code detected from the story text")


# =============================================================================
# CREDIT SCHEMAS
# =============================================================================

class CreditPricingItem(BaseModel):
    """A single pricing configuration item."""
    operation: str
    credit_cost: float
    description: Optional[str] = None
    display_name: Optional[str] = None
    is_image_model: bool = False


class CreditPricingResponse(BaseModel):
    """Response for GET /credits/pricing."""
    pricing: List[CreditPricingItem]


class CreditBalanceResponse(BaseModel):
    """Response for GET /credits/balance."""
    balance: float


class CreditUsageItem(BaseModel):
    """A single credit usage log entry."""
    id: str
    job_id: str
    job_type: str
    credits_used: float
    status: str
    description: Optional[str] = None
    created_at: str


class CreditUsageResponse(BaseModel):
    """Response for GET /credits/usage."""
    usage: List[CreditUsageItem]


class InsufficientCreditsResponse(BaseModel):
    """Error response when user lacks credits."""
    detail: str
    balance: float
    required: float


class UsageLogItem(BaseModel):
    """A single usage log entry with metadata."""
    id: str
    job_id: str
    job_type: str
    credits_used: float
    status: str
    description: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: str


class PaginatedUsageLogsResponse(BaseModel):
    """Paginated response for GET /credits/usage-logs."""
    items: List[UsageLogItem]
    total: int
    page: int
    page_size: int
