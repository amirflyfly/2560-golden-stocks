"""Add 9:20-9:25 auction snapshots.

Revision ID: 0019_auction_snapshots
Revises: 0018_limit_up_return_rules
Create Date: 2026-05-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0019_auction_snapshots"
down_revision = "0018_limit_up_return_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_auction_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("auction_time", sa.DateTime(), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False, server_default="call_auction_0920_0925"),
        sa.Column("prev_close", sa.Numeric(18, 4), nullable=True),
        sa.Column("indicative_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("matched_volume", sa.Integer(), nullable=True),
        sa.Column("matched_amount", sa.Numeric(24, 4), nullable=True),
        sa.Column("unmatched_buy_volume", sa.Integer(), nullable=True),
        sa.Column("unmatched_sell_volume", sa.Integer(), nullable=True),
        sa.Column("bid_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("bid_volume", sa.Integer(), nullable=True),
        sa.Column("ask_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("ask_volume", sa.Integer(), nullable=True),
        sa.Column("order_book", sa.JSON(), nullable=True),
        sa.Column("withdrawal_buy_volume", sa.Integer(), nullable=True),
        sa.Column("withdrawal_sell_volume", sa.Integer(), nullable=True),
        sa.Column("withdrawal_buy_amount", sa.Numeric(24, 4), nullable=True),
        sa.Column("withdrawal_sell_amount", sa.Numeric(24, 4), nullable=True),
        sa.Column("seal_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("seal_volume", sa.Integer(), nullable=True),
        sa.Column("seal_amount", sa.Numeric(24, 4), nullable=True),
        sa.Column("seal_side", sa.String(length=8), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("symbol", "trade_date", "auction_time", "source", name="uk_auction_symbol_date_time_source"),
    )
    op.create_index("ix_stock_auction_snapshots_symbol", "stock_auction_snapshots", ["symbol"])
    op.create_index("ix_stock_auction_snapshots_trade_date", "stock_auction_snapshots", ["trade_date"])
    op.create_index("ix_stock_auction_snapshots_auction_time", "stock_auction_snapshots", ["auction_time"])
    op.create_index("ix_stock_auction_snapshots_phase", "stock_auction_snapshots", ["phase"])
    op.create_index("ix_stock_auction_snapshots_source", "stock_auction_snapshots", ["source"])


def downgrade() -> None:
    op.drop_index("ix_stock_auction_snapshots_source", table_name="stock_auction_snapshots")
    op.drop_index("ix_stock_auction_snapshots_phase", table_name="stock_auction_snapshots")
    op.drop_index("ix_stock_auction_snapshots_auction_time", table_name="stock_auction_snapshots")
    op.drop_index("ix_stock_auction_snapshots_trade_date", table_name="stock_auction_snapshots")
    op.drop_index("ix_stock_auction_snapshots_symbol", table_name="stock_auction_snapshots")
    op.drop_table("stock_auction_snapshots")
