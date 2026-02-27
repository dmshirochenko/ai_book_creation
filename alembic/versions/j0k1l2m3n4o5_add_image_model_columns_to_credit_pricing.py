"""add display_name and is_image_model columns to credit_pricing

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-02-27 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op


revision: str = "j0k1l2m3n4o5"
down_revision: Union[str, None] = "i9j0k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns
    op.execute("""
        ALTER TABLE credit_pricing
            ADD COLUMN display_name varchar(100),
            ADD COLUMN is_image_model boolean NOT NULL DEFAULT false;
    """)

    # Deactivate old flat-rate page_with_images row
    op.execute("""
        UPDATE credit_pricing SET is_active = false WHERE operation = 'page_with_images';
    """)

    # Insert per-model pricing rows
    op.execute("""
        INSERT INTO credit_pricing (operation, credit_cost, description, display_name, is_image_model) VALUES
            ('google/gemini-2.5-flash-image', 2.0, 'Per page with Gemini Flash images', 'Gemini Flash', true),
            ('openai/gpt-4o', 3.0, 'Per page with GPT-4o images', 'GPT-4o', true),
            ('google/gemini-2.5-pro-preview', 4.0, 'Per page with Gemini 2.5 Pro images', 'Gemini 2.5 Pro', true);
    """)


def downgrade() -> None:
    # Remove model pricing rows
    op.execute("""
        DELETE FROM credit_pricing WHERE is_image_model = true;
    """)

    # Re-activate old flat-rate row
    op.execute("""
        UPDATE credit_pricing SET is_active = true WHERE operation = 'page_with_images';
    """)

    # Drop new columns
    op.execute("""
        ALTER TABLE credit_pricing
            DROP COLUMN IF EXISTS display_name,
            DROP COLUMN IF EXISTS is_image_model;
    """)
