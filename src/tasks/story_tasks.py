"""
Background tasks for story creation.

Extracted from src/api/routes/stories.py to keep route handlers thin.
"""

import logging
import uuid

from src.api.schemas import StoryCreateRequest
from src.core.config import LLMConfig
from src.core.story_generator import StoryGenerator
from src.db.engine import get_session_factory
from src.db import repository as repo
from src.services.credit_service import CreditService


logger = logging.getLogger(__name__)


async def create_story_task(
    job_id: str, request: StoryCreateRequest, user_id: uuid.UUID,
    usage_log_id: uuid.UUID | None = None,
) -> None:
    """
    Background task to create a story.
    Uses its own DB session (background tasks run outside FastAPI dependency injection).
    """
    logger.info(f"[{job_id}] Starting story creation task: tone={request.tone}, length={request.length}")

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

            # Initialize LLM config
            llm_config = LLMConfig()
            if not llm_config.validate():
                logger.error(f"[{job_id}] No OpenRouter API key configured")
                await repo.update_story_job(
                    session, uuid.UUID(job_id),
                    status="failed",
                    error="OpenRouter API key not configured. Set OPENROUTER_API_KEY in .env file.",
                )
                # Release reserved credits
                if usage_log_id:
                    try:
                        credit_service = CreditService(session)
                        await credit_service.release(usage_log_id, user_id)
                        logger.info(f"[{job_id}] Credits released: usage_log={usage_log_id}")
                    except Exception as release_err:
                        logger.error(
                            f"[{job_id}] Failed to release credits: usage_log={usage_log_id}, user={user_id}, error={release_err}",
                            exc_info=True,
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
                # Release reserved credits
                if usage_log_id:
                    try:
                        credit_service = CreditService(session)
                        await credit_service.release(usage_log_id, user_id)
                        logger.info(f"[{job_id}] Credits released: usage_log={usage_log_id}")
                    except Exception as release_err:
                        logger.error(
                            f"[{job_id}] Failed to release credits: usage_log={usage_log_id}, user={user_id}, error={release_err}",
                            exc_info=True,
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

            # Confirm credit deduction
            if usage_log_id:
                credit_service = CreditService(session)
                await credit_service.confirm(usage_log_id, user_id)
                logger.info(f"[{job_id}] Credits confirmed: usage_log={usage_log_id}")

            logger.info(f"[{job_id}] Story created: '{result.title}', {result.page_count} pages, {result.tokens_used} tokens")

        except Exception as e:
            logger.error(f"[{job_id}] Story creation failed: {str(e)}", exc_info=True)
            try:
                async with session_factory() as err_session:
                    await repo.update_story_job(
                        err_session, uuid.UUID(job_id),
                        status="failed", error=str(e), progress=f"Failed: {str(e)}",
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
                logger.error(f"[{job_id}] Could not record failure: {err_exc}", exc_info=True)
