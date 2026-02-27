"""
Credit management service.

Handles credit balance checks, FIFO batch consumption, reservations,
confirmations, and releases using SELECT ... FOR UPDATE for atomicity.
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import CreditPricing, CreditUsageLog, UserCredits

logger = logging.getLogger(__name__)


class InsufficientCreditsError(Exception):
    def __init__(self, balance: Decimal, required: Decimal):
        self.balance = balance
        self.required = required
        super().__init__(f"Insufficient credits: have {balance}, need {required}")


class CreditService:
    ALLOWED_METADATA_KEYS = frozenset({
        "prompt", "total_cost", "pricing_snapshot", "batches_consumed",
        "title", "pages", "with_images", "cost_per_page",
    })

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_pricing(self) -> dict[str, Decimal]:
        result = await self._session.execute(
            select(CreditPricing).where(CreditPricing.is_active.is_(True))
        )
        rows = result.scalars().all()
        return {row.operation: row.credit_cost for row in rows}

    async def calculate_story_cost(self) -> Decimal:
        pricing = await self.get_pricing()
        return pricing.get("story_generation", Decimal("0"))

    async def calculate_book_cost(
        self, pages: int, with_images: bool, image_model: str | None = None,
    ) -> Decimal:
        pricing = await self.get_pricing()
        if not with_images:
            key = "page_without_images"
        elif image_model and image_model in pricing:
            key = image_model
        else:
            key = "page_with_images"
        return pages * pricing.get(key, Decimal("0"))

    async def get_balance(self, user_id: uuid.UUID) -> Decimal:
        result = await self._session.execute(
            select(func.coalesce(func.sum(UserCredits.remaining_amount), 0))
            .where(UserCredits.user_id == user_id, UserCredits.is_refunded.is_(False))
        )
        return result.scalar_one()

    async def get_usage_logs(
        self,
        user_id: uuid.UUID,
        from_date: datetime,
        to_date: datetime,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[CreditUsageLog], int]:
        """Return paginated usage logs filtered by date range."""
        base_filter = [
            CreditUsageLog.user_id == user_id,
            CreditUsageLog.created_at >= from_date,
            CreditUsageLog.created_at <= to_date,
        ]

        count_result = await self._session.execute(
            select(func.count(CreditUsageLog.id)).where(*base_filter)
        )
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        items_result = await self._session.execute(
            select(CreditUsageLog)
            .where(*base_filter)
            .order_by(CreditUsageLog.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        items = items_result.scalars().all()

        return items, total

    async def reserve(
        self, user_id: uuid.UUID, amount: Decimal, job_id: uuid.UUID,
        job_type: str, description: str, metadata: dict,
    ) -> Optional[uuid.UUID]:
        if amount <= 0:
            return None

        result = await self._session.execute(
            select(UserCredits)
            .where(UserCredits.user_id == user_id, UserCredits.remaining_amount > 0, UserCredits.is_refunded.is_(False))
            .order_by(UserCredits.created_at.asc())
            .with_for_update()
        )
        batches = result.scalars().all()

        total_available = sum(b.remaining_amount for b in batches)
        if total_available < amount:
            raise InsufficientCreditsError(balance=total_available, required=amount)

        remaining_to_consume = amount
        batches_consumed = []
        for batch in batches:
            if remaining_to_consume <= 0:
                break
            consume = min(batch.remaining_amount, remaining_to_consume)
            batch.remaining_amount -= consume
            remaining_to_consume -= consume
            batches_consumed.append({"batch_id": str(batch.id), "amount": str(consume)})

        # Sanitize metadata keys
        safe_metadata = {k: v for k, v in metadata.items() if k in self.ALLOWED_METADATA_KEYS}
        metadata_with_batches = {**safe_metadata, "batches_consumed": batches_consumed}
        usage_log = CreditUsageLog(
            user_id=user_id, job_id=job_id, job_type=job_type,
            credits_used=amount, status="reserved", description=description,
            extra_metadata=metadata_with_batches,
            reserved_at=datetime.now(timezone.utc),
        )
        self._session.add(usage_log)
        await self._session.commit()
        await self._session.refresh(usage_log)

        logger.info(f"Reserved {amount} credits for user {user_id}, job {job_id} ({job_type}), usage_log={usage_log.id}")
        return usage_log.id

    async def confirm(self, usage_log_id: Optional[uuid.UUID], user_id: Optional[uuid.UUID] = None) -> None:
        if usage_log_id is None:
            return
        query = select(CreditUsageLog).where(CreditUsageLog.id == usage_log_id).with_for_update()
        if user_id is not None:
            query = query.where(CreditUsageLog.user_id == user_id)
        result = await self._session.execute(query)
        log = result.scalar_one_or_none()
        if not log or log.status != "reserved":
            return
        log.status = "confirmed"
        await self._session.commit()
        logger.info(f"Confirmed credit usage {usage_log_id}")

    async def release(self, usage_log_id: Optional[uuid.UUID], user_id: Optional[uuid.UUID] = None) -> None:
        if usage_log_id is None:
            return
        query = select(CreditUsageLog).where(CreditUsageLog.id == usage_log_id).with_for_update()
        if user_id is not None:
            query = query.where(CreditUsageLog.user_id == user_id)
        result = await self._session.execute(query)
        log = result.scalar_one_or_none()
        if not log or log.status != "reserved":
            return

        batches_consumed = (log.extra_metadata or {}).get("batches_consumed", [])
        for entry in batches_consumed:
            batch_result = await self._session.execute(
                select(UserCredits).where(UserCredits.id == uuid.UUID(entry["batch_id"])).with_for_update()
            )
            batch = batch_result.scalar_one_or_none()
            if batch:
                batch.remaining_amount += Decimal(entry["amount"])

        log.status = "released"
        await self._session.commit()
        logger.info(f"Released {log.credits_used} credits for usage {usage_log_id}")

    async def cleanup_stale_reservations(self, ttl_minutes: int = 30) -> int:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=ttl_minutes)
        result = await self._session.execute(
            select(CreditUsageLog).where(CreditUsageLog.status == "reserved", CreditUsageLog.reserved_at < cutoff)
        )
        stale_logs = result.scalars().all()
        count = 0
        for log in stale_logs:
            await self.release(log.id)
            count += 1
        if count > 0:
            logger.warning(f"Cleaned up {count} stale credit reservations")
        return count
