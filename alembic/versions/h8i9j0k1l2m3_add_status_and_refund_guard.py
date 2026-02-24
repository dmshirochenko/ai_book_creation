"""add status column to credit_transactions, refund guard, rename usage log status

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-02-24 14:00:00.000000
"""
from typing import Sequence, Union
from alembic import op


revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add status column to credit_transactions
    op.execute("""
        ALTER TABLE credit_transactions
            ADD COLUMN status varchar(20) NOT NULL DEFAULT 'completed';
    """)

    op.execute("""
        ALTER TABLE credit_transactions
            ADD CONSTRAINT ck_credit_transactions_status
            CHECK (status IN ('completed', 'refunded'));
    """)

    # 2. Rename 'refunded' -> 'released' in credit_usage_logs status values
    op.execute("""
        UPDATE credit_usage_logs SET status = 'released' WHERE status = 'refunded';
    """)

    # 3. Update check constraint on credit_usage_logs to use 'released' instead of 'refunded'
    op.execute("""
        ALTER TABLE credit_usage_logs DROP CONSTRAINT IF EXISTS ck_credit_usage_logs_status;
    """)
    op.execute("""
        ALTER TABLE credit_usage_logs
            ADD CONSTRAINT ck_credit_usage_logs_status
            CHECK (status IN ('reserved', 'confirmed', 'released'));
    """)

    # 4. Replace trigger function with refund guard + status update
    op.execute("""
        CREATE OR REPLACE FUNCTION propagate_credit_transaction()
        RETURNS TRIGGER AS $$
        DECLARE
            v_uc_remaining numeric;
            v_uc_original numeric;
        BEGIN
            IF NEW.transaction_type = 'purchase' THEN
                INSERT INTO user_credits (
                    user_id, original_amount, remaining_amount, source, credit_transaction_id
                ) VALUES (
                    NEW.user_id, NEW.amount, NEW.amount, 'purchase', NEW.id
                );
            ELSIF NEW.transaction_type = 'refund' THEN
                -- Look up the user_credits batch for the original purchase
                SELECT uc.remaining_amount, uc.original_amount
                INTO v_uc_remaining, v_uc_original
                FROM user_credits uc
                JOIN credit_transactions ct ON uc.credit_transaction_id = ct.id
                WHERE ct.stripe_session_id = NEW.stripe_session_id
                AND ct.transaction_type = 'purchase'
                LIMIT 1;

                -- Guard: only allow refund if credits are fully unused
                IF v_uc_remaining IS NULL THEN
                    RAISE EXCEPTION 'No matching purchase found for stripe_session_id %', NEW.stripe_session_id;
                END IF;

                IF v_uc_remaining < v_uc_original THEN
                    RAISE EXCEPTION 'Cannot refund: % of % credits already used', (v_uc_original - v_uc_remaining), v_uc_original;
                END IF;

                -- Mark the user_credits batch as refunded
                UPDATE user_credits
                SET is_refunded = true, updated_at = now()
                WHERE credit_transaction_id = (
                    SELECT ct.id FROM credit_transactions ct
                    WHERE ct.stripe_session_id = NEW.stripe_session_id
                    AND ct.transaction_type = 'purchase'
                    LIMIT 1
                );

                -- Mark the original purchase transaction as refunded
                UPDATE credit_transactions
                SET status = 'refunded'
                WHERE stripe_session_id = NEW.stripe_session_id
                AND transaction_type = 'purchase';
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public';
    """)


def downgrade() -> None:
    # Restore old trigger without guard
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
        $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public';
    """)

    # Revert usage log status rename
    op.execute("ALTER TABLE credit_usage_logs DROP CONSTRAINT IF EXISTS ck_credit_usage_logs_status;")
    op.execute("""
        ALTER TABLE credit_usage_logs
            ADD CONSTRAINT ck_credit_usage_logs_status
            CHECK (status IN ('reserved', 'confirmed', 'refunded'));
    """)
    op.execute("UPDATE credit_usage_logs SET status = 'refunded' WHERE status = 'released';")

    # Drop status from credit_transactions
    op.execute("ALTER TABLE credit_transactions DROP CONSTRAINT IF EXISTS ck_credit_transactions_status;")
    op.execute("ALTER TABLE credit_transactions DROP COLUMN IF EXISTS status;")
