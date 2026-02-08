"""
Book generation endpoints.
"""

import os
import uuid
import hashlib
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    BookGenerateRequest,
    BookGenerateResponse,
    BookRegenerateResponse,
    BookImageStatusResponse,
    FailedImageItem,
    JobStatus,
    BookListItem,
    BookListResponse,
    GeneratedBookItem,
    GeneratedBookListResponse,
    ErrorResponse,
)
from src.api.deps import get_db, get_current_user_id
from src.core.config import LLMConfig
from src.core.llm_connector import analyze_story_for_visuals
from src.core.text_processor import TextProcessor, validate_book_content
from src.core.pdf_generator import generate_both_pdfs
from src.core.storage import get_storage
from src.db.engine import get_session_factory
from src.db import repository as repo

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/books", tags=["Books"])


async def _generate_book_task(
    job_id: str, request: BookGenerateRequest, user_id: uuid.UUID
) -> None:
    """
    Background task to generate the book.
    Uses its own DB session (background tasks run outside FastAPI dependency injection).
    """
    logger.info(f"[{job_id}] Starting book generation task")
    logger.info(f"[{job_id}] Title: {request.title}")

    session_factory = get_session_factory()
    if session_factory is None:
        logger.error(f"[{job_id}] Database not initialized, cannot run background task")
        return

    storage = get_storage()

    async with session_factory() as session:
        try:
            await repo.update_book_job(
                session, uuid.UUID(job_id),
                status="processing", progress="Starting book generation...",
            )
            logger.info(f"[{job_id}] Status updated to 'processing'")

            story_text = request.story
            logger.debug(f"[{job_id}] Story length: {len(story_text)} characters")

            logger.info(f"[{job_id}] Book settings: age {request.age_min}-{request.age_max}, language: {request.language}")

            llm_config = LLMConfig()

            # Process text into pages (story text used as-is)
            logger.info(f"[{job_id}] Processing text into pages...")
            await repo.update_book_job(
                session, uuid.UUID(job_id),
                progress="Processing text into pages...",
            )
            processor = TextProcessor(
                max_sentences_per_page=2,
                max_chars_per_page=100,
                end_page_text=request.end_text,
            )

            if request.story_structured and request.story_structured.get("pages"):
                logger.info(f"[{job_id}] Using process_structured (structured JSON input)")
                book_content = processor.process_structured(
                    story_data=request.story_structured,
                    author=request.author,
                    language=request.language,
                    custom_title=request.title,
                )
            else:
                logger.info(f"[{job_id}] Using process_raw_story (text input)")
                book_content = processor.process_raw_story(
                    story=story_text,
                    title=request.title or "My Story",
                    author=request.author,
                    language=request.language,
                )

            await repo.update_book_job(
                session, uuid.UUID(job_id),
                title=book_content.title,
                total_pages=book_content.total_pages,
            )
            logger.info(f"[{job_id}] Book content created: '{book_content.title}', {book_content.total_pages} pages")

            # Validate
            warnings = validate_book_content(book_content)
            if warnings:
                logger.warning(f"[{job_id}] Content warnings: {warnings}")
                await repo.update_book_job(
                    session, uuid.UUID(job_id),
                    progress=f"Warnings: {', '.join(warnings)}",
                )

            # Generate images if requested
            images = None
            visual_context = None
            if request.generate_images:
                from src.core.image_generator import ImageConfig, BookImageGenerator

                logger.info(f"[{job_id}] Starting image generation...")
                await repo.update_book_job(
                    session, uuid.UUID(job_id),
                    progress="Analyzing story for visual consistency...",
                )

                # Analyze story for visual context (characters, setting, etc.)
                if llm_config.validate():
                    logger.info(f"[{job_id}] Analyzing story for visual context...")
                    visual_context, analysis_response = await analyze_story_for_visuals(
                        story=story_text,
                        config=llm_config,
                    )
                    if analysis_response.success and not visual_context.is_empty():
                        logger.info(f"[{job_id}] Visual context extracted: {len(visual_context.characters)} characters, setting: {visual_context.setting[:50] if visual_context.setting else 'N/A'}...")
                        # Use suggested background color if not specified in request
                        if not request.background_color and visual_context.background_color:
                            request.background_color = visual_context.background_color
                            logger.info(f"[{job_id}] Using suggested background color: {visual_context.background_color}")
                    else:
                        logger.warning(f"[{job_id}] Could not extract visual context: {analysis_response.error if not analysis_response.success else 'empty response'}")
                else:
                    logger.warning(f"[{job_id}] No API key for story analysis, skipping visual context")

                await repo.update_book_job(
                    session, uuid.UUID(job_id),
                    progress="Generating AI illustrations...",
                )

                image_config = ImageConfig(
                    model=request.image_model,
                    image_style=request.image_style,
                    use_cache=request.use_image_cache,
                    text_on_image=request.text_on_image,
                )

                if image_config.validate():
                    logger.info(f"[{job_id}] Image config valid, model: {request.image_model}")

                    # DB-backed cache check function for cross-book cache.
                    # Uses its own session per call because asyncio.gather()
                    # runs these concurrently and a single async session
                    # cannot handle concurrent operations.
                    async def cache_check_fn(prompt_hash: str):
                        async with session_factory() as cache_session:
                            return await repo.find_cached_image_by_hash(cache_session, prompt_hash)

                    image_generator = BookImageGenerator(
                        image_config,
                        request,
                        visual_context,
                        storage=storage,
                        book_job_id=job_id,
                        cache_check_fn=cache_check_fn,
                    )

                    page_data = [
                        {
                            "page_number": p.page_number,
                            "content": p.content,
                            "page_type": p.page_type.value,
                        }
                        for p in book_content.pages
                    ]

                    logger.info(f"[{job_id}] Page data for image generation: {[(p['page_number'], p['page_type']) for p in page_data]}")

                    story_context = " ".join(
                        [
                            p.content
                            for p in book_content.pages
                            if p.page_type.value == "content"
                        ][:3]
                    )

                    logger.info(f"[{job_id}] Calling generate_all_images with {len(page_data)} pages")
                    image_results = await image_generator.generate_all_images(
                        pages=page_data,
                        story_context=story_context,
                    )
                    logger.info(f"[{job_id}] Image results: {[(pn, r.success, r.error if not r.success else 'OK') for pn, r in image_results.items()]}")

                    # Create DB rows for generated images
                    images = {}
                    for page_num, result in image_results.items():
                        prompt_hash = hashlib.md5(
                            (result.prompt_used or "").encode()
                        ).hexdigest()
                        file_size = len(result.image_data) if result.image_data else None

                        await repo.create_generated_image(
                            session,
                            book_job_id=uuid.UUID(job_id),
                            user_id=user_id,
                            page_number=page_num,
                            prompt=result.prompt_used or "",
                            prompt_hash=prompt_hash,
                            status="completed" if result.success else "failed",
                            r2_key=result.image_path if result.success else None,
                            file_size_bytes=file_size,
                            error=result.error,
                            cached=result.cached,
                        )

                        if result.success and result.image_data:
                            images[page_num] = result.image_data

                    logger.info(f"[{job_id}] Generated {len(images)} images successfully")
                else:
                    logger.warning(f"[{job_id}] Image config invalid (missing API key?)")

            # Generate PDFs
            logger.info(f"[{job_id}] Starting PDF generation...")
            await repo.update_book_job(
                session, uuid.UUID(job_id),
                progress="Generating PDF files...",
            )

            # Generate filenames
            safe_title = "".join(
                c if c.isalnum() or c in " -_" else "_" for c in book_content.title
            )
            safe_title = safe_title.strip().replace(" ", "_")[:50]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            booklet_filename = f"{safe_title}_{timestamp}_booklet.pdf"
            review_filename = f"{safe_title}_{timestamp}_review.pdf"

            # Generate PDFs in a temp directory, then upload to R2
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
                logger.info(f"[{job_id}] PDFs generated: {booklet_filename}, {review_filename}")

                # Upload to R2
                booklet_r2_key = f"pdfs/{job_id}/{booklet_filename}"
                review_r2_key = f"pdfs/{job_id}/{review_filename}"

                booklet_size = await storage.upload_file(
                    booklet_path, booklet_r2_key, "application/pdf"
                )
                review_size = await storage.upload_file(
                    review_path, review_r2_key, "application/pdf"
                )
                logger.info(f"[{job_id}] PDFs uploaded to R2")

            # Store PDF metadata with R2 keys
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

            # Update job status
            await repo.update_book_job(
                session, uuid.UUID(job_id),
                status="completed",
                progress="Book generation completed!",
                booklet_filename=booklet_filename,
                review_filename=review_filename,
            )
            logger.info(f"[{job_id}] Book generation completed successfully!")

        except Exception as e:
            logger.error(f"[{job_id}] Book generation failed: {str(e)}", exc_info=True)
            # Use a fresh session to record the failure — the original
            # session may be in a broken state (e.g. after a concurrent
            # operation error), which would prevent updating the job and
            # leave it stuck in "processing" forever.
            try:
                async with session_factory() as err_session:
                    await repo.update_book_job(
                        err_session, uuid.UUID(job_id),
                        status="failed",
                        error=str(e),
                        progress=f"Failed: {str(e)}",
                    )
            except Exception as err_exc:
                logger.error(
                    f"[{job_id}] Could not record failure status: {err_exc}",
                    exc_info=True,
                )


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


