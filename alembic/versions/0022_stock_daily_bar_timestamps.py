"""Add timestamps to stock daily bars.

Revision ID: 0022_stock_daily_bar_timestamps
Revises: 0021_external_push_deliveries
Create Date: 2026-05-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "0022_stock_daily_bar_timestamps"
down_revision = "0021_external_push_deliveries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_columns = {column["name"] for column in inspect(op.get_bind()).get_columns("stock_daily_bars")}
    if "created_at" not in existing_columns:
        op.add_column(
            "stock_daily_bars",
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    if "updated_at" not in existing_columns:
        op.add_column(
            "stock_daily_bars",
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_column("stock_daily_bars", "updated_at")
    op.drop_column("stock_daily_bars", "created_at")
