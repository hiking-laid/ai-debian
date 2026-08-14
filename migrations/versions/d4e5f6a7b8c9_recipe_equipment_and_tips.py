"""recipe: add equipment and tips tables

Adds two relational tables (recipe_equipment, recipe_tips) mirroring recipe_steps,
so a recipe's structure is Ingredients / Equipment / Method / Tips.

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-08-11 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: str | Sequence[str] | None = 'c1d2e3f4a5b6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_list_table(name: str) -> None:
    op.create_table(
        name,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'recipe_id',
            sa.Integer(),
            sa.ForeignKey('recipes.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('text', sa.Text(), nullable=False),
    )
    op.create_index(f'ix_{name}_recipe_id', name, ['recipe_id'])


def upgrade() -> None:
    _create_list_table('recipe_equipment')
    _create_list_table('recipe_tips')


def downgrade() -> None:
    op.drop_index('ix_recipe_tips_recipe_id', table_name='recipe_tips')
    op.drop_table('recipe_tips')
    op.drop_index('ix_recipe_equipment_recipe_id', table_name='recipe_equipment')
    op.drop_table('recipe_equipment')
