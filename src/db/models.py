"""
SQLAlchemy async ORM models for job persistence.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    String,
    Integer,
    BigInteger,
    Text,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Index,
    Numeric,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class BookJob(Base):
    __tablename__ = "book_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    progress: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    booklet_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    pdfs: Mapped[list["GeneratedPdf"]] = relationship(
        back_populates="book_job", cascade="all, delete-orphan"
    )
    images: Mapped[list["GeneratedImage"]] = relationship(
        back_populates="book_job", cascade="all, delete-orphan"
    )
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed', 'deleted')",
            name="ck_book_jobs_status",
        ),
        Index("idx_book_jobs_user_id", "user_id"),
        Index("idx_book_jobs_status", "status"),
        Index("idx_book_jobs_created_at", "created_at"),
        Index("idx_book_jobs_user_id_status", "user_id", "status"),
    )


class StoryJob(Base):
    __tablename__ = "story_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    progress: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    safety_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    safety_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)

    generated_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_story: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_story_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    story_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)

    request_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_story_jobs_status",
        ),
        Index("idx_story_jobs_user_id", "user_id"),
        Index("idx_story_jobs_status", "status"),
        Index("idx_story_jobs_user_id_status", "user_id", "status"),
    )


class GeneratedPdf(Base):
    __tablename__ = "generated_pdfs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    book_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("book_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    pdf_type: Mapped[str] = mapped_column(String(10), nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    book_job: Mapped["BookJob"] = relationship(back_populates="pdfs")

    __table_args__ = (
        CheckConstraint(
            "pdf_type IN ('booklet', 'review')",
            name="ck_generated_pdfs_type",
        ),
        Index("idx_generated_pdfs_user_id", "user_id"),
        Index("idx_generated_pdfs_book_job_id", "book_job_id"),
    )


class GeneratedImage(Base):
    __tablename__ = "generated_images"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    book_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("book_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    r2_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    image_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retry_attempt: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    retried_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    book_job: Mapped["BookJob"] = relationship(back_populates="images")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_generated_images_status",
        ),
        Index("idx_generated_images_book_job_id", "book_job_id"),
        Index("idx_generated_images_prompt_hash", "prompt_hash"),
        Index("idx_generated_images_user_id", "user_id"),
        Index("idx_generated_images_prompt_hash_status", "prompt_hash", "status"),
    )


class UserCredits(Base):
    """Per-batch credit ledger. Each purchase or bonus is a separate row."""
    __tablename__ = "user_credits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    original_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    remaining_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    credit_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("credit_transactions.id"),
        nullable=True,
    )
    is_refunded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        CheckConstraint(
            "remaining_amount >= 0",
            name="ck_user_credits_remaining_non_negative",
        ),
        CheckConstraint(
            "remaining_amount <= original_amount",
            name="ck_user_credits_remaining_lte_original",
        ),
        Index("idx_user_credits_user_id", "user_id"),
        Index(
            "idx_user_credits_credit_transaction_id",
            "credit_transaction_id",
            unique=True,
            postgresql_where=text("credit_transaction_id IS NOT NULL"),
        ),
    )


class CreditPricing(Base):
    __tablename__ = "credit_pricing"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    operation: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    credit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_image_model: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class CreditUsageLog(Base):
    __tablename__ = "credit_usage_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(20), nullable=False)
    credits_used: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="reserved"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    reserved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('reserved', 'confirmed', 'released')",
            name="ck_credit_usage_logs_status",
        ),
        CheckConstraint(
            "job_type IN ('story', 'book')",
            name="ck_credit_usage_logs_job_type",
        ),
        Index("idx_credit_usage_logs_user_id", "user_id"),
        Index("idx_credit_usage_logs_status", "status"),
        Index("idx_credit_usage_logs_created_at", "created_at"),
    )


class CreditTransaction(Base):
    """Immutable Stripe transaction ledger. Single entry point for all money events."""
    __tablename__ = "credit_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="completed"
    )
    stripe_session_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    stripe_event_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        CheckConstraint(
            "transaction_type IN ('purchase', 'refund')",
            name="ck_credit_transactions_type",
        ),
        CheckConstraint(
            "status IN ('completed', 'refunded')",
            name="ck_credit_transactions_status",
        ),
        Index("idx_credit_transactions_user_id", "user_id"),
        Index(
            "idx_credit_transactions_stripe_event_id",
            "stripe_event_id",
            unique=True,
            postgresql_where=text("stripe_event_id IS NOT NULL"),
        ),
        Index(
            "idx_credit_transactions_stripe_session_id",
            "stripe_session_id",
            postgresql_where=text("stripe_session_id IS NOT NULL"),
        ),
    )


class IllustrationStyle(Base):
    """System-wide illustration style definitions for book generation."""
    __tablename__ = "illustration_styles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    prompt_string: Mapped[str] = mapped_column(Text, nullable=False)
    icon_name: Mapped[str] = mapped_column(String(50), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    preview_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_illustration_styles_slug", "slug"),
        Index("idx_illustration_styles_display_order", "display_order"),
    )
