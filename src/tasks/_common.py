"""Shared helpers for background tasks."""

import logging
import uuid

from src.services.credit_service import CreditService


logger = logging.getLogger(__name__)


async def safe_release_credits(
    session, usage_log_id: uuid.UUID, user_id: uuid.UUID, job_id: str,
) -> None:
    """Release reserved credits, logging but not raising on failure."""
    try:
        credit_service = CreditService(session)
        await credit_service.release(usage_log_id, user_id)
        logger.info(f"[{job_id}] Credits released: usage_log={usage_log_id}")
    except Exception as release_err:
        logger.error(
            f"[{job_id}] Failed to release credits: usage_log={usage_log_id}, user={user_id}, error={release_err}",
            exc_info=True,
        )
