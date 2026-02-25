"""add job_type check constraint to credit_usage_logs

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-02-25 23:00:00.000000
"""
from typing import Sequence, Union
from alembic import op


revision: str = "i9j0k1l2m3n4"
down_revision: Union[str, None] = "h8i9j0k1l2m3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE credit_usage_logs
            ADD CONSTRAINT ck_credit_usage_logs_job_type
            CHECK (job_type IN ('story', 'book'));
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE credit_usage_logs
            DROP CONSTRAINT IF EXISTS ck_credit_usage_logs_job_type;
    """)
