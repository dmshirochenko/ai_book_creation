"""
Book generation endpoints.
"""

import uuid
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.requests import Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    BookGenerateRequest,
    BookGenerateResponse,
    BookRegenerateResponse,
    BookImageStatusResponse,
    FailedImageItem,
    BatchImageStatusRequest,
    BatchImageStatusItem,
    BatchImageStatusResponse,
    JobStatus,
    BookListItem,
    BookListResponse,
    GeneratedBookItem,
    GeneratedBookListResponse,
    ErrorResponse,
)
from src.api.deps import get_db, get_current_user_id
from src.core.storage import get_storage
from src.db import repository as repo
from src.tasks.book_tasks import generate_book_task, regenerate_book_task
from src.services.credit_service import CreditService, InsufficientCreditsError
from src.api.rate_limit import limiter

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/books", tags=["Books"])


@router.post(
    "/generate",
    response_model=BookGenerateResponse,
    responses={400: {"model": ErrorResponse}},
)
@limiter.limit("3/minute")
async def generate_book(
    request: Request,
    body: BookGenerateRequest,
    background_tasks: BackgroundTasks,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> BookGenerateResponse:
    """
    Generate a children's book from story text.

    Returns a job ID to track progress. Use `/books/{job_id}/status` to check status
    and `/books/{job_id}/download/{type}` to download the PDFs when complete.
    """
    if not body.story.strip():
        raise HTTPException(status_code=400, detail="Story text cannot be empty")

    if body.age_min > body.age_max:
        raise HTTPException(
            status_code=400, detail="age_min must be less than or equal to age_max"
        )

    job_id = uuid.uuid4()

    # Calculate page count for cost estimation
    if body.story_structured and body.story_structured.pages:
        page_count = len(body.story_structured.pages)
    else:
        from src.core.text_processor import TextProcessor
        processor = TextProcessor(max_sentences_per_page=2, max_chars_per_page=100)
        book_content = processor.process_raw_story(
            story=body.story, title=body.title or "My Story",
            author=body.author, language=body.language,
        )
        page_count = book_content.total_pages

    if page_count < 1:
        raise HTTPException(status_code=400, detail="Book must have at least one page")

    # Reserve credits
    credit_service = CreditService(db)
    try:
        book_cost = await credit_service.calculate_book_cost(
            pages=page_count, with_images=body.generate_images,
        )
        pricing_snapshot = await credit_service.get_pricing()
        cost_per_page_key = "page_with_images" if body.generate_images else "page_without_images"
        usage_log_id = await credit_service.reserve(
            user_id=user_id,
            amount=book_cost,
            job_id=job_id,
            job_type="book",
            description=f"Book: {body.title or 'Untitled'} ({page_count} pages{'  with images' if body.generate_images else ''})",
            metadata={
                "title": body.title,
                "pages": page_count,
                "with_images": body.generate_images,
                "cost_per_page": float(pricing_snapshot.get(cost_per_page_key, 0)),
                "total_cost": float(book_cost),
                "pricing_snapshot": {k: float(v) for k, v in pricing_snapshot.items()},
            },
        )
    except InsufficientCreditsError as e:
        raise HTTPException(
            status_code=402,
            detail={
                "message": "Insufficient credits",
                "balance": float(e.balance),
                "required": float(e.required),
            },
        )

    # Create job in database — release reserved credits if this fails
    try:
        await repo.create_book_job(
            db, job_id=job_id, user_id=user_id,
            request_params=body.model_dump(),
        )
    except Exception:
        await credit_service.release(usage_log_id, user_id)
        raise

    # Start background task
    background_tasks.add_task(generate_book_task, str(job_id), body, user_id, usage_log_id)

    return BookGenerateResponse(
        job_id=str(job_id),
        message="Book generation started. Use /books/{job_id}/status to track progress.",
    )


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
        regenerate_book_task, job_id, failed_images, user_id
    )

    response = BookRegenerateResponse(
        job_id=job_id,
        status="pending",
        failed_image_count=len(failed_images),
        message=f"Regeneration started. Retrying {len(failed_images)} failed images.",
    )
    return JSONResponse(content=response.model_dump(), status_code=202)


