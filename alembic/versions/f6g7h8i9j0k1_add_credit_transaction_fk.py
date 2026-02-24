"""add credit_transaction_id FK to user_credits

Revision ID: f6g7h8i9j0k1
Revises: e5f6g7h8i9j0
Create Date: 2026-02-24 12:01:00.000000
"""
from typing import Sequence, Union
from alembic import op


revision: str = "f6g7h8i9j0k1"
down_revision: Union[str, None] = "e5f6g7h8i9j0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add credit_transaction_id column (nullable — signup_bonus rows have no transaction)
    op.execute("""
        ALTER TABLE user_credits
            ADD COLUMN credit_transaction_id uuid
            REFERENCES credit_transactions(id);
    """)

    # 2. Add unique constraint (one-to-one: each transaction maps to one credit batch)
    op.execute("""
        CREATE UNIQUE INDEX idx_user_credits_credit_transaction_id
        ON user_credits (credit_transaction_id)
        WHERE credit_transaction_id IS NOT NULL;
    """)

    # 3. Drop old stripe_session_id column and its unique index from user_credits
    op.execute("DROP INDEX IF EXISTS idx_user_credits_stripe_session_id;")
    op.execute("ALTER TABLE user_credits DROP COLUMN IF EXISTS stripe_session_id;")


def downgrade() -> None:
    # Restore stripe_session_id
    op.execute("ALTER TABLE user_credits ADD COLUMN stripe_session_id text;")
    op.execute("""
        CREATE UNIQUE INDEX idx_user_credits_stripe_session_id
        ON user_credits (stripe_session_id)
        WHERE stripe_session_id IS NOT NULL;
    """)

    # Drop credit_transaction_id
    op.execute("DROP INDEX IF EXISTS idx_user_credits_credit_transaction_id;")
    op.execute("ALTER TABLE user_credits DROP COLUMN IF EXISTS credit_transaction_id;")
