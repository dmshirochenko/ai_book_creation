"""
Book generation endpoints.
"""

import os
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from src.api.schemas import (
    BookGenerateRequest,
    BookGenerateResponse,
    JobStatus,
    ErrorResponse,
)
from src.core.config import BookConfig, LLMConfig
from src.core.llm_connector import adapt_story_for_children
from src.core.text_processor import TextProcessor, validate_book_content
from src.core.pdf_generator import generate_both_pdfs

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/books", tags=["Books"])

# In-memory job storage (use Redis/database in production)
jobs: Dict[str, JobStatus] = {}

OUTPUT_DIR = "output"


def _generate_book_task(job_id: str, request: BookGenerateRequest) -> None:
    """
    Background task to generate the book.
    Updates job status as it progresses.
    """
    logger.info(f"[{job_id}] Starting book generation task")
    logger.info(f"[{job_id}] Title: {request.title}, Skip adaptation: {request.skip_adaptation}")
    
    try:
        jobs[job_id].status = "processing"
        jobs[job_id].progress = "Starting book generation..."
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
        )
        logger.info(f"[{job_id}] Book config created: age {request.age_min}-{request.age_max}, language: {request.language}")

        llm_config = LLMConfig()

        # Adapt story (or use as-is)
        if request.skip_adaptation:
            logger.info(f"[{job_id}] Skipping LLM adaptation (skip_adaptation=True)")
            jobs[job_id].progress = "Skipping LLM adaptation..."
            adapted_text = story_text
        else:
            if not llm_config.validate():
                logger.warning(f"[{job_id}] No OpenRouter API key configured, using story as-is")
                jobs[job_id].progress = "No API key, using story as-is..."
                adapted_text = story_text
            else:
                logger.info(f"[{job_id}] Adapting story with LLM...")
                jobs[job_id].progress = "Adapting story with LLM..."
                response = adapt_story_for_children(
                    story=story_text,
                    config=llm_config,
                    target_age_min=request.age_min,
                    target_age_max=request.age_max,
                    language=request.language,
                )
                if not response.success:
                    logger.warning(f"[{job_id}] LLM adaptation failed: {response.error}, using original story")
                    adapted_text = story_text
                else:
                    logger.info(f"[{job_id}] LLM adaptation successful, adapted text length: {len(response.content)}")
                    adapted_text = response.content

        # Process text into pages
        logger.info(f"[{job_id}] Processing text into pages...")
        jobs[job_id].progress = "Processing text into pages..."
        processor = TextProcessor(
            max_sentences_per_page=2,
            max_chars_per_page=100,
            end_page_text=request.end_text,
        )

        if request.skip_adaptation and request.title:
            logger.info(f"[{job_id}] Using process_raw_story (pre-formatted input)")
            book_content = processor.process_raw_story(
                story=adapted_text,
                title=request.title,
                author=request.author,
                language=request.language,
            )
        else:
            logger.info(f"[{job_id}] Using standard process (LLM-formatted input)")
            book_content = processor.process(
                adapted_text=adapted_text,
                author=request.author,
                language=request.language,
                custom_title=request.title,
            )

        jobs[job_id].title = book_content.title
        jobs[job_id].total_pages = book_content.total_pages
        logger.info(f"[{job_id}] Book content created: '{book_content.title}', {book_content.total_pages} pages")

        # Validate
        warnings = validate_book_content(book_content)
        if warnings:
            logger.warning(f"[{job_id}] Content warnings: {warnings}")
            jobs[job_id].progress = f"Warnings: {', '.join(warnings)}"

        # Generate images if requested
        images = None
        if request.generate_images:
            from src.core.image_generator import ImageConfig, BookImageGenerator

            logger.info(f"[{job_id}] Starting image generation...")
            jobs[job_id].progress = "Generating AI illustrations..."

            image_config = ImageConfig(
                model=request.image_model,
                image_style=request.image_style,
                use_cache=request.use_image_cache,
                text_on_image=request.text_on_image,
            )

            if image_config.validate():
                logger.info(f"[{job_id}] Image config valid, model: {request.image_model}")
                image_generator = BookImageGenerator(image_config, book_config)

                page_data = [
                    {
                        "page_number": p.page_number,
                        "content": p.content,
                        "page_type": p.page_type.value,
                    }
                    for p in book_content.pages
                ]

                story_context = " ".join(
                    [
                        p.content
                        for p in book_content.pages
                        if p.page_type.value == "content"
                    ][:3]
                )

                image_results = image_generator.generate_all_images(
                    pages=page_data,
                    story_context=story_context,
                )

                images = {}
                for page_num, result in image_results.items():
                    if result.success and result.image_data:
                        images[page_num] = result.image_data
                logger.info(f"[{job_id}] Generated {len(images)} images successfully")
            else:
                logger.warning(f"[{job_id}] Image config invalid (missing API key?)")

        # Generate PDFs
        logger.info(f"[{job_id}] Starting PDF generation...")
        jobs[job_id].progress = "Generating PDF files..."

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

        # Update job status
        jobs[job_id].status = "completed"
        jobs[job_id].progress = "Book generation completed!"
        jobs[job_id].booklet_filename = booklet_filename
        jobs[job_id].review_filename = review_filename
        logger.info(f"[{job_id}] ✅ Book generation completed successfully!")

    except Exception as e:
        logger.error(f"[{job_id}] ❌ Book generation failed: {str(e)}", exc_info=True)
        jobs[job_id].status = "failed"
        jobs[job_id].error = str(e)
        jobs[job_id].progress = f"Failed: {str(e)}"


