"""add display_order to credit_pricing

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-02-28 19:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "n4o5p6q7r8s9"
down_revision: Union[str, None] = "m3n4o5p6q7r8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "credit_pricing",
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
    )

    # Backfill display_order for existing image models
    op.execute(sa.text("""
        UPDATE credit_pricing SET display_order = 1
        WHERE operation = 'google/gemini-2.5-flash-image'
    """))
    op.execute(sa.text("""
        UPDATE credit_pricing SET display_order = 2
        WHERE operation = 'openai/gpt-5-image-mini'
    """))
    op.execute(sa.text("""
        UPDATE credit_pricing SET display_order = 3
        WHERE operation = 'bytedance-seed/seedream-4.5'
    """))


def downgrade() -> None:
    op.drop_column("credit_pricing", "display_order")
