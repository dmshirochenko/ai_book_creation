"""
Credit management endpoints.

Provides pricing info, balance checks, and usage history.
All credit amounts are returned as float (serialized from Decimal).
"""

import uuid
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    CreditPricingItem,
    CreditPricingResponse,
    CreditBalanceResponse,
    CreditUsageItem,
    CreditUsageResponse,
)
from src.api.deps import get_db, get_current_user_id
from src.db.models import CreditPricing, CreditUsageLog
from src.services.credit_service import CreditService

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
                credit_cost=float(r.credit_cost),
                description=r.description,
            )
            for r in rows
        ]
    )


@router.get("/balance", response_model=CreditBalanceResponse)
async def get_balance(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> CreditBalanceResponse:
    """Get the authenticated user's credit balance."""
    service = CreditService(db)
    balance = await service.get_balance(user_id)
    return CreditBalanceResponse(balance=float(balance))


@router.get("/usage", response_model=CreditUsageResponse)
async def get_usage(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
) -> CreditUsageResponse:
    """Get credit usage history for the authenticated user."""
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
                credits_used=float(log.credits_used),
                status=log.status,
                description=log.description,
                metadata=log.extra_metadata,
                created_at=log.created_at.isoformat(),
            )
            for log in logs
        ]
    )
