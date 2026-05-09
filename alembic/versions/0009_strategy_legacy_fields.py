"""Add MySQL strategy legacy management fields.

Revision ID: 0009_strategy_legacy_fields
Revises: 0008_strategy_pool_backtests
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0009_strategy_legacy_fields"
down_revision = "0008_strategy_pool_backtests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "strategies",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "strategies",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_strategies_is_active", "strategies", ["is_active"])
    op.create_index("ix_strategies_sort_order", "strategies", ["sort_order"])
    op.execute("UPDATE strategies SET is_active = enabled")


def downgrade() -> None:
    op.drop_index("ix_strategies_sort_order", table_name="strategies")
    op.drop_index("ix_strategies_is_active", table_name="strategies")
    op.drop_column("strategies", "sort_order")
    op.drop_column("strategies", "is_active")
