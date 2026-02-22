"""restructure user_credits and add credit tables

Revision ID: a1b2c3d4e5f7
Revises: f7a8b9c0d1e2
Create Date: 2026-02-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Part 1: Restructure user_credits ---

    # Add new columns (nullable initially)
    op.execute("""
        ALTER TABLE user_credits
            ADD COLUMN original_amount numeric(10,2),
            ADD COLUMN remaining_amount numeric(10,2),
            ADD COLUMN source varchar(30),
            ADD COLUMN stripe_session_id text,
            ADD COLUMN is_refunded boolean NOT NULL DEFAULT false;
    """)

    # Migrate existing data from balance to new columns
    op.execute("""
        UPDATE user_credits
        SET original_amount = balance::numeric(10,2),
            remaining_amount = balance::numeric(10,2),
            source = CASE WHEN balance > 0 THEN 'purchase' ELSE 'signup_bonus' END;
    """)

    # Make new columns NOT NULL after data migration
    op.execute("""
        ALTER TABLE user_credits
            ALTER COLUMN original_amount SET NOT NULL,
            ALTER COLUMN remaining_amount SET NOT NULL,
            ALTER COLUMN source SET NOT NULL;
    """)

    # Drop the old balance column
    op.execute("""
        ALTER TABLE user_credits DROP COLUMN balance;
    """)

    # Drop the UNIQUE constraint on user_id (now one user can have multiple credit rows)
    op.execute("""
        ALTER TABLE user_credits DROP CONSTRAINT user_credits_user_id_key;
    """)

    # Add check constraints
    op.execute("""
        ALTER TABLE user_credits
            ADD CONSTRAINT ck_user_credits_remaining_non_negative CHECK (remaining_amount >= 0),
            ADD CONSTRAINT ck_user_credits_remaining_lte_original CHECK (remaining_amount <= original_amount);
    """)

    # Add partial index for efficient lookup of available credits
    op.execute("""
        CREATE INDEX idx_user_credits_remaining ON user_credits (user_id, is_refunded) WHERE remaining_amount > 0;
    """)

    # --- Part 2: Create credit_pricing table ---

    op.execute("""
        CREATE TABLE IF NOT EXISTS credit_pricing (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            operation varchar(50) UNIQUE NOT NULL,
            credit_cost numeric(10,2) NOT NULL,
            description text,
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
    """)

    op.execute("""
        CREATE TRIGGER update_credit_pricing_updated_at
            BEFORE UPDATE ON credit_pricing
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    op.execute("""
        ALTER TABLE credit_pricing ENABLE ROW LEVEL SECURITY;
    """)

    op.execute("""
        CREATE POLICY "Authenticated users can read pricing"
            ON credit_pricing FOR SELECT TO authenticated USING (true);
    """)

    op.execute("""
        INSERT INTO credit_pricing (operation, credit_cost, description) VALUES
            ('story_generation', 1.0, 'Story text generation'),
            ('page_with_images', 2.0, 'Per page with image generation'),
            ('page_without_images', 1.0, 'Per page without image generation');
    """)

    # --- Part 3: Create credit_usage_logs table ---

    op.execute("""
        CREATE TABLE IF NOT EXISTS credit_usage_logs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            job_id uuid NOT NULL,
            job_type varchar(20) NOT NULL,
            credits_used numeric(10,2) NOT NULL,
            status varchar(20) NOT NULL DEFAULT 'reserved',
            description text,
            metadata jsonb,
            reserved_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
    """)

    op.execute("""
        CREATE INDEX idx_credit_usage_logs_user_id ON credit_usage_logs(user_id);
    """)

    op.execute("""
        CREATE INDEX idx_credit_usage_logs_created_at ON credit_usage_logs(created_at);
    """)

    op.execute("""
        CREATE INDEX idx_credit_usage_logs_status ON credit_usage_logs(status);
    """)

    op.execute("""
        CREATE TRIGGER update_credit_usage_logs_updated_at
            BEFORE UPDATE ON credit_usage_logs
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    op.execute("""
        ALTER TABLE credit_usage_logs ENABLE ROW LEVEL SECURITY;
    """)

    op.execute("""
        CREATE POLICY "Users can view own usage logs"
            ON credit_usage_logs FOR SELECT TO authenticated USING (auth.uid() = user_id);
    """)


def downgrade() -> None:
    # --- Reverse Part 3: Drop credit_usage_logs ---

    op.execute("""
        DROP POLICY IF EXISTS "Users can view own usage logs" ON credit_usage_logs;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS update_credit_usage_logs_updated_at ON credit_usage_logs;
    """)

    op.execute("""
        DROP INDEX IF EXISTS idx_credit_usage_logs_user_id;
    """)

    op.execute("""
        DROP INDEX IF EXISTS idx_credit_usage_logs_created_at;
    """)

    op.execute("""
        DROP INDEX IF EXISTS idx_credit_usage_logs_status;
    """)

    op.execute("""
        DROP TABLE IF EXISTS credit_usage_logs;
    """)

    # --- Reverse Part 2: Drop credit_pricing ---

    op.execute("""
        DROP POLICY IF EXISTS "Authenticated users can read pricing" ON credit_pricing;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS update_credit_pricing_updated_at ON credit_pricing;
    """)

    op.execute("""
        DROP TABLE IF EXISTS credit_pricing;
    """)

    # --- Reverse Part 1: Restore user_credits ---

    # Drop new indexes and constraints
    op.execute("""
        DROP INDEX IF EXISTS idx_user_credits_remaining;
    """)

    op.execute("""
        ALTER TABLE user_credits
            DROP CONSTRAINT IF EXISTS ck_user_credits_remaining_non_negative,
            DROP CONSTRAINT IF EXISTS ck_user_credits_remaining_lte_original;
    """)

    # Add balance column back
    op.execute("""
        ALTER TABLE user_credits ADD COLUMN balance integer;
    """)

    # Migrate data back from remaining_amount to balance
    op.execute("""
        UPDATE user_credits SET balance = remaining_amount::integer;
    """)

    # Make balance NOT NULL
    op.execute("""
        ALTER TABLE user_credits ALTER COLUMN balance SET NOT NULL;
    """)

    # Drop new columns
    op.execute("""
        ALTER TABLE user_credits
            DROP COLUMN original_amount,
            DROP COLUMN remaining_amount,
            DROP COLUMN source,
            DROP COLUMN stripe_session_id,
            DROP COLUMN is_refunded;
    """)

    # Re-add UNIQUE constraint on user_id
    op.execute("""
        ALTER TABLE user_credits ADD CONSTRAINT user_credits_user_id_key UNIQUE (user_id);
    """)
