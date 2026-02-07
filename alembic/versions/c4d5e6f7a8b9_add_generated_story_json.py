"""add generated_story_json to story_jobs

Revision ID: c4d5e6f7a8b9
Revises: b3a2b7b6b1b4
Create Date: 2026-02-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3a2b7b6b1b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "story_jobs",
        sa.Column("generated_story_json", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("story_jobs", "generated_story_json")
