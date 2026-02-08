# Image Retry Mechanism Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add automatic inline retries (3 attempts with exponential backoff) to image generation and a `POST /books/{job_id}/regenerate` endpoint to retry failed images and replace PDFs.

**Architecture:** An `@async_retry` decorator wraps the single-image generation call with exponential backoff (2s, 4s). The regenerate endpoint runs as a background task that finds failed images, retries them, then regenerates and replaces both PDFs in R2.

**Tech Stack:** Python asyncio, FastAPI BackgroundTasks, SQLAlchemy async, Alembic, pytest

---

### Task 1: Create the `@async_retry` decorator

**Files:**
- Create: `src/core/retry.py`
- Test: `tests/unit/test_retry.py`

**Step 1: Write the failing test**

Create `tests/unit/test_retry.py`:

```python
"""Unit tests for src/core/retry.py — async_retry decorator."""

import asyncio
import pytest

from src.core.retry import async_retry


class TestAsyncRetry:
    """Tests for the @async_retry decorator."""

    async def test_returns_on_first_success(self):
        call_count = 0

        @async_retry(max_attempts=3, backoff_base=0.01)
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    async def test_retries_on_failure_then_succeeds(self):
        call_count = 0

        @async_retry(max_attempts=3, backoff_base=0.01)
        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient error")
            return "ok"

        result = await fail_then_succeed()
        assert result == "ok"
        assert call_count == 3

    async def test_raises_after_all_attempts_exhausted(self):
        call_count = 0

        @async_retry(max_attempts=3, backoff_base=0.01)
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("permanent error")

        with pytest.raises(RuntimeError, match="permanent error"):
            await always_fail()
        assert call_count == 3

    async def test_exponential_backoff_timing(self):
        """Verify that retries take at least the expected backoff time."""
        call_count = 0

        @async_retry(max_attempts=3, backoff_base=0.05)
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        start = asyncio.get_event_loop().time()
        with pytest.raises(RuntimeError):
            await always_fail()
        elapsed = asyncio.get_event_loop().time() - start

        # backoff_base=0.05: sleep 0.05 + 0.10 = 0.15s minimum
        assert elapsed >= 0.14  # small tolerance
        assert call_count == 3

    async def test_default_parameters(self):
        call_count = 0

        @async_retry()
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            await always_fail()
        # default max_attempts=3
        assert call_count == 3
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_retry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.retry'`

**Step 3: Write minimal implementation**

Create `src/core/retry.py`:

```python
"""Async retry decorator with exponential backoff."""

import asyncio
import logging
from functools import wraps
from typing import TypeVar, Callable, Any

logger = logging.getLogger(__name__)

T = TypeVar("T")


def async_retry(
    max_attempts: int = 3,
    backoff_base: float = 2.0,
) -> Callable:
    """
    Decorator that retries an async function on exception.

    Uses exponential backoff: sleeps backoff_base * 2^(attempt-1) seconds
    between retries (i.e. backoff_base after first failure,
    backoff_base*2 after second, etc.).

    Args:
        max_attempts: Total number of attempts (1 = no retry).
        backoff_base: Base delay in seconds for the first retry.
    """
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    last_exception = exc
                    if attempt < max_attempts:
                        delay = backoff_base * (2 ** (attempt - 1))
                        logger.warning(
                            f"{fn.__name__} attempt {attempt}/{max_attempts} "
                            f"failed: {exc}. Retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"{fn.__name__} failed after {max_attempts} attempts: {exc}"
                        )
            raise last_exception  # type: ignore[misc]
        return wrapper
    return decorator
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_retry.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/core/retry.py tests/unit/test_retry.py
git commit -m "feat: add @async_retry decorator with exponential backoff"
```

---

### Task 2: Apply `@async_retry` to image generation

**Files:**
- Modify: `src/core/image_generator.py:136-222` (OpenRouterImageGenerator.generate)
- Modify: `src/core/image_generator.py:293-334` (BookImageGenerator.generate_image)
- Test: `tests/unit/test_image_retry.py`

**Context:** Currently `OpenRouterImageGenerator.generate()` catches all exceptions and returns `GeneratedImage(success=False)`. For the retry decorator to work, we need the generation call to **raise** on failure. The approach: add a private `_generate_once()` method that raises `ImageGenerationError` on failure, decorate it with `@async_retry`, and call it from `generate_image()`.

