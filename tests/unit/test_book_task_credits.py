"""Tests for credit confirm/release flows in generate_book_task."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.schemas import BookGenerateRequest
from src.tasks.book_tasks import generate_book_task


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_TEST_JOB_ID = str(uuid.UUID("00000000-0000-0000-0000-000000000099"))
_TEST_USAGE_LOG_ID = uuid.UUID("00000000-0000-0000-0000-000000000077")

_REQUEST = BookGenerateRequest(
    story="A bunny hops in the garden. The bunny finds a flower.",
    title="Test Story",
    generate_images=False,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _mock_storage():
    """Create a mock storage with upload_file returning 1024."""
    storage = AsyncMock()
    storage.upload_file = AsyncMock(return_value=1024)
    return storage


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBookTaskCredits:
    """Verify credit confirm / release in generate_book_task."""

    @pytest.mark.asyncio
    async def test_confirm_credits_on_success(self):
        """Successful generation must confirm credits and never release."""
        factory, _session = _mock_session_factory()
        storage = _mock_storage()

        with (
            patch("src.tasks.book_tasks.get_session_factory", return_value=factory),
            patch("src.tasks.book_tasks.get_storage", return_value=storage),
            patch("src.tasks.book_tasks.repo.update_book_job", new_callable=AsyncMock),
            patch("src.tasks.book_tasks.repo.create_generated_pdf", new_callable=AsyncMock),
            patch("src.tasks.book_tasks.generate_both_pdfs") as mock_gen_pdfs,
            patch("src.tasks.book_tasks.CreditService.confirm", new_callable=AsyncMock) as mock_confirm,
            patch("src.tasks.book_tasks.CreditService.release", new_callable=AsyncMock) as mock_release,
        ):
            # generate_both_pdfs is called inside run_in_executor (sync)
            mock_gen_pdfs.return_value = None

            await generate_book_task(
                job_id=_TEST_JOB_ID,
                request=_REQUEST,
                user_id=_TEST_USER_ID,
                usage_log_id=_TEST_USAGE_LOG_ID,
            )

            mock_confirm.assert_called_once_with(_TEST_USAGE_LOG_ID, _TEST_USER_ID)
            mock_release.assert_not_called()

    @pytest.mark.asyncio
    async def test_release_credits_on_exception(self):
        """When an exception occurs, the except handler must release credits."""
        factory, _session = _mock_session_factory()
        storage = _mock_storage()

        # First call (inside try) raises; subsequent calls (inside except's
        # fresh session) succeed so the error handler can record the failure
        # and release credits.
        mock_update = AsyncMock(
            side_effect=[RuntimeError("DB connection lost"), None],
        )

        with (
            patch("src.tasks.book_tasks.get_session_factory", return_value=factory),
            patch("src.tasks.book_tasks.get_storage", return_value=storage),
            patch("src.tasks.book_tasks.repo.update_book_job", mock_update),
            patch("src.tasks.book_tasks.repo.create_generated_pdf", new_callable=AsyncMock),
            patch("src.tasks.book_tasks.generate_both_pdfs") as mock_gen_pdfs,
            patch("src.tasks.book_tasks.CreditService.confirm", new_callable=AsyncMock) as mock_confirm,
            patch("src.tasks.book_tasks.CreditService.release", new_callable=AsyncMock) as mock_release,
        ):
            mock_gen_pdfs.return_value = None

            await generate_book_task(
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
        storage = _mock_storage()

        with (
            patch("src.tasks.book_tasks.get_session_factory", return_value=factory),
            patch("src.tasks.book_tasks.get_storage", return_value=storage),
            patch("src.tasks.book_tasks.repo.update_book_job", new_callable=AsyncMock),
            patch("src.tasks.book_tasks.repo.create_generated_pdf", new_callable=AsyncMock),
            patch("src.tasks.book_tasks.generate_both_pdfs") as mock_gen_pdfs,
            patch("src.tasks.book_tasks.CreditService.confirm", new_callable=AsyncMock) as mock_confirm,
            patch("src.tasks.book_tasks.CreditService.release", new_callable=AsyncMock) as mock_release,
        ):
            mock_gen_pdfs.return_value = None

            await generate_book_task(
                job_id=_TEST_JOB_ID,
                request=_REQUEST,
                user_id=_TEST_USER_ID,
                usage_log_id=None,
            )

            mock_confirm.assert_not_called()
            mock_release.assert_not_called()
