"""add composite indexes for common query patterns

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-02-28 22:00:00.000000
"""
from typing import Sequence, Union
from alembic import op


revision: str = "o5p6q7r8s9t0"
down_revision: Union[str, None] = "n4o5p6q7r8s9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # BookJob: list_book_jobs_for_user filters by (user_id) excluding status='deleted'
    op.create_index(
        "idx_book_jobs_user_id_status",
        "book_jobs",
        ["user_id", "status"],
    )
    # StoryJob: list queries filter by user_id + status
    op.create_index(
        "idx_story_jobs_user_id_status",
        "story_jobs",
        ["user_id", "status"],
    )
    # GeneratedImage: cache lookup by prompt_hash + status='completed'
    op.create_index(
        "idx_generated_images_prompt_hash_status",
        "generated_images",
        ["prompt_hash", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_generated_images_prompt_hash_status", table_name="generated_images")
    op.drop_index("idx_story_jobs_user_id_status", table_name="story_jobs")
    op.drop_index("idx_book_jobs_user_id_status", table_name="book_jobs")