@router.post(
    "/generate",
    response_model=BookGenerateResponse,
    responses={400: {"model": ErrorResponse}},
)
async def generate_book(
    request: BookGenerateRequest,
    background_tasks: BackgroundTasks,
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

    # Create job
    job_id = str(uuid.uuid4())
    jobs[job_id] = JobStatus(
        job_id=job_id,
        status="pending",
        progress="Job created, waiting to start...",
    )

    # Start background task
    background_tasks.add_task(_generate_book_task, job_id, request)

    return BookGenerateResponse(
        job_id=job_id,
        message="Book generation started. Use /books/{job_id}/status to track progress.",
    )


@router.post(
    "/generate/file",
    response_model=BookGenerateResponse,
    responses={400: {"model": ErrorResponse}},
)
async def generate_book_from_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Text file containing the story"),
    title: Optional[str] = Form(None),
    author: str = Form("A Bedtime Story"),
    age_min: int = Form(2),
    age_max: int = Form(4),
    language: str = Form("English"),
    font_size: int = Form(24),
    title_font_size: int = Form(36),
    skip_adaptation: bool = Form(False),
    end_text: str = Form("The End"),
    generate_images: bool = Form(False),
    image_model: str = Form("google/gemini-3-pro-image-preview"),
    image_style: str = Form(
        "children's book illustration, soft watercolor style, gentle colors, simple shapes, cute and friendly"
    ),
    use_image_cache: bool = Form(True),
    text_on_image: bool = Form(False),
) -> BookGenerateResponse:
    """
    Generate a children's book from an uploaded text file.
    
    Returns a job ID to track progress.
    """
    # Read file content
    content = await file.read()
    try:
        story_text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400, detail="File must be a valid UTF-8 text file"
        )

    if not story_text.strip():
        raise HTTPException(status_code=400, detail="File is empty")

    # Create request object
    request = BookGenerateRequest(
        story=story_text,
        title=title,
        author=author,
        age_min=age_min,
        age_max=age_max,
        language=language,
        font_size=font_size,
        title_font_size=title_font_size,
        skip_adaptation=skip_adaptation,
        end_text=end_text,
        generate_images=generate_images,
        image_model=image_model,
        image_style=image_style,
        use_image_cache=use_image_cache,
        text_on_image=text_on_image,
    )

    # Create job
    job_id = str(uuid.uuid4())
    jobs[job_id] = JobStatus(
        job_id=job_id,
        status="pending",
        progress="Job created, waiting to start...",
    )

    # Start background task
    background_tasks.add_task(_generate_book_task, job_id, request)

    return BookGenerateResponse(
        job_id=job_id,
        message="Book generation started. Use /books/{job_id}/status to track progress.",
    )


@router.get(
    "/{job_id}/status",
    response_model=JobStatus,
    responses={404: {"model": ErrorResponse}},
)
async def get_job_status(job_id: str) -> JobStatus:
    """
    Get the status of a book generation job.
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return jobs[job_id]


@router.get(
    "/{job_id}/download/{pdf_type}",
    responses={
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
    },
)
async def download_book(job_id: str, pdf_type: str) -> FileResponse:
    """
    Download a generated PDF.
    
    - `pdf_type`: Either "booklet" (for printing) or "review" (for screen reading)
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

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


@router.delete(
    "/{job_id}",
    responses={404: {"model": ErrorResponse}},
)
async def delete_job(job_id: str) -> dict:
    """
    Delete a job and its associated PDF files.
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

    # Delete PDF files if they exist
    if job.booklet_filename:
        booklet_path = Path(OUTPUT_DIR) / job.booklet_filename
        if booklet_path.exists():
            booklet_path.unlink()

    if job.review_filename:
        review_path = Path(OUTPUT_DIR) / job.review_filename
        if review_path.exists():
            review_path.unlink()

    # Remove from jobs dict
    del jobs[job_id]

    return {"message": f"Job {job_id} deleted successfully"}