**Step 1: Write the failing test**

Create `tests/unit/test_image_retry.py`:

```python
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
        original_generate = gen.generate

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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_image_retry.py -v`
Expected: FAIL with `ImportError: cannot import name 'ImageGenerationError'`

**Step 3: Write minimal implementation**

Modify `src/core/image_generator.py`:

1. Add `ImageGenerationError` exception class after the imports (around line 19):

```python
class ImageGenerationError(Exception):
    """Raised when a single image generation attempt fails."""
    pass
```

2. Add a `_generate_with_retry` method to `BookImageGenerator` (after `_upload_image`, around line 291). This method wraps the generator call and raises on failure so the decorator can retry:

```python
    @async_retry(max_attempts=3, backoff_base=2.0)
    async def _generate_with_retry(self, prompt: str) -> GeneratedImage:
        """Generate a single image, raising on failure so @async_retry can retry."""
        result = await self.generator.generate(prompt)
        if not result.success:
            raise ImageGenerationError(result.error or "Unknown image generation error")
        return result
```

3. Update `generate_image` (lines 326-327) to call `_generate_with_retry` instead of `self.generator.generate(prompt)`, catching `ImageGenerationError` to return a failed `GeneratedImage`:

Replace:
```python
        # Generate new image
        result = await self.generator.generate(prompt)
```

With:
```python
        # Generate new image (with automatic retry)
        try:
            result = await self._generate_with_retry(prompt)
        except ImageGenerationError as e:
            result = GeneratedImage(success=False, error=str(e), prompt_used=prompt)
```

4. Add the import at the top of the file:

```python
from src.core.retry import async_retry
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_image_retry.py -v`
Expected: All 3 tests PASS

**Step 5: Run existing tests to check for regressions**

Run: `pytest tests/ -v`
Expected: All existing tests still PASS

**Step 6: Commit**

```bash
git add src/core/image_generator.py tests/unit/test_image_retry.py
git commit -m "feat: add automatic retry with exponential backoff to image generation"
```

---

### Task 3: Add database columns for retry tracking

**Files:**
- Modify: `src/db/models.py:172-214` (GeneratedImage model)
- Create: `alembic/versions/e6f7a8b9c0d1_add_retry_columns_to_generated_images.py`

**Step 1: Add columns to the SQLAlchemy model**

In `src/db/models.py`, add two columns to the `GeneratedImage` class (after the `cached` column, line 195):

```python
    retry_attempt: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    retried_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

**Step 2: Create the Alembic migration**

Create `alembic/versions/e6f7a8b9c0d1_add_retry_columns_to_generated_images.py`:

```python
"""add retry columns to generated_images

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-02-08 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "generated_images",
        sa.Column("retry_attempt", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column(
        "generated_images",
        sa.Column("retried_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("generated_images", "retried_at")
    op.drop_column("generated_images", "retry_attempt")
```

**Step 3: Run existing tests to verify model changes don't break anything**

Run: `pytest tests/ -v`
Expected: All tests PASS (no test touches these new columns yet)

**Step 4: Commit**

```bash
git add src/db/models.py alembic/versions/e6f7a8b9c0d1_add_retry_columns_to_generated_images.py
git commit -m "feat: add retry_attempt and retried_at columns to generated_images"
```

---

### Task 4: Add repository helpers for retry and PDF replacement

**Files:**
- Modify: `src/db/repository.py`
- Test: `tests/unit/test_repository_retry.py`

**Step 1: Write the failing tests**

Create `tests/unit/test_repository_retry.py`:

```python
"""Tests for retry-related repository functions."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from sqlalchemy import select, update, delete

from src.db import repository as repo
from src.db.models import GeneratedImage, GeneratedPdf


class TestGetFailedImagesForBook:
    async def test_calls_select_with_correct_filters(self):
        session = AsyncMock()
        book_job_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_failed_images_for_book(session, book_job_id)
        assert result == []
        session.execute.assert_awaited_once()


class TestResetImageForRetry:
    async def test_updates_image_fields(self):
        session = AsyncMock()
        image_id = uuid.uuid4()

        await repo.reset_image_for_retry(session, image_id, retry_attempt=1)
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()