@router.get(
    "/{job_id}/images/status",
    response_model=BookImageStatusResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def get_image_status(
    job_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> BookImageStatusResponse:
    """
    Check if a completed book has any failed images.

    Used by the frontend to determine whether to show a "retry" button
    for the book's failed illustrations.
    """
    job = await repo.get_book_job_for_user(db, uuid.UUID(job_id), user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in ("pending", "processing"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot check image status: job is still {job.status}",
        )

    all_images = await repo.get_images_for_book(db, uuid.UUID(job_id))
    failed_images = await repo.get_failed_images_for_book(db, uuid.UUID(job_id))

    return BookImageStatusResponse(
        job_id=job_id,
        total_images=len(all_images),
        failed_images=len(failed_images),
        has_failed_images=len(failed_images) > 0,
        failed_pages=[
            FailedImageItem(page_number=img.page_number, error=img.error)
            for img in failed_images
        ],
    )


@router.post(
    "/images/status/batch",
    response_model=BatchImageStatusResponse,
)
async def batch_image_status(
    request: BatchImageStatusRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> BatchImageStatusResponse:
    """
    Get image status for multiple books in a single request.

    Returns failed image counts for each book, used by the My Books page
    to show "fix broken images" buttons without N+1 queries.
    """
    job_ids = [uuid.UUID(jid) for jid in request.job_ids]
    rows = await repo.get_batch_image_status(db, job_ids, user_id)
    return BatchImageStatusResponse(
        statuses=[BatchImageStatusItem(**row) for row in rows]
    )


@router.get(
    "/generated",
    response_model=GeneratedBookListResponse,
)
async def list_generated_books(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> GeneratedBookListResponse:
    """
    List completed books with download links for the authenticated user.
    """
    jobs = await repo.list_completed_books_for_user(db, user_id, limit=limit, offset=offset)
    total_count = await repo.count_completed_books_for_user(db, user_id)
    items = [
        GeneratedBookItem(
            job_id=str(j.id),
            title=j.title or "Untitled",
            booklet_url=f"/api/v1/books/{j.id}/download/booklet",
            review_url=f"/api/v1/books/{j.id}/download/review",
            created_at=j.created_at.isoformat() if j.created_at else "",
        )
        for j in jobs
    ]
    return GeneratedBookListResponse(books=items, total=total_count)


@router.get(
    "/{job_id}/status",
    response_model=JobStatus,
    responses={404: {"model": ErrorResponse}},
)
async def get_job_status(
    job_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> JobStatus:
    """
    Get the status of a book generation job.
    """
    job = await repo.get_book_job_for_user(db, uuid.UUID(job_id), user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatus(
        job_id=str(job.id),
        status=job.status,
        progress=job.progress,
        title=job.title,
        total_pages=job.total_pages,
        booklet_filename=job.booklet_filename,
        review_filename=job.review_filename,
        error=job.error,
    )


@router.get(
    "/{job_id}/download/{pdf_type}",
    responses={
        307: {"description": "Redirect to presigned R2 URL"},
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
    },
)
async def download_book(
    job_id: str,
    pdf_type: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    Download a generated PDF via presigned R2 URL redirect.

    - `pdf_type`: Either "booklet" (for printing) or "review" (for screen reading)
    """
    job = await repo.get_book_job_for_user(db, uuid.UUID(job_id), user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Book not ready. Current status: {job.status}",
        )

    if pdf_type == "booklet":
        filename = job.booklet_filename
    elif pdf_type == "review":
        filename = job.review_filename
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid pdf_type. Use 'booklet' or 'review'",
        )

    if not filename:
        raise HTTPException(status_code=404, detail="PDF file not found")

    r2_key = f"pdfs/{job_id}/{filename}"
    storage = get_storage()
    presigned_url = await storage.generate_presigned_url(
        r2_key, expiration=3600, response_filename=filename
    )

    return RedirectResponse(url=presigned_url, status_code=307)


@router.get(
    "",
    response_model=BookListResponse,
)
async def list_books(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> BookListResponse:
    """
    List all book generation jobs for the authenticated user.
    """
    jobs = await repo.list_book_jobs_for_user(db, user_id, limit=limit, offset=offset)
    items = [
        BookListItem(
            job_id=str(j.id),
            title=j.title or "Untitled",
            created_at=j.created_at.isoformat() if j.created_at else "",
            status=j.status,
        )
        for j in jobs
    ]
    return BookListResponse(books=items, total=len(items))


@router.delete(
    "/{job_id}",
    responses={404: {"model": ErrorResponse}},
)
async def delete_job(
    job_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Soft-delete a job by setting its status to 'deleted'.
    """
    job = await repo.get_book_job_for_user(db, uuid.UUID(job_id), user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    await repo.update_book_job(db, uuid.UUID(job_id), status="deleted")

    return {"message": f"Job {job_id} deleted successfully"}
