"""add safety fields to story_jobs

Revision ID: a1b2c3d4e5f6
Revises: f7a8b9c0d1e2
Create Date: 2026-02-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("story_jobs", sa.Column("safety_status", sa.String(20), nullable=True))
    op.add_column("story_jobs", sa.Column("safety_reasoning", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("story_jobs", "safety_reasoning")
    op.drop_column("story_jobs", "safety_status")
