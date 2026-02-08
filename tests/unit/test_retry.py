"""Unit tests for src/core/retry.py — async_retry decorator."""

import asyncio
import pytest

from src.core.retry import async_retry


class TestAsyncRetry:
    """Tests for the @async_retry decorator."""

    async def test_returns_on_first_success(self):
        call_count = 0

        @async_retry(max_attempts=3, backoff_base=0.01)
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    async def test_retries_on_failure_then_succeeds(self):
        call_count = 0

        @async_retry(max_attempts=3, backoff_base=0.01)
        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient error")
            return "ok"

        result = await fail_then_succeed()
        assert result == "ok"
        assert call_count == 3

    async def test_raises_after_all_attempts_exhausted(self):
        call_count = 0

        @async_retry(max_attempts=3, backoff_base=0.01)
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("permanent error")

        with pytest.raises(RuntimeError, match="permanent error"):
            await always_fail()
        assert call_count == 3

    async def test_exponential_backoff_timing(self):
        """Verify that retries take at least the expected backoff time."""
        call_count = 0

        @async_retry(max_attempts=3, backoff_base=0.05)
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        start = asyncio.get_event_loop().time()
        with pytest.raises(RuntimeError):
            await always_fail()
        elapsed = asyncio.get_event_loop().time() - start

        # backoff_base=0.05: sleep 0.05 + 0.10 = 0.15s minimum
        assert elapsed >= 0.14  # small tolerance
        assert call_count == 3

    async def test_default_parameters(self):
        call_count = 0

        @async_retry()
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            await always_fail()
        # default max_attempts=3
        assert call_count == 3
