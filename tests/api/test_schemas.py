"""Tests for src/api/schemas.py — Pydantic model validation."""

import pytest
from pydantic import ValidationError

from src.api.schemas import (
    BookGenerateRequest,
    JobStatus,
    BookGenerateResponse,
    BookListItem,
    BookListResponse,
    GeneratedBookItem,
    GeneratedBookListResponse,
    ErrorResponse,
    HealthResponse,
    StoryCreateRequest,
    StoryJobStatus,
    StoryCreateResponse,
)


# =============================================================================
# BookGenerateRequest
# =============================================================================


class TestBookGenerateRequest:
    def test_minimal_valid(self):
        req = BookGenerateRequest(story="A bunny hops around.")
        assert req.story == "A bunny hops around."
        assert req.age_min == 2
        assert req.age_max == 4
        assert req.generate_images is False

    def test_all_fields(self):
        req = BookGenerateRequest(
            story="A story here.",
            title="My Book",
            author="Author",
            age_min=3,
            age_max=5,
            language="Spanish",
            font_size=28,
            title_font_size=42,
            end_text="Fin",
            generate_images=True,
            image_style="cartoon",
            text_on_image=True,
            background_color="#FFF8E7",
        )
        assert req.title == "My Book"
        assert req.age_min == 3
        assert req.background_color == "#FFF8E7"

    def test_age_min_too_low(self):
        with pytest.raises(ValidationError):
            BookGenerateRequest(story="test", age_min=0)

    def test_age_max_too_high(self):
        with pytest.raises(ValidationError):
            BookGenerateRequest(story="test", age_max=11)

    def test_font_size_bounds(self):
        with pytest.raises(ValidationError):
            BookGenerateRequest(story="test", font_size=10)
        with pytest.raises(ValidationError):
            BookGenerateRequest(story="test", font_size=50)


# =============================================================================
# JobStatus
# =============================================================================


class TestJobStatus:
    def test_pending(self):
        status = JobStatus(job_id="abc", status="pending")
        assert status.status == "pending"
        assert status.progress is None

    def test_completed_with_files(self):
        status = JobStatus(
            job_id="abc",
            status="completed",
            title="My Book",
            total_pages=8,
            booklet_filename="test_booklet.pdf",
            review_filename="test_review.pdf",
        )
        assert status.booklet_filename == "test_booklet.pdf"

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            JobStatus(job_id="abc", status="unknown")


# =============================================================================
# StoryCreateRequest
# =============================================================================


class TestStoryCreateRequest:
    def test_minimal_valid(self):
        req = StoryCreateRequest(prompt="A kitten finds a magical garden in the yard")
        assert req.tone == "cheerful"
        assert req.length == "medium"
        assert req.author == "TaleHop Stories"

    def test_prompt_too_short(self):
        with pytest.raises(ValidationError):
            StoryCreateRequest(prompt="short")

    def test_invalid_tone(self):
        with pytest.raises(ValidationError):
            StoryCreateRequest(
                prompt="A valid prompt here that is long enough",
                tone="angry",
            )

    def test_invalid_length(self):
        with pytest.raises(ValidationError):
            StoryCreateRequest(
                prompt="A valid prompt here that is long enough",
                length="extra-long",
            )


# =============================================================================
# StoryJobStatus
# =============================================================================


class TestStoryJobStatus:
    def test_completed_with_story(self):
        status = StoryJobStatus(
            job_id="abc",
            status="completed",
            generated_title="My Story",
            generated_story="Once upon a time...",
            generated_story_json={"title": "My Story", "pages": []},
            story_length=5,
            tokens_used=200,
        )
        assert status.generated_title == "My Story"
        assert status.tokens_used == 200


# =============================================================================
# HealthResponse
# =============================================================================


class TestHealthResponse:
    def test_defaults(self):
        resp = HealthResponse(openrouter_configured=True)
        assert resp.status == "healthy"
        assert resp.version == "1.0.0"
        assert resp.openrouter_configured is True
        assert resp.database_configured is False


# =============================================================================
# Simple response models
# =============================================================================


class TestResponseModels:
    def test_book_generate_response(self):
        resp = BookGenerateResponse(job_id="abc", message="Started")
        assert resp.job_id == "abc"

    def test_error_response(self):
        resp = ErrorResponse(detail="Something went wrong", error_code="ERR001")
        assert resp.detail == "Something went wrong"

    def test_book_list_response(self):
        items = [
            BookListItem(
                job_id="a", title="Book A", created_at="2024-01-01", status="completed"
            )
        ]
        resp = BookListResponse(books=items, total=1)
        assert resp.total == 1

    def test_story_create_response(self):
        resp = StoryCreateResponse(job_id="xyz", message="Started")
        assert resp.job_id == "xyz"

    def test_generated_book_item(self):
        item = GeneratedBookItem(
            job_id="abc",
            title="My Book",
            booklet_url="/api/v1/books/abc/download/booklet",
            review_url="/api/v1/books/abc/download/review",
            created_at="2024-01-01T00:00:00+00:00",
        )
        assert item.job_id == "abc"
        assert item.title == "My Book"
        assert "booklet" in item.booklet_url
        assert "review" in item.review_url

    def test_generated_book_list_response(self):
        items = [
            GeneratedBookItem(
                job_id="a",
                title="Book A",
                booklet_url="/api/v1/books/a/download/booklet",
                review_url="/api/v1/books/a/download/review",
                created_at="2024-01-01",
            )
        ]
        resp = GeneratedBookListResponse(books=items, total=1)
        assert resp.total == 1
        assert len(resp.books) == 1
        assert resp.books[0].title == "Book A"

    def test_generated_book_list_response_empty(self):
        resp = GeneratedBookListResponse(books=[], total=0)
        assert resp.total == 0
        assert resp.books == []

    def test_generated_book_item_missing_required_field(self):
        with pytest.raises(ValidationError):
            GeneratedBookItem(
                job_id="abc",
                title="My Book",
                # missing booklet_url, review_url, created_at
            )
