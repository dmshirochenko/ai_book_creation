"""
Credit management endpoints.

Provides pricing info, balance checks, and usage history.
All credit amounts are returned as float (serialized from Decimal).
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from starlette.requests import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    CreditPricingItem,
    CreditPricingResponse,
    CreditBalanceResponse,
    CreditUsageItem,
    CreditUsageResponse,
    UsageLogItem,
    PaginatedUsageLogsResponse,
)
from src.api.deps import get_db, get_current_user_id
from src.db.models import CreditPricing, CreditUsageLog
from src.services.credit_service import CreditService
from src.api.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/credits", tags=["Credits"])


@router.get("/pricing", response_model=CreditPricingResponse)
async def get_pricing(
    db: AsyncSession = Depends(get_db),
) -> CreditPricingResponse:
    """Get current credit pricing for all operations."""
    result = await db.execute(
        select(CreditPricing).where(CreditPricing.is_active.is_(True))
    )
    rows = result.scalars().all()
    return CreditPricingResponse(
        pricing=[
            CreditPricingItem(
                operation=r.operation,
                credit_cost=float(round(r.credit_cost, 2)),
                description=r.description,
            )
            for r in rows
        ]
    )


@router.get("/balance", response_model=CreditBalanceResponse)
@limiter.limit("30/minute")
async def get_balance(
    request: Request,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> CreditBalanceResponse:
    """Get the authenticated user's credit balance."""
    service = CreditService(db)
    balance = await service.get_balance(user_id)
    return CreditBalanceResponse(balance=float(round(balance, 2)))


@router.get("/usage", response_model=CreditUsageResponse)
@limiter.limit("30/minute")
async def get_usage(
    request: Request,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
) -> CreditUsageResponse:
    """Get credit usage history for the authenticated user."""
    limit = max(1, min(limit, 100))
    result = await db.execute(
        select(CreditUsageLog)
        .where(CreditUsageLog.user_id == user_id)
        .order_by(CreditUsageLog.created_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    return CreditUsageResponse(
        usage=[
            CreditUsageItem(
                id=str(log.id),
                job_id=str(log.job_id),
                job_type=log.job_type,
                credits_used=float(round(log.credits_used, 2)),
                status=log.status,
                description=log.description,
                created_at=log.created_at.isoformat(),
            )
            for log in logs
        ]
    )


@router.get("/usage-logs", response_model=PaginatedUsageLogsResponse)
@limiter.limit("30/minute")
async def get_usage_logs(
    request: Request,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedUsageLogsResponse:
    """Get paginated credit usage logs with date range filtering."""
    now = datetime.now(timezone.utc)

    if from_date:
        parsed_from = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
    else:
        parsed_from = now - timedelta(hours=24)

    if to_date:
        parsed_to = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
    else:
        parsed_to = now

    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    service = CreditService(db)
    items, total = await service.get_usage_logs(
        user_id=user_id,
        from_date=parsed_from,
        to_date=parsed_to,
        page=page,
        page_size=page_size,
    )

    return PaginatedUsageLogsResponse(
        items=[
            UsageLogItem(
                id=str(log.id),
                job_id=str(log.job_id),
                job_type=log.job_type,
                credits_used=float(round(log.credits_used, 2)),
                status=log.status,
                description=log.description,
                metadata=log.extra_metadata,
                created_at=log.created_at.isoformat(),
            )
            for log in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
