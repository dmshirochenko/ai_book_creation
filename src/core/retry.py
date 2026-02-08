"""Async retry decorator with exponential backoff."""

import asyncio
import logging
from functools import wraps
from typing import TypeVar, Callable, Any

logger = logging.getLogger(__name__)

T = TypeVar("T")


def async_retry(
    max_attempts: int = 3,
    backoff_base: float = 2.0,
) -> Callable:
    """
    Decorator that retries an async function on exception.

    Uses exponential backoff: sleeps backoff_base * 2^(attempt-1) seconds
    between retries (i.e. backoff_base after first failure,
    backoff_base*2 after second, etc.).

    Args:
        max_attempts: Total number of attempts (1 = no retry).
        backoff_base: Base delay in seconds for the first retry.
    """
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    last_exception = exc
                    if attempt < max_attempts:
                        delay = backoff_base * (2 ** (attempt - 1))
                        logger.warning(
                            f"{fn.__name__} attempt {attempt}/{max_attempts} "
                            f"failed: {exc}. Retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"{fn.__name__} failed after {max_attempts} attempts: {exc}"
                        )
            raise last_exception  # type: ignore[misc]
        return wrapper
    return decorator