class TestDeletePdfsForBook:
    async def test_deletes_pdfs_and_returns_r2_keys(self):
        session = AsyncMock()
        book_job_id = uuid.uuid4()

        mock_pdf1 = MagicMock()
        mock_pdf1.file_path = "pdfs/job1/booklet.pdf"
        mock_pdf2 = MagicMock()
        mock_pdf2.file_path = "pdfs/job1/review.pdf"

        mock_select_result = MagicMock()
        mock_select_result.scalars.return_value.all.return_value = [mock_pdf1, mock_pdf2]

        mock_delete_result = MagicMock()

        session.execute = AsyncMock(side_effect=[mock_select_result, mock_delete_result])

        r2_keys = await repo.delete_pdfs_for_book(session, book_job_id)
        assert r2_keys == ["pdfs/job1/booklet.pdf", "pdfs/job1/review.pdf"]
        assert session.execute.call_count == 2
        session.commit.assert_awaited_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_repository_retry.py -v`
Expected: FAIL with `AttributeError: module 'src.db.repository' has no attribute 'get_failed_images_for_book'`

**Step 3: Write minimal implementation**

Add to `src/db/repository.py` at the end of the file:

```python
async def get_failed_images_for_book(
    session: AsyncSession,
    book_job_id: uuid.UUID,
) -> list[GeneratedImage]:
    """Get all failed images for a book job."""
    result = await session.execute(
        select(GeneratedImage)
        .where(
            GeneratedImage.book_job_id == book_job_id,
            GeneratedImage.status == "failed",
        )
        .order_by(GeneratedImage.page_number)
    )
    return list(result.scalars().all())


