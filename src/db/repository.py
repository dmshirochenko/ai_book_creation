"""
Repository layer: async CRUD operations for job persistence.
"""

import uuid
from typing import Optional

from sqlalchemy import select, update, delete, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import BookJob, StoryJob, GeneratedPdf, GeneratedImage


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


async def list_completed_books_for_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[BookJob]:
    result = await session.execute(
        select(BookJob)
        .where(BookJob.user_id == user_id, BookJob.status == "completed")
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


# ========================
# GENERATED IMAGES
# ========================


async def create_generated_image(
    session: AsyncSession,
    *,
    book_job_id: uuid.UUID,
    user_id: uuid.UUID,
    page_number: int,
    prompt: str,
    prompt_hash: str,
    status: str = "pending",
    r2_key: Optional[str] = None,
    file_size_bytes: Optional[int] = None,
    error: Optional[str] = None,
    cached: bool = False,
) -> GeneratedImage:
    image = GeneratedImage(
        book_job_id=book_job_id,
        user_id=user_id,
        page_number=page_number,
        prompt=prompt,
        prompt_hash=prompt_hash,
        status=status,
        r2_key=r2_key,
        file_size_bytes=file_size_bytes,
        error=error,
        cached=cached,
    )
    session.add(image)
    await session.commit()
    await session.refresh(image)
    return image


async def update_generated_image(
    session: AsyncSession,
    image_id: uuid.UUID,
    **kwargs,
) -> None:
    await session.execute(
        update(GeneratedImage)
        .where(GeneratedImage.id == image_id)
        .values(**kwargs)
    )
    await session.commit()


async def find_cached_image_by_hash(
    session: AsyncSession,
    prompt_hash: str,
) -> Optional[GeneratedImage]:
    """Find any completed image with a matching prompt hash (for cross-book cache)."""
    result = await session.execute(
        select(GeneratedImage)
        .where(
            GeneratedImage.prompt_hash == prompt_hash,
            GeneratedImage.status == "completed",
            GeneratedImage.r2_key.isnot(None),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_images_for_book(
    session: AsyncSession,
    book_job_id: uuid.UUID,
) -> list[GeneratedImage]:
    result = await session.execute(
        select(GeneratedImage)
        .where(GeneratedImage.book_job_id == book_job_id)
        .order_by(GeneratedImage.page_number)
    )
    return list(result.scalars().all())


async def get_failed_images_for_book(
    session: AsyncSession,
    book_job_id: uuid.UUID,
) -> list[GeneratedImage]:
    """Get all failed images for a book job."""
    result = await session.execute(
        select(GeneratedImage)
        .where(
            GeneratedImage.book_job_id == book_job_id,
            GeneratedImage.status == "failed",
        )
        .order_by(GeneratedImage.page_number)
    )
    return list(result.scalars().all())


async def get_batch_image_status(
    session: AsyncSession,
    book_job_ids: list[uuid.UUID],
    user_id: uuid.UUID,
) -> list[dict]:
    """Get image status summary (total + failed count) for multiple books in one query."""
    if not book_job_ids:
        return []
    result = await session.execute(
        select(
            GeneratedImage.book_job_id,
            func.count().label("total_images"),
            func.sum(
                case((GeneratedImage.status == "failed", 1), else_=0)
            ).label("failed_images"),
        )
        .where(
            GeneratedImage.book_job_id.in_(book_job_ids),
            GeneratedImage.user_id == user_id,
        )
        .group_by(GeneratedImage.book_job_id)
    )
    return [
        {
            "job_id": str(row.book_job_id),
            "total_images": row.total_images,
            "failed_images": row.failed_images,
            "has_failed_images": row.failed_images > 0,
        }
        for row in result.all()
    ]


async def count_completed_books_for_user(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> int:
    """Count total completed books for a user (for accurate pagination)."""
    result = await session.execute(
        select(func.count())
        .select_from(BookJob)
        .where(BookJob.user_id == user_id, BookJob.status == "completed")
    )
    return result.scalar_one()


async def reset_image_for_retry(
    session: AsyncSession,
    image_id: uuid.UUID,
    retry_attempt: int,
) -> None:
    """Reset a failed image to pending for retry."""
    from datetime import datetime, timezone

    await session.execute(
        update(GeneratedImage)
        .where(GeneratedImage.id == image_id)
        .values(
            status="pending",
            error=None,
            retry_attempt=retry_attempt,
            retried_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()


async def delete_pdfs_for_book(
    session: AsyncSession,
    book_job_id: uuid.UUID,
) -> list[str]:
    """Delete all PDF rows for a book and return their R2 keys for cleanup."""
    result = await session.execute(
        select(GeneratedPdf).where(GeneratedPdf.book_job_id == book_job_id)
    )
    pdfs = result.scalars().all()
    r2_keys = [pdf.file_path for pdf in pdfs]

    await session.execute(
        delete(GeneratedPdf).where(GeneratedPdf.book_job_id == book_job_id)
    )
    await session.commit()
    return r2_keys
