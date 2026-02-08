# Image Status Endpoint Design

## Purpose

A dedicated GET endpoint for the frontend to check if a completed book has any failed images, enabling it to show a "retry" button that triggers the existing `POST /books/{job_id}/regenerate` endpoint.

## Endpoint

`GET /api/v1/books/{job_id}/images/status`

## Auth

Same as other book endpoints — `get_current_user_id` dependency, job scoped to user.

## Behavior

- Looks up the book job (scoped to user). Returns 404 if not found.
- Returns 400 if job status is `pending` or `processing` (images not finalized yet).
- Queries all images and failed images using existing repo functions.
- Returns image health summary with page-level detail for failures.

## Response Schema

`BookImageStatusResponse`:

```json
{
  "job_id": "uuid",
  "total_images": 8,
  "failed_images": 2,
  "has_failed_images": true,
  "failed_pages": [
    {"page_number": 2, "error": "API error: 503"},
    {"page_number": 5, "error": "timeout"}
  ]
}

`FailedImageItem`:

```json
{
  "page_number": 2,
  "error": "API error: 503"
}
```

## Existing Infrastructure Used

- `repo.get_book_job_for_user` — job lookup with user scoping
- `repo.get_images_for_book` — total image count
- `repo.get_failed_images_for_book` — failed images with page numbers and errors

No new repository functions needed.

## Frontend Usage

Called from the generated books list page (`GET /books/generated`) for each completed book to determine whether to show a retry/regenerate button.
