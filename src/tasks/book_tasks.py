"""
Background tasks for book generation.

Extracted from src/api/routes/books.py to keep route handlers thin.
"""

import asyncio
import hashlib
import logging
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from src.api.schemas import BookGenerateRequest
from src.core.config import LLMConfig
from src.core.llm_connector import analyze_story_for_visuals
from src.core.text_processor import TextProcessor, validate_book_content
from src.core.pdf_generator import generate_both_pdfs
from src.core.storage import get_storage
from src.db.engine import get_session_factory
from src.db import repository as repo
from src.services.credit_service import CreditService


logger = logging.getLogger(__name__)

TASK_TIMEOUT_SECONDS = 1200  # 20 minutes


async def _generate_book_inner(
    job_id: str, request: BookGenerateRequest, user_id: uuid.UUID,
    usage_log_id: uuid.UUID | None, session, session_factory, storage,
) -> None:
    """Inner logic for generate_book_task, extracted for timeout wrapping."""
    await repo.update_book_job(
        session, uuid.UUID(job_id),
        status="processing", progress="Starting book generation...",
    )

    story_text = request.story

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

    if request.story_structured and request.story_structured.pages:
        logger.info(f"[{job_id}] Using process_structured (structured JSON input)")
        book_content = processor.process_structured(
            story_data=request.story_structured.model_dump(),
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
            # Create DB rows for generated images
            images = {}
            for page_num, result in image_results.items():
                prompt_hash = hashlib.md5(
                    (result.prompt_used or "").encode()
                ).hexdigest()
                file_size = len(result.image_data) if result.image_data else None

                # NOTE: For cache hits, r2_key may reference another book's
                # R2 namespace (e.g. "images/other-job-id/page_1.png").
                # Any future R2 cleanup must check for shared references.
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
                    image_model=request.image_model,
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

        await asyncio.to_thread(
            generate_both_pdfs,
            content=book_content,
            booklet_path=booklet_path,
            review_path=review_path,
            config=request,
            images=images,
        )
        # Upload to R2
        booklet_r2_key = f"pdfs/{job_id}/{booklet_filename}"
        review_r2_key = f"pdfs/{job_id}/{review_filename}"

        booklet_size, review_size = await asyncio.gather(
            storage.upload_file(booklet_path, booklet_r2_key, "application/pdf"),
            storage.upload_file(review_path, review_r2_key, "application/pdf"),
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

    # Confirm credit deduction
    if usage_log_id:
        credit_service = CreditService(session)
        await credit_service.confirm(usage_log_id, user_id)
        logger.info(f"[{job_id}] Credits confirmed: usage_log={usage_log_id}")


async def generate_book_task(
    job_id: str, request: BookGenerateRequest, user_id: uuid.UUID,
    usage_log_id: uuid.UUID | None = None,
) -> None:
    """
    Background task to generate the book.
    Uses its own DB session (background tasks run outside FastAPI dependency injection).
    """
    logger.info(f"[{job_id}] Starting book generation task: '{request.title}'")

    session_factory = get_session_factory()
    if session_factory is None:
        logger.error(f"[{job_id}] Database not initialized, cannot run background task")
        return

    storage = get_storage()

    async with session_factory() as session:
        try:
            await asyncio.wait_for(
                _generate_book_inner(
                    job_id, request, user_id, usage_log_id,
                    session, session_factory, storage,
                ),
                timeout=TASK_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.error(f"[{job_id}] Book generation timed out after {TASK_TIMEOUT_SECONDS}s")
            try:
                async with session_factory() as err_session:
                    await repo.update_book_job(
                        err_session, uuid.UUID(job_id),
                        status="failed",
                        error=f"Book generation timed out after {TASK_TIMEOUT_SECONDS // 60} minutes",
                        progress="Failed: generation timed out",
                    )
                    if usage_log_id:
                        try:
                            credit_service = CreditService(err_session)
                            await credit_service.release(usage_log_id, user_id)
                            logger.info(f"[{job_id}] Credits released after timeout")
                        except Exception as release_err:
                            logger.error(
                                f"[{job_id}] Failed to release credits: usage_log={usage_log_id}, user={user_id}, error={release_err}",
                                exc_info=True,
                            )
            except Exception as err_exc:
                logger.error(
                    f"[{job_id}] Could not record timeout failure: {err_exc}",
                    exc_info=True,
                )
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
                    # Release reserved credits with fresh session
                    if usage_log_id:
                        try:
                            credit_service = CreditService(err_session)
                            await credit_service.release(usage_log_id, user_id)
                            logger.info(f"[{job_id}] Credits released after failure")
                        except Exception as release_err:
                            logger.error(
                                f"[{job_id}] Failed to release credits: usage_log={usage_log_id}, user={user_id}, error={release_err}",
                                exc_info=True,
                            )
            except Exception as err_exc:
                logger.error(
                    f"[{job_id}] Could not record failure status: {err_exc}",
                    exc_info=True,
                )


async def _regenerate_book_inner(
    job_id: str, failed_images: list, user_id: uuid.UUID,
    session, session_factory, storage,
) -> None:
    """Inner logic for regenerate_book_task, extracted for timeout wrapping."""
    await repo.update_book_job(
        session, uuid.UUID(job_id),
        status="processing",
        progress=f"Retrying {len(failed_images)} failed images...",
    )

    from src.core.image_generator import ImageConfig, OpenRouterImageGenerator, GeneratedImage as GenImg, ImageGenerationError
    from src.core.retry import async_retry
    from src.core.config import DEFAULT_IMAGE_MODEL

    # Retry each failed image — each may use a different model
    for img in failed_images:
        image_id = img.id
        prompt = img.prompt
        page_number = img.page_number
        retry_attempt = img.retry_attempt + 1
        model = img.image_model or DEFAULT_IMAGE_MODEL

        logger.info(f"[{job_id}] Retrying page {page_number} (attempt #{retry_attempt}) with model {model}")

        image_config = ImageConfig(model=model)
        generator = OpenRouterImageGenerator(image_config)

        @async_retry(max_attempts=3, backoff_base=2.0)
        async def generate_with_retry(prompt: str) -> GenImg:
            result = await generator.generate(prompt)
            if not result.success:
                raise ImageGenerationError(result.error or "Unknown error")
            return result

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
        finally:
            await generator.close()

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

    if request.story_structured and request.story_structured.pages:
        book_content = processor.process_structured(
            story_data=request.story_structured.model_dump(),
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

        await asyncio.to_thread(
            generate_both_pdfs,
            content=book_content,
            booklet_path=booklet_path,
            review_path=review_path,
            config=request,
            images=images,
        )

        booklet_r2_key = f"pdfs/{job_id}/{booklet_filename}"
        review_r2_key = f"pdfs/{job_id}/{review_filename}"

        booklet_size, review_size = await asyncio.gather(
            storage.upload_file(booklet_path, booklet_r2_key, "application/pdf"),
            storage.upload_file(review_path, review_r2_key, "application/pdf"),
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


async def regenerate_book_task(
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
            await asyncio.wait_for(
                _regenerate_book_inner(
                    job_id, failed_images, user_id,
                    session, session_factory, storage,
                ),
                timeout=TASK_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.error(f"[{job_id}] Book regeneration timed out after {TASK_TIMEOUT_SECONDS}s")
            try:
                async with session_factory() as err_session:
                    await repo.update_book_job(
                        err_session, uuid.UUID(job_id),
                        status="failed",
                        error=f"Book regeneration timed out after {TASK_TIMEOUT_SECONDS // 60} minutes",
                        progress="Failed: regeneration timed out",
                    )
            except Exception as err_exc:
                logger.error(
                    f"[{job_id}] Could not record timeout failure: {err_exc}",
                    exc_info=True,
                )
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
