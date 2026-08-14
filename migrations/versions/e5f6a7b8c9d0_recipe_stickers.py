"""recipe_stickers: post-cook handwritten notes

Adds recipe_stickers — a note pinned to a recipe (general), a section, or a Method step.
Step pins reference recipe_steps.id with ON DELETE SET NULL, so deleting a step demotes
the sticker to general rather than deleting it.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-11 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: str | Sequence[str] | None = 'd4e5f6a7b8c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'recipe_stickers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'recipe_id',
            sa.Integer(),
            sa.ForeignKey('recipes.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('target_section', sa.String(length=30), nullable=True),
        sa.Column(
            'target_step_id',
            sa.Integer(),
            sa.ForeignKey('recipe_steps.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_recipe_stickers_recipe_id', 'recipe_stickers', ['recipe_id'])


def downgrade() -> None:
    op.drop_index('ix_recipe_stickers_recipe_id', table_name='recipe_stickers')
    op.drop_table('recipe_stickers')
