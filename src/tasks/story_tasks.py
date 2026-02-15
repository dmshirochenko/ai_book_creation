"""
Background tasks for story creation.

Extracted from src/api/routes/stories.py to keep route handlers thin.
"""

import asyncio
import logging
import uuid

from src.api.schemas import StoryCreateRequest
from src.core.config import LLMConfig
from src.core.story_generator import StoryGenerator
from src.db.engine import get_session_factory
from src.db import repository as repo


logger = logging.getLogger(__name__)


async def create_story_task(
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
                    from src.tasks.book_tasks import generate_book_task
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
                        generate_book_task(str(book_job_id), book_request, user_id)
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
