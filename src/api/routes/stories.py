"""
Story creation endpoints.

This module provides API endpoints for generating original children's stories
from user prompts with safety guardrails.
"""

import uuid
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from starlette.requests import Request
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
from src.core.story_generator import StoryGenerator
from src.db import repository as repo
from src.tasks.story_tasks import create_story_task
from src.services.credit_service import CreditService, InsufficientCreditsError
from src.api.rate_limit import limiter


# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stories", tags=["Story Creation"])


@router.post(
    "/create",
    response_model=StoryCreateResponse,
    responses={400: {"model": ErrorResponse}},
)
@limiter.limit("5/minute")
async def create_story(
    request: Request,
    body: StoryCreateRequest,
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
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="Story prompt cannot be empty")

    if body.age_min > body.age_max:
        raise HTTPException(
            status_code=400,
            detail="age_min must be less than or equal to age_max",
        )

    job_id = uuid.uuid4()

    # Reserve credits
    credit_service = CreditService(db)
    try:
        story_cost = await credit_service.calculate_story_cost()
        pricing_snapshot = await credit_service.get_pricing()
        usage_log_id = await credit_service.reserve(
            user_id=user_id,
            amount=story_cost,
            job_id=job_id,
            job_type="story",
            description="Story generation",
            metadata={
                "prompt": body.prompt[:100],
                "total_cost": float(story_cost),
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
        await repo.create_story_job(
            db, job_id=job_id, user_id=user_id,
            request_params=body.model_dump(),
        )
    except Exception:
        await credit_service.release(usage_log_id, user_id)
        raise

    # Start background task
    background_tasks.add_task(create_story_task, str(job_id), body, user_id, usage_log_id)

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
            language_code=result.language_code,
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
            language_code=result.language_code,
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
        language_code=job.language_code,
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
