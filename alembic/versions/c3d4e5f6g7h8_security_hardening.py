"""security hardening: constraints, indexes, RLS

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f7a8
Create Date: 2026-02-22 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c3d4e5f6g7h8"
down_revision: Union[str, None] = "b2c3d4e5f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Unique partial index on stripe_session_id (prevents duplicate Stripe webhook credit grants)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_user_credits_stripe_session_id
        ON user_credits (stripe_session_id)
        WHERE stripe_session_id IS NOT NULL;
    """)

    # 2. Unique partial index: one signup_bonus per user
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_user_credits_one_signup_bonus
        ON user_credits (user_id)
        WHERE source = 'signup_bonus';
    """)

    # 3. Enable RLS on user_credits + SELECT policy for authenticated users
    op.execute("ALTER TABLE user_credits ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY user_credits_select_own ON user_credits
        FOR SELECT
        USING (auth.uid() = user_id);
    """)

    # 4. ALL policy on credit_usage_logs for service_role
    op.execute("ALTER TABLE credit_usage_logs ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY credit_usage_logs_service_role ON credit_usage_logs
        FOR ALL
        TO service_role
        USING (true)
        WITH CHECK (true);
    """)


def downgrade() -> None:
    # Remove RLS policies and disable RLS
    op.execute("DROP POLICY IF EXISTS credit_usage_logs_service_role ON credit_usage_logs;")
    op.execute("ALTER TABLE credit_usage_logs DISABLE ROW LEVEL SECURITY;")

    op.execute("DROP POLICY IF EXISTS user_credits_select_own ON user_credits;")
    op.execute("ALTER TABLE user_credits DISABLE ROW LEVEL SECURITY;")

    # Drop indexes
    op.execute("DROP INDEX IF EXISTS idx_user_credits_one_signup_bonus;")
    op.execute("DROP INDEX IF EXISTS idx_user_credits_stripe_session_id;")
