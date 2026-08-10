"""dinner_history: composite primary key (recipe_id, served_on)

Enforces one dinner per recipe per day, so "cooked it today" can no longer create
duplicate history rows for the same recipe.

Revision ID: c1d2e3f4a5b6
Revises: 32316ea85c11
Create Date: 2026-08-11 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c1d2e3f4a5b6'
down_revision: str | Sequence[str] | None = '32316ea85c11'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Drop title-only rows (no recipe_id) — they can't satisfy the NOT NULL composite key.
    op.execute("DELETE FROM dinner_history WHERE recipe_id IS NULL")
    # 2. Collapse existing duplicate (recipe_id, served_on) rows, keeping the lowest id.
    op.execute(
        """
        DELETE FROM dinner_history a
        USING dinner_history b
        WHERE a.recipe_id = b.recipe_id
          AND a.served_on = b.served_on
          AND a.id > b.id
        """
    )
    # 3. Rebuild the primary key as (recipe_id, served_on).
    op.drop_constraint('dinner_history_pkey', 'dinner_history', type_='primary')
    op.drop_column('dinner_history', 'id')
    op.alter_column('dinner_history', 'recipe_id', existing_type=sa.Integer(), nullable=False)
    op.drop_index('ix_dinner_history_recipe_id', table_name='dinner_history')
    op.create_primary_key('dinner_history_pkey', 'dinner_history', ['recipe_id', 'served_on'])
    # 4. recipe_id is now a NOT NULL PK column, so ON DELETE SET NULL is invalid -> CASCADE.
    op.drop_constraint('dinner_history_recipe_id_fkey', 'dinner_history', type_='foreignkey')
    op.create_foreign_key(
        'dinner_history_recipe_id_fkey', 'dinner_history', 'recipes',
        ['recipe_id'], ['id'], ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('dinner_history_recipe_id_fkey', 'dinner_history', type_='foreignkey')
    op.drop_constraint('dinner_history_pkey', 'dinner_history', type_='primary')
    op.add_column(
        'dinner_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    )
    op.create_primary_key('dinner_history_pkey', 'dinner_history', ['id'])
    op.alter_column('dinner_history', 'recipe_id', existing_type=sa.Integer(), nullable=True)
    op.create_index('ix_dinner_history_recipe_id', 'dinner_history', ['recipe_id'], unique=False)
    op.create_foreign_key(
        'dinner_history_recipe_id_fkey', 'dinner_history', 'recipes',
        ['recipe_id'], ['id'], ondelete='SET NULL',
    )
