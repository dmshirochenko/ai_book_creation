"""add generated_images table

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-02-08 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generated_images",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "book_job_id",
            UUID(as_uuid=True),
            sa.ForeignKey("book_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("auth.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer, nullable=False),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("prompt_hash", sa.String(32), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("r2_key", sa.Text, nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("cached", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_generated_images_status",
        ),
    )
    op.create_index(
        "idx_generated_images_book_job_id", "generated_images", ["book_job_id"]
    )
    op.create_index(
        "idx_generated_images_prompt_hash", "generated_images", ["prompt_hash"]
    )
    op.create_index(
        "idx_generated_images_user_id", "generated_images", ["user_id"]
    )

    # Row Level Security
    op.execute("ALTER TABLE generated_images ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY "Users can view own images"
            ON generated_images FOR SELECT USING (auth.uid() = user_id);
    """)


def downgrade() -> None:
    op.execute(
        'DROP POLICY IF EXISTS "Users can view own images" ON generated_images;'
    )
    op.drop_table("generated_images")
