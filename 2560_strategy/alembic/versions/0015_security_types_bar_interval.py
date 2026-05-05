"""Add security types and bar intervals.

Revision ID: 0015_security_types_bar_interval
Revises: 0014_sync_state_paper_trading
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0015_security_types_bar_interval"
down_revision = "0014_sync_state_paper_trading"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stocks", sa.Column("security_type", sa.String(length=32), nullable=False, server_default="stock"))
    op.create_index("ix_stocks_security_type", "stocks", ["security_type"])

    op.add_column("stock_daily_bars", sa.Column("trade_time", sa.DateTime(), nullable=True))
    op.add_column("stock_daily_bars", sa.Column("interval", sa.String(length=16), nullable=False, server_default="1d"))
    op.execute("UPDATE stock_daily_bars SET trade_time = CAST(trade_date AS DATETIME) WHERE trade_time IS NULL")
    op.alter_column("stock_daily_bars", "trade_time", nullable=False)
    op.create_index("ix_stock_daily_bars_trade_time", "stock_daily_bars", ["trade_time"])
    op.create_index("ix_stock_daily_bars_interval", "stock_daily_bars", ["interval"])

    op.drop_constraint("uk_daily_symbol_date_source_adjust", "stock_daily_bars", type_="unique")
    op.create_unique_constraint(
        "uk_bar_symbol_time_interval_source_adjust",
        "stock_daily_bars",
        ["symbol", "trade_date", "trade_time", "interval", "source", "adjust"],
    )


def downgrade() -> None:
    op.drop_constraint("uk_bar_symbol_time_interval_source_adjust", "stock_daily_bars", type_="unique")
    op.create_unique_constraint(
        "uk_daily_symbol_date_source_adjust",
        "stock_daily_bars",
        ["symbol", "trade_date", "source", "adjust"],
    )
    op.drop_index("ix_stock_daily_bars_interval", table_name="stock_daily_bars")
    op.drop_index("ix_stock_daily_bars_trade_time", table_name="stock_daily_bars")
    op.drop_column("stock_daily_bars", "interval")
    op.drop_column("stock_daily_bars", "trade_time")

    op.drop_index("ix_stocks_security_type", table_name="stocks")
    op.drop_column("stocks", "security_type")
