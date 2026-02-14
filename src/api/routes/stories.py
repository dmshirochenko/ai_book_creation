"""
Story creation endpoints.

This module provides API endpoints for generating original children's stories
from user prompts with safety guardrails.
"""

import asyncio
import uuid
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    StoryCreateRequest,
    StoryCreateResponse,
    StoryJobStatus,
    StoryValidateRequest,
    StoryValidateResponse,
    StoryResplitRequest,
    StoryResplitResponse,
    StoryResplitPageItem,
    ErrorResponse,
)
from src.api.deps import get_db, get_current_user_id
from src.core.config import LLMConfig
from src.core.story_generator import StoryGenerator, StoryValidationResult, StoryResplitResult
from src.db.engine import get_session_factory
from src.db import repository as repo


# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stories", tags=["Story Creation"])


async def _create_story_task(
    job_id: str, request: StoryCreateRequest, user_id: uuid.UUID
) -> None:
    """
    Background task to create a story.
    Uses its own DB session (background tasks run outside FastAPI dependency injection).
    """
    logger.info(f"[{job_id}] Starting story creation task")
    logger.info(f"[{job_id}] Prompt: '{request.prompt[:50]}...', tone: {request.tone}, length: {request.length}")

    session_factory = get_session_factory()
    if session_factory is None:
        logger.error(f"[{job_id}] Database not initialized, cannot run background task")
        return

    async with session_factory() as session:
        try:
            await repo.update_story_job(
                session, uuid.UUID(job_id),
                status="processing",
                progress="Validating prompt and preparing generation...",
            )
            logger.info(f"[{job_id}] Status updated to 'processing'")

            # Initialize LLM config
            llm_config = LLMConfig()
            if not llm_config.validate():
                logger.error(f"[{job_id}] No OpenRouter API key configured")
                await repo.update_story_job(
                    session, uuid.UUID(job_id),
                    status="failed",
                    error="OpenRouter API key not configured. Set OPENROUTER_API_KEY in .env file.",
                )
                return

            # Increase max_tokens for story generation (stories need more space than adaptation)
            llm_config.max_tokens = 3000
            llm_config.temperature = 0.7  # Creative but controlled

            await repo.update_story_job(
                session, uuid.UUID(job_id),
                progress="Generating your story...",
            )
            generator = StoryGenerator(llm_config)

            # Generate story
            result = await generator.generate_story(
                user_prompt=request.prompt,
                age_min=request.age_min,
                age_max=request.age_max,
                tone=request.tone,
                length=request.length,
                language=request.language,
            )

            if not result.success:
                logger.warning(f"[{job_id}] Story generation failed: {result.error}")
                await repo.update_story_job(
                    session, uuid.UUID(job_id),
                    status="failed",
                    error=result.error,
                    progress=f"Failed: {result.error}",
                    safety_status=result.safety_status,
                    safety_reasoning=result.safety_reasoning,
                )
                return

            # Success - store results
            await repo.update_story_job(
                session, uuid.UUID(job_id),
                status="completed",
                progress="Story created successfully!",
                generated_title=result.title,
                generated_story=result.story,
                generated_story_json=result.story_structured,
                story_length=result.page_count,
                tokens_used=result.tokens_used,
                safety_status=result.safety_status,
                safety_reasoning=result.safety_reasoning,
            )

            logger.info(f"[{job_id}] Story created: '{result.title}', {result.page_count} pages, {result.tokens_used} tokens")

            # If generate_book requested, create book generation job
            if request.generate_book:
                logger.info(f"[{job_id}] User requested automatic book generation")
                try:
                    from src.api.routes.books import _generate_book_task
                    from src.api.schemas import BookGenerateRequest

                    book_job_id = uuid.uuid4()

                    # Create book request with the generated story
                    book_request = BookGenerateRequest(
                        story=f"{result.title}\n{result.story}",
                        story_structured=result.story_structured,
                        title=result.title,
                        author=request.author,
                        age_min=request.age_min,
                        age_max=request.age_max,
                        language=request.language,
                        generate_images=False,  # User can enable this later if desired
                    )

                    # Create book job in database
                    await repo.create_book_job(
                        session,
                        job_id=book_job_id,
                        user_id=user_id,
                        request_params=book_request.model_dump(),
                    )

                    # Start book generation as a concurrent async task
                    asyncio.create_task(
                        _generate_book_task(str(book_job_id), book_request, user_id)
                    )

                    # Store book job reference
                    await repo.update_story_job(
                        session, uuid.UUID(job_id),
                        book_job_id=book_job_id,
                        progress=f"Story created successfully! Book generation started (job {book_job_id}).",
                    )
                    logger.info(f"[{job_id}] Started book generation job {book_job_id}")

                except Exception as e:
                    logger.error(f"[{job_id}] Failed to start book generation: {str(e)}", exc_info=True)
                    await repo.update_story_job(
                        session, uuid.UUID(job_id),
                        progress=f"Story created successfully! Note: Book generation failed to start: {str(e)}",
                    )

        except Exception as e:
            logger.error(f"[{job_id}] Story creation failed: {str(e)}", exc_info=True)
            await repo.update_story_job(
                session, uuid.UUID(job_id),
                status="failed",
                error=str(e),
                progress=f"Failed: {str(e)}",
            )


