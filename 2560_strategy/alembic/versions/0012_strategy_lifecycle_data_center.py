"""Add strategy lifecycle and market data adjust fields.

Revision ID: 0012_strategy_lifecycle_data_center
Revises: 0011_user_engagement_fields
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0012_strategy_lifecycle_data_center"
down_revision = "0011_user_engagement_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("strategies", sa.Column("code_body", sa.Text(), nullable=True))
    op.add_column("strategies", sa.Column("source_type", sa.String(length=32), nullable=False, server_default="builtin"))
    op.add_column("strategies", sa.Column("lifecycle_status", sa.String(length=32), nullable=False, server_default="deployed"))
    op.add_column("strategies", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("strategies", sa.Column("deployed_at", sa.DateTime(), nullable=True))
    op.add_column("strategies", sa.Column("last_test_status", sa.String(length=32), nullable=True))
    op.add_column("strategies", sa.Column("last_test_message", sa.Text(), nullable=True))
    op.add_column("strategies", sa.Column("last_test_at", sa.DateTime(), nullable=True))

    op.add_column("stock_daily_bars", sa.Column("adjust", sa.String(length=16), nullable=False, server_default="qfq"))
    op.create_index("ix_stock_daily_bars_adjust", "stock_daily_bars", ["adjust"])


def downgrade() -> None:
    op.drop_index("ix_stock_daily_bars_adjust", table_name="stock_daily_bars")
    op.drop_column("stock_daily_bars", "adjust")
    op.drop_column("strategies", "last_test_at")
    op.drop_column("strategies", "last_test_message")
    op.drop_column("strategies", "last_test_status")
    op.drop_column("strategies", "deployed_at")
    op.drop_column("strategies", "version")
    op.drop_column("strategies", "lifecycle_status")
    op.drop_column("strategies", "source_type")
    op.drop_column("strategies", "code_body")