@router.post(
    "/generate",
    response_model=BookGenerateResponse,
    responses={400: {"model": ErrorResponse}},
)
async def generate_book(
    request: BookGenerateRequest,
    background_tasks: BackgroundTasks,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> BookGenerateResponse:
    """
    Generate a children's book from story text.

    Returns a job ID to track progress. Use `/books/{job_id}/status` to check status
    and `/books/{job_id}/download/{type}` to download the PDFs when complete.
    """
    if not request.story.strip():
        raise HTTPException(status_code=400, detail="Story text cannot be empty")

    if request.age_min > request.age_max:
        raise HTTPException(
            status_code=400, detail="age_min must be less than or equal to age_max"
        )

    # Create job in database
    job_id = uuid.uuid4()
    await repo.create_book_job(
        db, job_id=job_id, user_id=user_id,
        request_params=request.model_dump(),
    )

    # Start background task
    background_tasks.add_task(_generate_book_task, str(job_id), request, user_id)

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
        _regenerate_book_task, job_id, failed_images, user_id
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


@router.get(
    "/generated",
    response_model=GeneratedBookListResponse,
)
async def list_generated_books(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> GeneratedBookListResponse:
    """
    List completed books with download links for the authenticated user.
    """
    jobs = await repo.list_completed_books_for_user(db, user_id, limit=limit, offset=offset)
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
    return GeneratedBookListResponse(books=items, total=len(items))


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
    limit: int = 50,
    offset: int = 0,
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
    Delete a job and its associated files from R2.
    """
    job = await repo.get_book_job_for_user(db, uuid.UUID(job_id), user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    storage = get_storage()

    # Delete R2 objects: images and PDFs for this job
    await storage.delete_prefix(f"images/{job_id}/")
    await storage.delete_prefix(f"pdfs/{job_id}/")

    # Delete from database (cascades to generated_pdfs and generated_images)
    await repo.delete_book_job(db, uuid.UUID(job_id))

    return {"message": f"Job {job_id} deleted successfully"}
