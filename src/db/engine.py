"""
Async SQLAlchemy engine and session factory for Supabase PostgreSQL.
"""

import os
import logging
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine,
)

logger = logging.getLogger(__name__)

_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


async def init_db() -> None:
    """Initialize the async engine and session factory. Call once at app startup."""
    global _engine, _async_session_factory

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.warning("DATABASE_URL not set — database features disabled")
        return

    # Ensure correct async driver prefix
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    _engine = create_async_engine(
        database_url,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=300,
    )
    _async_session_factory = async_sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False
    )
    logger.info("Database engine initialized")


async def close_db() -> None:
    """Dispose of the engine. Call once at app shutdown."""
    global _engine, _async_session_factory
    if _engine:
        await _engine.dispose()
        logger.info("Database engine disposed")
    _engine = None
    _async_session_factory = None


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async session.
    Usage: session: AsyncSession = Depends(get_async_session)
    """
    if _async_session_factory is None:
        raise RuntimeError("Database not initialized. Is DATABASE_URL set?")
    async with _async_session_factory() as session:
        yield session


def get_session_factory() -> Optional[async_sessionmaker[AsyncSession]]:
    """Get the session factory for use in background tasks."""
    return _async_session_factory
