"""Tests for credit confirm/release flows in create_story_task."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.schemas import StoryCreateRequest
from src.tasks.story_tasks import create_story_task


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_TEST_JOB_ID = str(uuid.UUID("00000000-0000-0000-0000-000000000099"))
_TEST_USAGE_LOG_ID = uuid.UUID("00000000-0000-0000-0000-000000000077")

_REQUEST = StoryCreateRequest(
    prompt="A curious kitten discovers a magical garden in the backyard",
    age_min=2,
    age_max=4,
    tone="cheerful",
    length="medium",
    language="English",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_success_result():
    """Return a mock StoryGenerationResult for a successful generation."""
    result = MagicMock()
    result.success = True
    result.title = "Test Story"
    result.story = "Once upon a time..."
    result.story_structured = {
        "title": "Test Story",
        "pages": [{"text": "Once upon a time..."}],
    }
    result.page_count = 1
    result.tokens_used = 100
    result.safety_status = "safe"
    result.safety_reasoning = None
    return result


def _make_failure_result():
    """Return a mock StoryGenerationResult for a failed generation."""
    result = MagicMock()
    result.success = False
    result.error = "Content policy violation"
    result.safety_status = "unsafe"
    result.safety_reasoning = "Prompt rejected"
    return result


def _mock_session_factory():
    """Create a mock session factory that works as async context manager.

    Returns (factory, session) — the factory is suitable for patching
    ``get_session_factory`` and the session is the mock AsyncSession yielded
    by ``async with factory() as session:``.
    """
    session = AsyncMock()

    # factory() returns an async context manager
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock()
    factory.return_value = ctx

    return factory, session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStoryTaskCredits:
    """Verify credit confirm / release in create_story_task."""

    @pytest.mark.asyncio
    async def test_confirm_credits_on_success(self):
        """Successful generation must confirm credits and never release."""
        factory, _session = _mock_session_factory()
        success_result = _make_success_result()

        mock_generator_instance = AsyncMock()
        mock_generator_instance.generate_story = AsyncMock(return_value=success_result)

        mock_llm_config_instance = MagicMock()
        mock_llm_config_instance.validate.return_value = True

        with (
            patch("src.tasks.story_tasks.get_session_factory", return_value=factory),
            patch("src.tasks.story_tasks.repo.update_story_job", new_callable=AsyncMock),
            patch("src.tasks.story_tasks.LLMConfig", return_value=mock_llm_config_instance),
            patch("src.tasks.story_tasks.StoryGenerator", return_value=mock_generator_instance),
            patch("src.tasks.story_tasks.CreditService.confirm", new_callable=AsyncMock) as mock_confirm,
            patch("src.tasks.story_tasks.CreditService.release", new_callable=AsyncMock) as mock_release,
        ):
            await create_story_task(
                job_id=_TEST_JOB_ID,
                request=_REQUEST,
                user_id=_TEST_USER_ID,
                usage_log_id=_TEST_USAGE_LOG_ID,
            )

            mock_confirm.assert_called_once_with(_TEST_USAGE_LOG_ID, _TEST_USER_ID)
            mock_release.assert_not_called()

    @pytest.mark.asyncio
    async def test_release_credits_on_generation_failure(self):
        """When generator returns success=False, credits must be released."""
        factory, _session = _mock_session_factory()
        failure_result = _make_failure_result()

        mock_generator_instance = AsyncMock()
        mock_generator_instance.generate_story = AsyncMock(return_value=failure_result)

        mock_llm_config_instance = MagicMock()
        mock_llm_config_instance.validate.return_value = True

        with (
            patch("src.tasks.story_tasks.get_session_factory", return_value=factory),
            patch("src.tasks.story_tasks.repo.update_story_job", new_callable=AsyncMock),
            patch("src.tasks.story_tasks.LLMConfig", return_value=mock_llm_config_instance),
            patch("src.tasks.story_tasks.StoryGenerator", return_value=mock_generator_instance),
            patch("src.tasks.story_tasks.CreditService.confirm", new_callable=AsyncMock) as mock_confirm,
            patch("src.tasks.story_tasks.CreditService.release", new_callable=AsyncMock) as mock_release,
        ):
            await create_story_task(
                job_id=_TEST_JOB_ID,
                request=_REQUEST,
                user_id=_TEST_USER_ID,
                usage_log_id=_TEST_USAGE_LOG_ID,
            )

            mock_release.assert_called_once_with(_TEST_USAGE_LOG_ID, _TEST_USER_ID)
            mock_confirm.assert_not_called()

    @pytest.mark.asyncio
    async def test_release_credits_on_no_api_key(self):
        """When LLMConfig.validate() returns False, credits must be released."""
        factory, _session = _mock_session_factory()

        mock_llm_config_instance = MagicMock()
        mock_llm_config_instance.validate.return_value = False

        with (
            patch("src.tasks.story_tasks.get_session_factory", return_value=factory),
            patch("src.tasks.story_tasks.repo.update_story_job", new_callable=AsyncMock),
            patch("src.tasks.story_tasks.LLMConfig", return_value=mock_llm_config_instance),
            patch("src.tasks.story_tasks.CreditService.confirm", new_callable=AsyncMock) as mock_confirm,
            patch("src.tasks.story_tasks.CreditService.release", new_callable=AsyncMock) as mock_release,
        ):
            await create_story_task(
                job_id=_TEST_JOB_ID,
                request=_REQUEST,
                user_id=_TEST_USER_ID,
                usage_log_id=_TEST_USAGE_LOG_ID,
            )

            mock_release.assert_called_once_with(_TEST_USAGE_LOG_ID, _TEST_USER_ID)
            mock_confirm.assert_not_called()

    @pytest.mark.asyncio
    async def test_release_credits_on_exception(self):
        """When generate_story raises, the except handler must release credits."""
        factory, _session = _mock_session_factory()

        mock_generator_instance = AsyncMock()
        mock_generator_instance.generate_story = AsyncMock(
            side_effect=RuntimeError("LLM service down")
        )

        mock_llm_config_instance = MagicMock()
        mock_llm_config_instance.validate.return_value = True

        with (
            patch("src.tasks.story_tasks.get_session_factory", return_value=factory),
            patch("src.tasks.story_tasks.repo.update_story_job", new_callable=AsyncMock),
            patch("src.tasks.story_tasks.LLMConfig", return_value=mock_llm_config_instance),
            patch("src.tasks.story_tasks.StoryGenerator", return_value=mock_generator_instance),
            patch("src.tasks.story_tasks.CreditService.confirm", new_callable=AsyncMock) as mock_confirm,
            patch("src.tasks.story_tasks.CreditService.release", new_callable=AsyncMock) as mock_release,
        ):
            await create_story_task(
                job_id=_TEST_JOB_ID,
                request=_REQUEST,
                user_id=_TEST_USER_ID,
                usage_log_id=_TEST_USAGE_LOG_ID,
            )

            mock_release.assert_called_once_with(_TEST_USAGE_LOG_ID, _TEST_USER_ID)
            mock_confirm.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_credit_ops_when_usage_log_none(self):
        """When usage_log_id is None, neither confirm nor release should be called."""
        factory, _session = _mock_session_factory()
        success_result = _make_success_result()

        mock_generator_instance = AsyncMock()
        mock_generator_instance.generate_story = AsyncMock(return_value=success_result)

        mock_llm_config_instance = MagicMock()
        mock_llm_config_instance.validate.return_value = True

        with (
            patch("src.tasks.story_tasks.get_session_factory", return_value=factory),
            patch("src.tasks.story_tasks.repo.update_story_job", new_callable=AsyncMock),
            patch("src.tasks.story_tasks.LLMConfig", return_value=mock_llm_config_instance),
            patch("src.tasks.story_tasks.StoryGenerator", return_value=mock_generator_instance),
            patch("src.tasks.story_tasks.CreditService.confirm", new_callable=AsyncMock) as mock_confirm,
            patch("src.tasks.story_tasks.CreditService.release", new_callable=AsyncMock) as mock_release,
        ):
            await create_story_task(
                job_id=_TEST_JOB_ID,
                request=_REQUEST,
                user_id=_TEST_USER_ID,
                usage_log_id=None,
            )

            mock_confirm.assert_not_called()
            mock_release.assert_not_called()
