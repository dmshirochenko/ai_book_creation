"""redesign credit_transactions for ledger-first architecture

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2026-02-24 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op


revision: str = "e5f6g7h8i9j0"
down_revision: Union[str, None] = "d4e5f6g7h8i9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Delete old test data (2 rows from pre-restructure era)
    op.execute("DELETE FROM credit_transactions;")

    # 2. Drop old columns
    op.execute("""
        ALTER TABLE credit_transactions
            DROP COLUMN IF EXISTS amount,
            DROP COLUMN IF EXISTS type,
            DROP COLUMN IF EXISTS description;
    """)

    # 3. Add new columns
    op.execute("""
        ALTER TABLE credit_transactions
            ADD COLUMN amount numeric(10,2) NOT NULL DEFAULT 0,
            ADD COLUMN transaction_type varchar(30) NOT NULL DEFAULT 'purchase',
            ADD COLUMN stripe_event_id text,
            ADD COLUMN metadata jsonb;
    """)

    # 4. Remove defaults (they were just for the ALTER)
    op.execute("""
        ALTER TABLE credit_transactions
            ALTER COLUMN amount DROP DEFAULT,
            ALTER COLUMN transaction_type DROP DEFAULT;
    """)

    # 5. Add unique constraint on stripe_event_id for idempotency
    op.execute("""
        CREATE UNIQUE INDEX idx_credit_transactions_stripe_event_id
        ON credit_transactions (stripe_event_id)
        WHERE stripe_event_id IS NOT NULL;
    """)

    # 6. Add index on stripe_session_id for refund lookups
    op.execute("""
        CREATE INDEX idx_credit_transactions_stripe_session_id
        ON credit_transactions (stripe_session_id)
        WHERE stripe_session_id IS NOT NULL;
    """)

    # 7. Add index on user_id
    op.execute("""
        CREATE INDEX idx_credit_transactions_user_id
        ON credit_transactions (user_id);
    """)

    # 8. Add check constraint on transaction_type
    op.execute("""
        ALTER TABLE credit_transactions
            ADD CONSTRAINT ck_credit_transactions_type
            CHECK (transaction_type IN ('purchase', 'refund'));
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE credit_transactions DROP CONSTRAINT IF EXISTS ck_credit_transactions_type;")
    op.execute("DROP INDEX IF EXISTS idx_credit_transactions_user_id;")
    op.execute("DROP INDEX IF EXISTS idx_credit_transactions_stripe_session_id;")
    op.execute("DROP INDEX IF EXISTS idx_credit_transactions_stripe_event_id;")

    op.execute("""
        ALTER TABLE credit_transactions
            DROP COLUMN IF EXISTS metadata,
            DROP COLUMN IF EXISTS stripe_event_id,
            DROP COLUMN IF EXISTS transaction_type,
            DROP COLUMN IF EXISTS amount;
    """)

    op.execute("""
        ALTER TABLE credit_transactions
            ADD COLUMN amount integer NOT NULL DEFAULT 0,
            ADD COLUMN type varchar NOT NULL DEFAULT 'purchase',
            ADD COLUMN description text;
    """)
