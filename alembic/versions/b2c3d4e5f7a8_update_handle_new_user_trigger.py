"""update handle_new_user trigger for per-batch credits

Revision ID: b2c3d4e5f7a8
Revises: a1b2c3d4e5f7
Create Date: 2026-02-22 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "b2c3d4e5f7a8"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION public.handle_new_user()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path TO 'public'
        AS $function$
        BEGIN
          INSERT INTO public.profiles (user_id, display_name)
          VALUES (NEW.id, NEW.raw_user_meta_data->>'display_name');
          INSERT INTO public.user_credits (user_id, original_amount, remaining_amount, source)
          VALUES (NEW.id, 1, 1, 'signup_bonus');
          RETURN NEW;
        END;
        $function$;
    """)


def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION public.handle_new_user()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path TO 'public'
        AS $function$
        BEGIN
          INSERT INTO public.profiles (user_id, display_name)
          VALUES (NEW.id, NEW.raw_user_meta_data->>'display_name');
          INSERT INTO public.user_credits (user_id, balance)
          VALUES (NEW.id, 0);
          RETURN NEW;
        END;
        $function$;
    """)
