"""
Book generation endpoints.
"""

import os
import uuid
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    BookGenerateRequest,
    BookGenerateResponse,
    JobStatus,
    BookListItem,
    BookListResponse,
    ErrorResponse,
)
from src.api.deps import get_db, get_current_user_id
from src.core.config import BookConfig, LLMConfig
from src.core.llm_connector import analyze_story_for_visuals
from src.core.text_processor import TextProcessor, validate_book_content
from src.core.pdf_generator import generate_both_pdfs
from src.db.engine import get_session_factory
from src.db import repository as repo

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/books", tags=["Books"])

OUTPUT_DIR = "output"


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

    async with session_factory() as session:
        try:
            await repo.update_book_job(
                session, uuid.UUID(job_id),
                status="processing", progress="Starting book generation...",
            )
            logger.info(f"[{job_id}] Status updated to 'processing'")

            story_text = request.story
            logger.debug(f"[{job_id}] Story length: {len(story_text)} characters")

            # Configure book settings
            book_config = BookConfig(
                target_age_min=request.age_min,
                target_age_max=request.age_max,
                language=request.language,
                font_size=request.font_size,
                title_font_size=request.title_font_size,
                cover_title=request.title,
                author_name=request.author,
                end_page_text=request.end_text,
                text_on_image=request.text_on_image,
                background_color=request.background_color,
            )
            logger.info(f"[{job_id}] Book config created: age {request.age_min}-{request.age_max}, language: {request.language}")

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
                            book_config.background_color = visual_context.background_color
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
                    image_generator = BookImageGenerator(image_config, book_config, visual_context)

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

                    images = {}
                    for page_num, result in image_results.items():
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

            os.makedirs(OUTPUT_DIR, exist_ok=True)

            # Generate filenames
            safe_title = "".join(
                c if c.isalnum() or c in " -_" else "_" for c in book_content.title
            )
            safe_title = safe_title.strip().replace(" ", "_")[:50]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            booklet_filename = f"{safe_title}_{timestamp}_booklet.pdf"
            review_filename = f"{safe_title}_{timestamp}_review.pdf"

            booklet_path = str(Path(OUTPUT_DIR) / booklet_filename)
            review_path = str(Path(OUTPUT_DIR) / review_filename)

            generate_both_pdfs(
                content=book_content,
                booklet_path=booklet_path,
                review_path=review_path,
                config=book_config,
                images=images,
            )
            logger.info(f"[{job_id}] PDFs generated: {booklet_filename}, {review_filename}")

            # Store PDF metadata
            booklet_size = os.path.getsize(booklet_path) if os.path.exists(booklet_path) else None
            review_size = os.path.getsize(review_path) if os.path.exists(review_path) else None

            await repo.create_generated_pdf(
                session,
                book_job_id=uuid.UUID(job_id),
                user_id=user_id,
                pdf_type="booklet",
                filename=booklet_filename,
                file_path=booklet_path,
                page_count=book_content.total_pages,
                file_size_bytes=booklet_size,
            )
            await repo.create_generated_pdf(
                session,
                book_job_id=uuid.UUID(job_id),
                user_id=user_id,
                pdf_type="review",
                filename=review_filename,
                file_path=review_path,
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
            await repo.update_book_job(
                session, uuid.UUID(job_id),
                status="failed",
                error=str(e),
                progress=f"Failed: {str(e)}",
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
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
    },
)
async def download_book(
    job_id: str,
    pdf_type: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """
    Download a generated PDF.

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

    file_path = Path(OUTPUT_DIR) / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on disk")

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/pdf",
    )


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
    Delete a job and its associated PDF files.
    """
    job = await repo.get_book_job_for_user(db, uuid.UUID(job_id), user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Delete PDF files if they exist
    if job.booklet_filename:
        booklet_path = Path(OUTPUT_DIR) / job.booklet_filename
        if booklet_path.exists():
            booklet_path.unlink()

    if job.review_filename:
        review_path = Path(OUTPUT_DIR) / job.review_filename
        if review_path.exists():
            review_path.unlink()

    # Delete from database (cascades to generated_pdfs)
    await repo.delete_book_job(db, uuid.UUID(job_id))

    return {"message": f"Job {job_id} deleted successfully"}
