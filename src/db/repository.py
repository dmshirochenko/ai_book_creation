"""
Repository layer: async CRUD operations for job persistence.
"""

import uuid
from typing import Optional

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import BookJob, StoryJob, GeneratedPdf


# ========================
# BOOK JOBS
# ========================


async def create_book_job(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    request_params: Optional[dict] = None,
) -> BookJob:
    job = BookJob(
        id=job_id,
        user_id=user_id,
        status="pending",
        progress="Job created, waiting to start...",
        request_params=request_params,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def get_book_job(
    session: AsyncSession, job_id: uuid.UUID
) -> Optional[BookJob]:
    result = await session.execute(select(BookJob).where(BookJob.id == job_id))
    return result.scalar_one_or_none()


async def get_book_job_for_user(
    session: AsyncSession, job_id: uuid.UUID, user_id: uuid.UUID
) -> Optional[BookJob]:
    result = await session.execute(
        select(BookJob).where(BookJob.id == job_id, BookJob.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_book_job(
    session: AsyncSession,
    job_id: uuid.UUID,
    **kwargs,
) -> None:
    await session.execute(
        update(BookJob).where(BookJob.id == job_id).values(**kwargs)
    )
    await session.commit()


async def delete_book_job(
    session: AsyncSession, job_id: uuid.UUID
) -> None:
    await session.execute(delete(BookJob).where(BookJob.id == job_id))
    await session.commit()


async def list_book_jobs_for_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[BookJob]:
    result = await session.execute(
        select(BookJob)
        .where(BookJob.user_id == user_id)
        .order_by(BookJob.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


# ========================
# STORY JOBS
# ========================


async def create_story_job(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    request_params: Optional[dict] = None,
) -> StoryJob:
    job = StoryJob(
        id=job_id,
        user_id=user_id,
        status="pending",
        progress="Job created, waiting to start...",
        request_params=request_params,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def get_story_job(
    session: AsyncSession, job_id: uuid.UUID
) -> Optional[StoryJob]:
    result = await session.execute(select(StoryJob).where(StoryJob.id == job_id))
    return result.scalar_one_or_none()


async def get_story_job_for_user(
    session: AsyncSession, job_id: uuid.UUID, user_id: uuid.UUID
) -> Optional[StoryJob]:
    result = await session.execute(
        select(StoryJob).where(
            StoryJob.id == job_id, StoryJob.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def update_story_job(
    session: AsyncSession,
    job_id: uuid.UUID,
    **kwargs,
) -> None:
    await session.execute(
        update(StoryJob).where(StoryJob.id == job_id).values(**kwargs)
    )
    await session.commit()


async def delete_story_job(
    session: AsyncSession, job_id: uuid.UUID
) -> None:
    await session.execute(delete(StoryJob).where(StoryJob.id == job_id))
    await session.commit()


# ========================
# GENERATED PDFs
# ========================


async def create_generated_pdf(
    session: AsyncSession,
    *,
    book_job_id: uuid.UUID,
    user_id: uuid.UUID,
    pdf_type: str,
    filename: str,
    file_path: str,
    page_count: Optional[int] = None,
    file_size_bytes: Optional[int] = None,
) -> GeneratedPdf:
    pdf = GeneratedPdf(
        book_job_id=book_job_id,
        user_id=user_id,
        pdf_type=pdf_type,
        filename=filename,
        file_path=file_path,
        page_count=page_count,
        file_size_bytes=file_size_bytes,
    )
    session.add(pdf)
    await session.commit()
    await session.refresh(pdf)
    return pdf
