"""
Story creation endpoints.

This module provides API endpoints for generating original children's stories
from user prompts with safety guardrails.
"""

import asyncio
import uuid
import logging
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException

from src.api.schemas import (
    StoryCreateRequest,
    StoryCreateResponse,
    StoryJobStatus,
    ErrorResponse,
)
from src.core.config import LLMConfig
from src.core.story_generator import StoryGenerator


# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stories", tags=["Story Creation"])

# In-memory job storage (use Redis/database in production)
story_jobs: Dict[str, StoryJobStatus] = {}


async def _create_story_task(job_id: str, request: StoryCreateRequest) -> None:
    """
    Background task to create a story.
    Updates job status as it progresses.
    """
    logger.info(f"[{job_id}] Starting story creation task")
    logger.info(f"[{job_id}] Prompt: '{request.prompt[:50]}...', tone: {request.tone}, length: {request.length}")

    try:
        story_jobs[job_id].status = "processing"
        story_jobs[job_id].progress = "Validating prompt and preparing generation..."
        logger.info(f"[{job_id}] Status updated to 'processing'")

        # Initialize LLM config
        llm_config = LLMConfig()
        if not llm_config.validate():
            logger.error(f"[{job_id}] No OpenRouter API key configured")
            story_jobs[job_id].status = "failed"
            story_jobs[job_id].error = "OpenRouter API key not configured. Set OPENROUTER_API_KEY in .env file."
            return

        # Increase max_tokens for story generation (stories need more space than adaptation)
        llm_config.max_tokens = 3000
        llm_config.temperature = 0.7  # Creative but controlled

        story_jobs[job_id].progress = "Generating your story..."
        generator = StoryGenerator(llm_config)

        # Generate story
        result = await generator.generate_story(
            user_prompt=request.prompt,
            age_min=request.age_min,
            age_max=request.age_max,
            tone=request.tone,
            length=request.length,
            language=request.language
        )

        if not result.success:
            logger.warning(f"[{job_id}] Story generation failed: {result.error}")
            story_jobs[job_id].status = "failed"
            story_jobs[job_id].error = result.error
            story_jobs[job_id].progress = f"Failed: {result.error}"
            return

        # Success - store results
        story_jobs[job_id].status = "completed"
        story_jobs[job_id].progress = "Story created successfully!"
        story_jobs[job_id].generated_title = result.title
        story_jobs[job_id].generated_story = result.story
        story_jobs[job_id].story_length = result.page_count
        story_jobs[job_id].tokens_used = result.tokens_used

        logger.info(f"[{job_id}] Story created: '{result.title}', {result.page_count} pages, {result.tokens_used} tokens")

        # If generate_book requested, create book generation job
        if request.generate_book:
            logger.info(f"[{job_id}] User requested automatic book generation")
            try:
                from src.api.routes.books import jobs as book_jobs, _generate_book_task
                from src.api.schemas import BookGenerateRequest, JobStatus

                book_job_id = str(uuid.uuid4())

                # Create book request with the generated story
                book_request = BookGenerateRequest(
                    story=f"{result.title}\n{result.story}",
                    title=result.title,
                    author=request.author,
                    age_min=request.age_min,
                    age_max=request.age_max,
                    language=request.language,
                    skip_adaptation=True,  # Story is already formatted for children
                    generate_images=False,  # User can enable this later if desired
                )

                # Create book job
                book_jobs[book_job_id] = JobStatus(
                    job_id=book_job_id,
                    status="pending",
                    progress="Job created, waiting to start...",
                )

                # Start book generation as a concurrent async task
                asyncio.create_task(_generate_book_task(book_job_id, book_request))

                # Store book job reference
                story_jobs[job_id].book_job_id = book_job_id
                story_jobs[job_id].progress += f" Book generation started (job {book_job_id})."
                logger.info(f"[{job_id}] Started book generation job {book_job_id}")

            except Exception as e:
                logger.error(f"[{job_id}] Failed to start book generation: {str(e)}", exc_info=True)
                story_jobs[job_id].progress += f" Note: Book generation failed to start: {str(e)}"

    except Exception as e:
        logger.error(f"[{job_id}] Story creation failed: {str(e)}", exc_info=True)
        story_jobs[job_id].status = "failed"
        story_jobs[job_id].error = str(e)
        story_jobs[job_id].progress = f"Failed: {str(e)}"


@router.post(
    "/create",
    response_model=StoryCreateResponse,
    responses={400: {"model": ErrorResponse}},
)
async def create_story(
    request: StoryCreateRequest,
    background_tasks: BackgroundTasks,
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
            detail="age_min must be less than or equal to age_max"
        )

    # Create job
    job_id = str(uuid.uuid4())
    story_jobs[job_id] = StoryJobStatus(
        job_id=job_id,
        status="pending",
        progress="Job created, waiting to start...",
    )

    # Start background task
    background_tasks.add_task(_create_story_task, job_id, request)

    return StoryCreateResponse(
        job_id=job_id,
        message="Story creation started. Use /stories/{job_id}/status to track progress.",
    )


@router.get(
    "/{job_id}/status",
    response_model=StoryJobStatus,
    responses={404: {"model": ErrorResponse}},
)
async def get_story_status(job_id: str) -> StoryJobStatus:
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
    if job_id not in story_jobs:
        raise HTTPException(status_code=404, detail="Story job not found")

    return story_jobs[job_id]


@router.delete(
    "/{job_id}",
    responses={404: {"model": ErrorResponse}},
)
async def delete_story_job(job_id: str) -> dict:
    """
    Delete a story creation job.

    Removes the job from storage. This does not affect any book generation
    jobs that may have been created from this story.
    """
    if job_id not in story_jobs:
        raise HTTPException(status_code=404, detail="Story job not found")

    del story_jobs[job_id]

    return {"message": f"Story job {job_id} deleted successfully"}
