"""create illustration_styles table

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-02-28 18:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "m3n4o5p6q7r8"
down_revision: Union[str, None] = "l2m3n4o5p6q7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "illustration_styles",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.String(50), unique=True, nullable=False),
        sa.Column("prompt_string", sa.Text, nullable=False),
        sa.Column("icon_name", sa.String(50), nullable=False),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("preview_image_url", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_illustration_styles_slug", "illustration_styles", ["slug"])
    op.create_index(
        "idx_illustration_styles_display_order", "illustration_styles", ["display_order"]
    )

    # Seed initial illustration styles
    op.execute(sa.text("""
        INSERT INTO illustration_styles (slug, prompt_string, icon_name, display_order)
        VALUES
            ('watercolor',
             'children''s book illustration, soft watercolor style, gentle colors, simple shapes, cute and friendly',
             'droplets', 1),
            ('2d-cartoon',
             'children''s book illustration, 2D cartoon style, bold clean outlines, vibrant flat colors, expressive characters, playful and dynamic',
             'film', 2),
            ('3d-cartoon',
             'children''s book illustration, 3D rendered cartoon style, smooth rounded shapes, soft vibrant lighting, Pixar-like quality, warm and inviting',
             'box', 3),
            ('3d-realistic',
             'children''s book illustration, 3D hyper-realistic style, photorealistic textures, detailed lighting and soft shadows, cinematic quality',
             'camera', 4),
            ('flat-minimal',
             'children''s book illustration, flat minimalist illustration style, geometric shapes, limited color palette, clean lines, modern and elegant',
             'hexagon', 5)
    """))


def downgrade() -> None:
    op.drop_index("idx_illustration_styles_display_order", table_name="illustration_styles")
    op.drop_index("idx_illustration_styles_slug", table_name="illustration_styles")
    op.drop_table("illustration_styles")
