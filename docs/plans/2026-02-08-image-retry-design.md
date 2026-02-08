# Image Generation Retry Mechanism — Design

## Summary

Add automatic inline retries during image generation and a manual book regeneration endpoint to recover from failed images.

## Automatic Inline Retry

- Retry logic implemented as an `@async_retry` decorator in `src/core/retry.py`
- Configurable `max_attempts` (default 3) and `backoff_base` (default 2s)
- Exponential backoff: 2s after first failure, 4s after second
- Applied to the single-image generation call inside `BookImageGenerator`
- The decorated method does one attempt — raises on failure, returns on success
- `generate_image()` calls the decorated method, catches final failure, records to DB
- Only the final failure is recorded as `status='failed'` — intermediate failures are transient
- Cache check still happens before any generation attempt
- `asyncio.gather()` parallel generation is untouched

## Database Changes

Add two columns to `generated_images` table:

- `retry_attempt` (`Integer`, default `0`) — tracks manual retry count
- `retried_at` (`DateTime`, nullable) — timestamp of last manual retry

No changes to the status CHECK constraint — existing `'pending'`, `'completed'`, `'failed'` states are sufficient. A manual retry sets the row back to `'pending'`, then updates to `'completed'` or `'failed'` when done.

One new Alembic migration with defaults so existing rows are unaffected.

## Manual Retry Endpoint — Book Regeneration

**`POST /books/{job_id}/regenerate`**

Runs as a background task (same pattern as current book generation).

Flow:
1. Validate the book job exists and belongs to the authenticated user
2. Validate the job status is `'completed'` or `'failed'` — reject if still `'pending'`/in-progress
3. Set job status back to `'pending'`
4. Kick off a background task that:
   - Queries all `generated_images` for this job
   - Finds rows with `status='failed'`
   - For each failed image: set to `'pending'`, increment `retry_attempt`, set `retried_at=now()`
   - Retry each failed image using the stored `prompt` (with `@async_retry` — 3 attempts with exponential backoff)
   - Update each image row to `'completed'` or `'failed'`
   - Regenerate both PDFs (booklet + review) using all successful images (original + newly recovered)
   - Delete old PDFs from R2 and replace the `generated_pdfs` DB rows with newly generated ones — old PDFs are fully replaced, not kept alongside
   - Update job status to `'completed'`
5. Return immediately with job ID and `status='pending'`

Response schema: `BookRegenerateResponse` with `job_id`, `status`, `failed_image_count`.

## File Changes

### New files
- `src/core/retry.py` — `@async_retry` decorator with configurable `max_attempts` and `backoff_base`
- Alembic migration — adds `retry_attempt` and `retried_at` columns to `generated_images`

### Modified files
- `src/core/image_generator.py` — Apply `@async_retry` decorator to single-image generation call
- `src/api/routes/books.py` — Add `POST /books/{job_id}/regenerate` endpoint + `_regenerate_book_task` background task
- `src/api/schemas.py` — Add `BookRegenerateResponse` schema
- `src/db/models.py` — Add `retry_attempt` and `retried_at` columns to `GeneratedImage`
- `src/db/repository.py` — Add `get_failed_images_for_book()`, `reset_image_for_retry()`, and PDF replacement helpers

### Not changed
- `src/core/pdf_generator.py` — PDF generation logic stays the same, just called again
- `src/core/llm_connector.py` — No changes
- Existing endpoints — No breaking changes