async def reset_image_for_retry(
    session: AsyncSession,
    image_id: uuid.UUID,
    retry_attempt: int,
) -> None:
    """Reset a failed image to pending for retry."""
    from datetime import datetime, timezone

    await session.execute(
        update(GeneratedImage)
        .where(GeneratedImage.id == image_id)
        .values(
            status="pending",
            error=None,
            retry_attempt=retry_attempt,
            retried_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()


async def delete_pdfs_for_book(
    session: AsyncSession,
    book_job_id: uuid.UUID,
) -> list[str]:
    """Delete all PDF rows for a book and return their R2 keys for cleanup."""
    result = await session.execute(
        select(GeneratedPdf).where(GeneratedPdf.book_job_id == book_job_id)
    )
    pdfs = result.scalars().all()
    r2_keys = [pdf.file_path for pdf in pdfs]

    await session.execute(
        delete(GeneratedPdf).where(GeneratedPdf.book_job_id == book_job_id)
    )
    await session.commit()
    return r2_keys
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_repository_retry.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/db/repository.py tests/unit/test_repository_retry.py
git commit -m "feat: add repository helpers for retry and PDF replacement"
```

---

### Task 5: Add `BookRegenerateResponse` schema

**Files:**
- Modify: `src/api/schemas.py`

**Step 1: Add the schema**

Add to `src/api/schemas.py` after the `BookGenerateResponse` class (around line 76):

```python
class BookRegenerateResponse(BaseModel):
    """Response schema for book regeneration request."""

    job_id: str = Field(..., description="Book job identifier")
    status: str = Field(..., description="New job status")
    failed_image_count: int = Field(..., description="Number of failed images to retry")
    message: str = Field(..., description="Status message")
```

**Step 2: Run existing tests**

Run: `pytest tests/api/test_schemas.py -v`
Expected: All tests PASS (adding a new schema doesn't break anything)

**Step 3: Commit**

```bash
git add src/api/schemas.py
git commit -m "feat: add BookRegenerateResponse schema"
```

---

### Task 6: Add the `POST /books/{job_id}/regenerate` endpoint

**Files:**
- Modify: `src/api/routes/books.py`
- Test: `tests/api/test_regenerate_route.py`

**Step 1: Write the failing test**

Create `tests/api/test_regenerate_route.py`:

```python
"""Tests for POST /api/v1/books/{job_id}/regenerate endpoint."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from src.api.app import app
from src.api.deps import get_db, get_current_user_id


_TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_book_job(*, job_id=None, status="completed"):
    job = MagicMock()
    job.id = job_id or uuid.uuid4()
    job.status = status
    job.user_id = _TEST_USER_ID
    return job


def _make_failed_image(*, page_number=1, prompt="test prompt"):
    img = MagicMock()
    img.id = uuid.uuid4()
    img.page_number = page_number
    img.prompt = prompt
    img.retry_attempt = 0
    return img


@pytest.fixture
async def client():
    mock_session = AsyncMock()

    async def _override_db():
        return mock_session

    async def _override_user():
        return _TEST_USER_ID

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user_id] = _override_user

    with (
        patch("src.api.app.init_db", new_callable=AsyncMock),
        patch("src.api.app.close_db", new_callable=AsyncMock),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    app.dependency_overrides.clear()


class TestRegenerateBook:
    async def test_returns_202_with_failed_images(self, client):
        job_id = uuid.uuid4()
        job = _make_book_job(job_id=job_id, status="completed")
        failed_images = [
            _make_failed_image(page_number=2),
            _make_failed_image(page_number=5),
        ]

        with (
            patch(
                "src.api.routes.books.repo.get_book_job_for_user",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "src.api.routes.books.repo.get_failed_images_for_book",
                new_callable=AsyncMock,
                return_value=failed_images,
            ),
            patch(
                "src.api.routes.books.repo.update_book_job",
                new_callable=AsyncMock,
            ),
        ):
            resp = await client.post(f"/api/v1/books/{job_id}/regenerate")
            assert resp.status_code == 202
            data = resp.json()
            assert data["job_id"] == str(job_id)
            assert data["status"] == "pending"
            assert data["failed_image_count"] == 2

    async def test_404_for_nonexistent_job(self, client):
        job_id = uuid.uuid4()
        with patch(
            "src.api.routes.books.repo.get_book_job_for_user",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await client.post(f"/api/v1/books/{job_id}/regenerate")
            assert resp.status_code == 404

    async def test_400_for_pending_job(self, client):
        job_id = uuid.uuid4()
        job = _make_book_job(job_id=job_id, status="pending")
        with patch(
            "src.api.routes.books.repo.get_book_job_for_user",
            new_callable=AsyncMock,
            return_value=job,
        ):
            resp = await client.post(f"/api/v1/books/{job_id}/regenerate")
            assert resp.status_code == 400

    async def test_400_for_processing_job(self, client):
        job_id = uuid.uuid4()
        job = _make_book_job(job_id=job_id, status="processing")
        with patch(
            "src.api.routes.books.repo.get_book_job_for_user",
            new_callable=AsyncMock,
            return_value=job,
        ):
            resp = await client.post(f"/api/v1/books/{job_id}/regenerate")
            assert resp.status_code == 400

    async def test_200_when_no_failed_images(self, client):
        job_id = uuid.uuid4()
        job = _make_book_job(job_id=job_id, status="completed")
        with (
            patch(
                "src.api.routes.books.repo.get_book_job_for_user",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "src.api.routes.books.repo.get_failed_images_for_book",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            resp = await client.post(f"/api/v1/books/{job_id}/regenerate")
            assert resp.status_code == 200
            data = resp.json()
            assert data["failed_image_count"] == 0
            assert "no failed images" in data["message"].lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_regenerate_route.py -v`
Expected: FAIL (404 because route doesn't exist yet)

**Step 3: Write minimal implementation**

Add to `src/api/routes/books.py`:

1. Add the import for the new schema (at the top, in the imports from `src.api.schemas`):

```python
from src.api.schemas import (
    BookGenerateRequest,
    BookGenerateResponse,
    BookRegenerateResponse,
    JobStatus,
    ...
)
```

2. Add the `_regenerate_book_task` background function (after `_generate_book_task`, around line 330):

```python
async def _regenerate_book_task(
    job_id: str, failed_images: list, user_id: uuid.UUID
) -> None:
    """
    Background task to retry failed images and regenerate PDFs.
    """
    logger.info(f"[{job_id}] Starting book regeneration task for {len(failed_images)} failed images")

    session_factory = get_session_factory()
    if session_factory is None:
        logger.error(f"[{job_id}] Database not initialized")
        return

    storage = get_storage()

    async with session_factory() as session:
        try:
            await repo.update_book_job(
                session, uuid.UUID(job_id),
                status="processing",
                progress=f"Retrying {len(failed_images)} failed images...",
            )

            from src.core.image_generator import ImageConfig, OpenRouterImageGenerator, GeneratedImage as GenImg, ImageGenerationError
            from src.core.retry import async_retry

            image_config = ImageConfig()
            generator = OpenRouterImageGenerator(image_config)

            # Wrap generator.generate with retry
            @async_retry(max_attempts=3, backoff_base=2.0)
            async def generate_with_retry(prompt: str) -> GenImg:
                result = await generator.generate(prompt)
                if not result.success:
                    raise ImageGenerationError(result.error or "Unknown error")
                return result

            # Retry each failed image
            for img in failed_images:
                image_id = img.id
                prompt = img.prompt
                page_number = img.page_number
                retry_attempt = img.retry_attempt + 1

                logger.info(f"[{job_id}] Retrying page {page_number} (attempt #{retry_attempt})")

                await repo.reset_image_for_retry(session, image_id, retry_attempt)

                try:
                    result = await generate_with_retry(prompt)
                    # Upload to R2
                    r2_key = f"images/{job_id}/page_{page_number}.png"
                    await storage.upload_bytes(result.image_data, r2_key, "image/png")
                    file_size = len(result.image_data) if result.image_data else None

                    await repo.update_generated_image(
                        session, image_id,
                        status="completed",
                        r2_key=r2_key,
                        file_size_bytes=file_size,
                        error=None,
                    )
                    logger.info(f"[{job_id}] Page {page_number} retry succeeded")

                except ImageGenerationError as e:
                    await repo.update_generated_image(
                        session, image_id,
                        status="failed",
                        error=str(e),
                    )
                    logger.warning(f"[{job_id}] Page {page_number} retry failed: {e}")

            # Regenerate PDFs with all successful images
            await repo.update_book_job(
                session, uuid.UUID(job_id),
                progress="Regenerating PDFs...",
            )

            # Get the book job to reconstruct book content
            job = await repo.get_book_job(session, uuid.UUID(job_id))
            if not job or not job.request_params:
                raise RuntimeError("Cannot regenerate: job or request_params missing")

            request = BookGenerateRequest(**job.request_params)

            # Process text into pages (same as original generation)
            processor = TextProcessor(
                max_sentences_per_page=2,
                max_chars_per_page=100,
                end_page_text=request.end_text,
            )

            if request.story_structured and request.story_structured.get("pages"):
                book_content = processor.process_structured(
                    story_data=request.story_structured,
                    author=request.author,
                    language=request.language,
                    custom_title=request.title,
                )
            else:
                book_content = processor.process_raw_story(
                    story=request.story,
                    title=request.title or "My Story",
                    author=request.author,
                    language=request.language,
                )

            # Gather all successful images (original + retried)
            all_images = await repo.get_images_for_book(session, uuid.UUID(job_id))
            images: dict[int, bytes] = {}
            for img_row in all_images:
                if img_row.status == "completed" and img_row.r2_key:
                    image_data = await storage.download_bytes(img_row.r2_key)
                    if image_data:
                        images[img_row.page_number] = image_data

            # Delete old PDFs from R2 and DB
            old_r2_keys = await repo.delete_pdfs_for_book(session, uuid.UUID(job_id))
            for key in old_r2_keys:
                await storage.delete(key)

            # Generate new PDFs
            safe_title = "".join(
                c if c.isalnum() or c in " -_" else "_" for c in book_content.title
            )
            safe_title = safe_title.strip().replace(" ", "_")[:50]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            booklet_filename = f"{safe_title}_{timestamp}_booklet.pdf"
            review_filename = f"{safe_title}_{timestamp}_review.pdf"

            with tempfile.TemporaryDirectory() as tmp_dir:
                booklet_path = str(Path(tmp_dir) / booklet_filename)
                review_path = str(Path(tmp_dir) / review_filename)

                generate_both_pdfs(
                    content=book_content,
                    booklet_path=booklet_path,
                    review_path=review_path,
                    config=request,
                    images=images,
                )

                booklet_r2_key = f"pdfs/{job_id}/{booklet_filename}"
                review_r2_key = f"pdfs/{job_id}/{review_filename}"

                booklet_size = await storage.upload_file(
                    booklet_path, booklet_r2_key, "application/pdf"
                )
                review_size = await storage.upload_file(
                    review_path, review_r2_key, "application/pdf"
                )

            await repo.create_generated_pdf(
                session,
                book_job_id=uuid.UUID(job_id),
                user_id=user_id,
                pdf_type="booklet",
                filename=booklet_filename,
                file_path=booklet_r2_key,
                page_count=book_content.total_pages,
                file_size_bytes=booklet_size,
            )
            await repo.create_generated_pdf(
                session,
                book_job_id=uuid.UUID(job_id),
                user_id=user_id,
                pdf_type="review",
                filename=review_filename,
                file_path=review_r2_key,
                page_count=book_content.total_pages,
                file_size_bytes=review_size,
            )

            await repo.update_book_job(
                session, uuid.UUID(job_id),
                status="completed",
                progress="Book regeneration completed!",
                booklet_filename=booklet_filename,
                review_filename=review_filename,
            )
            logger.info(f"[{job_id}] Book regeneration completed successfully!")

        except Exception as e:
            logger.error(f"[{job_id}] Book regeneration failed: {str(e)}", exc_info=True)
            try:
                async with session_factory() as err_session:
                    await repo.update_book_job(
                        err_session, uuid.UUID(job_id),
                        status="failed",
                        error=str(e),
                        progress=f"Regeneration failed: {str(e)}",
                    )
            except Exception as err_exc:
                logger.error(
                    f"[{job_id}] Could not record failure: {err_exc}",
                    exc_info=True,
                )
```

3. Add the endpoint (after the existing endpoints):

```python
@router.post(
    "/{job_id}/regenerate",
    response_model=BookRegenerateResponse,
    responses={
        200: {"description": "No failed images to retry"},
        202: {"description": "Regeneration started"},
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def regenerate_book(
    job_id: str,
    background_tasks: BackgroundTasks,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> BookRegenerateResponse:
    """
    Retry failed images for a book and regenerate PDFs.

    Finds all images with status='failed', retries them with automatic
    retry (3 attempts with exponential backoff), then regenerates both
    booklet and review PDFs, replacing the old ones.
    """
    job = await repo.get_book_job_for_user(db, uuid.UUID(job_id), user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in ("pending", "processing"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot regenerate: job is still {job.status}",
        )

    failed_images = await repo.get_failed_images_for_book(db, uuid.UUID(job_id))

    if not failed_images:
        return BookRegenerateResponse(
            job_id=job_id,
            status=job.status,
            failed_image_count=0,
            message="No failed images to retry.",
        )

    await repo.update_book_job(db, uuid.UUID(job_id), status="pending")

    background_tasks.add_task(
        _regenerate_book_task, job_id, failed_images, user_id
    )

    return BookRegenerateResponse(
        job_id=job_id,
        status="pending",
        failed_image_count=len(failed_images),
        message=f"Regeneration started. Retrying {len(failed_images)} failed images.",
    )
```

Note: The endpoint returns status code 200 (default) when no failed images, and we need to explicitly return 202 when starting regeneration. Update the endpoint to use `Response` to set 202:

Add to imports:
```python
from fastapi.responses import RedirectResponse, JSONResponse
```

And change the return for the regeneration case:
```python
    response = BookRegenerateResponse(
        job_id=job_id,
        status="pending",
        failed_image_count=len(failed_images),
        message=f"Regeneration started. Retrying {len(failed_images)} failed images.",
    )
    return JSONResponse(content=response.model_dump(), status_code=202)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_regenerate_route.py -v`
Expected: All 5 tests PASS

**Step 5: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/api/routes/books.py src/api/schemas.py tests/api/test_regenerate_route.py
git commit -m "feat: add POST /books/{job_id}/regenerate endpoint for retrying failed images"
```

---

### Task 7: Final integration verification

**Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 2: Verify the API docs render correctly**

Run: `python -c "from src.api.app import app; print('App imports OK')"`
Expected: No import errors

**Step 3: Final commit (if any fixups needed)**

```bash
git add -A
git commit -m "chore: final cleanup for image retry mechanism"
```
