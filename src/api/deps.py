"""
FastAPI dependencies: database sessions and user authentication.
"""

import os
import logging
from uuid import UUID
from typing import Optional

from fastapi import Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.engine import get_async_session

logger = logging.getLogger(__name__)

# Fixed UUID for local development when auth is not configured
_DEV_USER_ID = UUID("00000000-0000-0000-0000-000000000000")


async def get_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncSession:
    """Alias dependency for database session."""
    return session


async def get_current_user_id(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> UUID:
    """
    Extract the authenticated user's ID from the X-User-Id header.

    The Supabase Edge Function validates the JWT and forwards the user ID
    in the X-User-Id header. In local dev mode (no DATABASE_URL), falls back
    to a fixed dev UUID.
    """
    if x_user_id:
        try:
            return UUID(x_user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid X-User-Id header")

    # Local dev fallback: no auth required when DB is not configured
    if not os.getenv("DATABASE_URL"):
        return _DEV_USER_ID

    raise HTTPException(
        status_code=401,
        detail="Authentication required. Provide X-User-Id header.",
    )
