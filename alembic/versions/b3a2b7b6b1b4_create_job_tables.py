"""create job tables

Revision ID: b3a2b7b6b1b4
Revises:
Create Date: 2026-02-06 01:07:32.986970

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision: str = 'b3a2b7b6b1b4'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # book_jobs
    op.create_table(
        "book_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("progress", sa.Text, nullable=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("total_pages", sa.Integer, nullable=True),
        sa.Column("booklet_filename", sa.Text, nullable=True),
        sa.Column("review_filename", sa.Text, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("request_params", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('pending', 'processing', 'completed', 'failed')", name="ck_book_jobs_status"),
    )
    op.create_index("idx_book_jobs_user_id", "book_jobs", ["user_id"])
    op.create_index("idx_book_jobs_status", "book_jobs", ["status"])
    op.create_index("idx_book_jobs_created_at", "book_jobs", [sa.text("created_at DESC")])

    # story_jobs
    op.create_table(
        "story_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("progress", sa.Text, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("generated_title", sa.Text, nullable=True),
        sa.Column("generated_story", sa.Text, nullable=True),
        sa.Column("story_length", sa.Integer, nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=True),
        sa.Column("book_job_id", UUID(as_uuid=True), sa.ForeignKey("book_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("request_params", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('pending', 'processing', 'completed', 'failed')", name="ck_story_jobs_status"),
    )
    op.create_index("idx_story_jobs_user_id", "story_jobs", ["user_id"])
    op.create_index("idx_story_jobs_status", "story_jobs", ["status"])
    op.create_index("idx_story_jobs_book_job_id", "story_jobs", ["book_job_id"])

    # generated_pdfs
    op.create_table(
        "generated_pdfs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("book_job_id", UUID(as_uuid=True), sa.ForeignKey("book_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pdf_type", sa.String(10), nullable=False),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("pdf_type IN ('booklet', 'review')", name="ck_generated_pdfs_type"),
    )
    op.create_index("idx_generated_pdfs_user_id", "generated_pdfs", ["user_id"])
    op.create_index("idx_generated_pdfs_book_job_id", "generated_pdfs", ["book_job_id"])

    # Triggers for auto-updating updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION public.update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER update_book_jobs_updated_at
            BEFORE UPDATE ON book_jobs
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    op.execute("""
        CREATE TRIGGER update_story_jobs_updated_at
            BEFORE UPDATE ON story_jobs
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # Row Level Security
    op.execute("ALTER TABLE book_jobs ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE story_jobs ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE generated_pdfs ENABLE ROW LEVEL SECURITY;")

    op.execute("""
        CREATE POLICY "Users can view own book jobs"
            ON book_jobs FOR SELECT USING (auth.uid() = user_id);
    """)
    op.execute("""
        CREATE POLICY "Users can view own story jobs"
            ON story_jobs FOR SELECT USING (auth.uid() = user_id);
    """)
    op.execute("""
        CREATE POLICY "Users can view own PDFs"
            ON generated_pdfs FOR SELECT USING (auth.uid() = user_id);
    """)


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS "Users can view own PDFs" ON generated_pdfs;')
    op.execute('DROP POLICY IF EXISTS "Users can view own story jobs" ON story_jobs;')
    op.execute('DROP POLICY IF EXISTS "Users can view own book jobs" ON book_jobs;')
    op.execute("DROP TRIGGER IF EXISTS update_story_jobs_updated_at ON story_jobs;")
    op.execute("DROP TRIGGER IF EXISTS update_book_jobs_updated_at ON book_jobs;")
    op.drop_table("generated_pdfs")
    op.drop_table("story_jobs")
    op.drop_table("book_jobs")
