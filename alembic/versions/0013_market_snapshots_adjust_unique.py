"""Add market snapshots and adjust-aware daily bar uniqueness.

Revision ID: 0013_market_snapshots_adjust_unique
Revises: 0012_strategy_lifecycle_data_center
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0013_market_snapshots_adjust_unique"
down_revision = "0012_strategy_lifecycle_data_center"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uk_daily_symbol_date_source", "stock_daily_bars", type_="unique")
    op.create_unique_constraint(
        "uk_daily_symbol_date_source_adjust",
        "stock_daily_bars",
        ["symbol", "trade_date", "source", "adjust"],
    )

    op.create_table(
        "stock_price_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("trade_time", sa.DateTime(), nullable=True),
        sa.Column("last_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("open", sa.Numeric(18, 4), nullable=True),
        sa.Column("high", sa.Numeric(18, 4), nullable=True),
        sa.Column("low", sa.Numeric(18, 4), nullable=True),
        sa.Column("prev_close", sa.Numeric(18, 4), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(24, 4), nullable=True),
        sa.Column("bid_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("ask_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", name="uk_stock_price_snapshots_symbol"),
    )
    op.create_index("ix_stock_price_snapshots_symbol", "stock_price_snapshots", ["symbol"])
    op.create_index("ix_stock_price_snapshots_source", "stock_price_snapshots", ["source"])
    op.create_index("ix_stock_price_snapshots_trade_time", "stock_price_snapshots", ["trade_time"])


def downgrade() -> None:
    op.drop_index("ix_stock_price_snapshots_trade_time", table_name="stock_price_snapshots")
    op.drop_index("ix_stock_price_snapshots_source", table_name="stock_price_snapshots")
    op.drop_index("ix_stock_price_snapshots_symbol", table_name="stock_price_snapshots")
    op.drop_table("stock_price_snapshots")

    op.drop_constraint("uk_daily_symbol_date_source_adjust", "stock_daily_bars", type_="unique")
    op.create_unique_constraint(
        "uk_daily_symbol_date_source",
        "stock_daily_bars",
        ["symbol", "trade_date", "source"],
    )
