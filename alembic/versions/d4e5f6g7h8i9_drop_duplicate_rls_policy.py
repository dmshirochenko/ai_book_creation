"""drop duplicate user_credits RLS policy

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-02-22 22:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "d4e5f6g7h8i9"
down_revision: Union[str, None] = "c3d4e5f6g7h8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('DROP POLICY IF EXISTS "user_credits_select_own" ON user_credits;')


def downgrade() -> None:
    op.execute("""
        CREATE POLICY user_credits_select_own ON user_credits
            FOR SELECT USING (auth.uid() = user_id);
    """)
