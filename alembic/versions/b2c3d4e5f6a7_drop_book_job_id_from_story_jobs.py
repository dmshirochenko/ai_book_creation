"""drop book_job_id from story_jobs

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("idx_story_jobs_book_job_id", table_name="story_jobs")
    op.drop_constraint("story_jobs_book_job_id_fkey", table_name="story_jobs", type_="foreignkey")
    op.drop_column("story_jobs", "book_job_id")


def downgrade() -> None:
    op.add_column(
        "story_jobs",
        sa.Column("book_job_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "story_jobs_book_job_id_fkey",
        "story_jobs",
        "book_jobs",
        ["book_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_story_jobs_book_job_id", "story_jobs", ["book_job_id"])
