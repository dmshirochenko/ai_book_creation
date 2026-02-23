"""create credit_transaction propagation trigger

Revision ID: g7h8i9j0k1l2
Revises: f6g7h8i9j0k1
Create Date: 2026-02-24 12:02:00.000000
"""
from typing import Sequence, Union
from alembic import op


revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, None] = "f6g7h8i9j0k1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION propagate_credit_transaction()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.transaction_type = 'purchase' THEN
                INSERT INTO user_credits (
                    user_id, original_amount, remaining_amount, source, credit_transaction_id
                ) VALUES (
                    NEW.user_id, NEW.amount, NEW.amount, 'purchase', NEW.id
                );
            ELSIF NEW.transaction_type = 'refund' THEN
                UPDATE user_credits
                SET is_refunded = true, updated_at = now()
                WHERE credit_transaction_id = (
                    SELECT ct.id FROM credit_transactions ct
                    WHERE ct.stripe_session_id = NEW.stripe_session_id
                    AND ct.transaction_type = 'purchase'
                    LIMIT 1
                );
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
    """)

    op.execute("""
        CREATE TRIGGER trg_credit_transaction_propagate
            AFTER INSERT ON credit_transactions
            FOR EACH ROW
            EXECUTE FUNCTION propagate_credit_transaction();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_credit_transaction_propagate ON credit_transactions;")
    op.execute("DROP FUNCTION IF EXISTS propagate_credit_transaction();")