@router.post(
    "/create",
    response_model=StoryCreateResponse,
    responses={400: {"model": ErrorResponse}},
)
async def create_story(
    request: StoryCreateRequest,
    background_tasks: BackgroundTasks,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> StoryCreateResponse:
    """
    Generate an original children's story from a prompt.

    The story is generated with safety guardrails to ensure age-appropriate content
    and avoid copyrighted characters. Returns a job ID to track progress.

    ## Safety Features:
    - Pre-validation for copyrighted characters (Disney, Marvel, etc.)
    - Pre-validation for inappropriate keywords
    - AI safety instructions in prompt
    - Post-generation validation

    ## Usage:
    1. Submit a story prompt describing what you want
    2. Use the returned `job_id` to check status at `/stories/{job_id}/status`
    3. When completed, the status response will include the generated story

    ## Example Prompts:
    - "A curious kitten discovers a magical garden"
    - "A little turtle learns to swim in the ocean"
    - "A friendly bear helps forest animals build a home"
    """
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Story prompt cannot be empty")

    if request.age_min > request.age_max:
        raise HTTPException(
            status_code=400,
            detail="age_min must be less than or equal to age_max",
        )

    # Create job in database
    job_id = uuid.uuid4()
    await repo.create_story_job(
        db, job_id=job_id, user_id=user_id,
        request_params=request.model_dump(),
    )

    # Start background task
    background_tasks.add_task(_create_story_task, str(job_id), request, user_id)

    return StoryCreateResponse(
        job_id=str(job_id),
        message="Story creation started. Use /stories/{job_id}/status to track progress.",
    )


@router.post(
    "/validate",
    response_model=StoryValidateResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def validate_story(
    request: StoryValidateRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> StoryValidateResponse:
    """
    Validate an edited story for safety and appropriateness.

    This is a synchronous endpoint that checks the story text using an LLM.
    It does NOT rewrite the story -- it only evaluates whether the content
    is safe, age-appropriate, and coherent.

    ## Usage:
    Call this endpoint when the user edits a story on the preview step,
    before proceeding to book configuration.

    ## Response:
    - `status: "pass"` -- story is appropriate, proceed to next step
    - `status: "fail"` -- story has issues, show `reasoning` to the user
    """
    if request.age_min > request.age_max:
        raise HTTPException(
            status_code=400,
            detail="age_min must be less than or equal to age_max",
        )

    try:
        llm_config = LLMConfig()
        if not llm_config.validate():
            raise HTTPException(
                status_code=500,
                detail="OpenRouter API key not configured",
            )

        # Use lower max_tokens for validation (response is short)
        llm_config.max_tokens = 500
        llm_config.temperature = 0.3  # More deterministic for validation

        generator = StoryGenerator(llm_config)
        result = await generator.validate_story(
            title=request.title,
            story_text=request.story_text,
            age_min=request.age_min,
            age_max=request.age_max,
        )

        return StoryValidateResponse(
            status=result.status,
            reasoning=result.reasoning,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Story validation error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Story validation failed. Please try again.",
        )


@router.post(
    "/resplit",
    response_model=StoryResplitResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def resplit_story(
    request: StoryResplitRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> StoryResplitResponse:
    """
    Re-split an edited story into narrative-aware pages using an LLM.

    This is a synchronous endpoint that takes story text and returns
    a structured page breakdown. It does NOT rewrite the story -- it
    only decides where page breaks should go.

    ## Usage:
    Call this endpoint after story validation passes (for edited stories),
    before proceeding to book generation. Pass the resulting structured
    pages in the book generation request's `story_structured` field.

    ## Response:
    Returns `{"title": "...", "pages": [{"text": "..."}]}` --
    the same format expected by the book generation endpoint's
    `story_structured` field.
    """
    if request.age_min > request.age_max:
        raise HTTPException(
            status_code=400,
            detail="age_min must be less than or equal to age_max",
        )

    try:
        llm_config = LLMConfig()
        if not llm_config.validate():
            raise HTTPException(
                status_code=500,
                detail="OpenRouter API key not configured",
            )

        # Use moderate max_tokens (page array can be larger than validation)
        llm_config.max_tokens = 2000
        llm_config.temperature = 0.3  # Deterministic splitting

        generator = StoryGenerator(llm_config)
        result = await generator.resplit_story(
            title=request.title,
            story_text=request.story_text,
            age_min=request.age_min,
            age_max=request.age_max,
        )

        if not result.success:
            raise HTTPException(
                status_code=500,
                detail=result.error or "Failed to split story into pages.",
            )

        return StoryResplitResponse(
            title=result.story_structured["title"],
            pages=[
                StoryResplitPageItem(text=p["text"])
                for p in result.story_structured["pages"]
            ],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Story re-split error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Story page splitting failed. Please try again.",
        )


@router.get(
    "/{job_id}/status",
    response_model=StoryJobStatus,
    responses={404: {"model": ErrorResponse}},
)
async def get_story_status(
    job_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> StoryJobStatus:
    """
    Get the status of a story creation job.

    Returns the current status and progress. When completed, the response includes
    the generated story title and full story text.

    ## Status Values:
    - `pending`: Job is queued but not started
    - `processing`: Story is being generated
    - `completed`: Story generation succeeded (check `generated_story` field)
    - `failed`: Story generation failed (check `error` field)
    """
    job = await repo.get_story_job_for_user(db, uuid.UUID(job_id), user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Story job not found")

    return StoryJobStatus(
        job_id=str(job.id),
        status=job.status,
        progress=job.progress,
        error=job.error,
        safety_status=job.safety_status,
        safety_reasoning=job.safety_reasoning,
        generated_title=job.generated_title,
        generated_story=job.generated_story,
        generated_story_json=job.generated_story_json,
        story_length=job.story_length,
        tokens_used=job.tokens_used,
        book_job_id=str(job.book_job_id) if job.book_job_id else None,
    )


@router.delete(
    "/{job_id}",
    responses={404: {"model": ErrorResponse}},
)
async def delete_story_job(
    job_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Delete a story creation job.

    Removes the job from storage. This does not affect any book generation
    jobs that may have been created from this story.
    """
    job = await repo.get_story_job_for_user(db, uuid.UUID(job_id), user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Story job not found")

    await repo.delete_story_job(db, uuid.UUID(job_id))

    return {"message": f"Story job {job_id} deleted successfully"}
