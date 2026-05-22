"""Add signal review links.

Revision ID: 0023_signal_review_links
Revises: 0022_stock_daily_bar_timestamps
Create Date: 2026-05-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0023_signal_review_links"
down_revision = "0022_stock_daily_bar_timestamps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signal_review_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("source_signal_hash", sa.String(length=128), nullable=False),
        sa.Column("trade_signal_id", sa.Integer(), nullable=True),
        sa.Column("pick_id", sa.Integer(), nullable=True),
        sa.Column("buy_order_id", sa.Integer(), nullable=True),
        sa.Column("sell_order_id", sa.Integer(), nullable=True),
        sa.Column("buy_fill_id", sa.Integer(), nullable=True),
        sa.Column("sell_fill_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("opened_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("realized_return_pct", sa.Numeric(12, 4), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "source_signal_hash", name="uk_signal_review_links_source_hash"),
    )
    op.create_index("ix_signal_review_links_tenant_id", "signal_review_links", ["tenant_id"])
    op.create_index("ix_signal_review_links_trade_signal_id", "signal_review_links", ["trade_signal_id"])
    op.create_index("ix_signal_review_links_pick_id", "signal_review_links", ["pick_id"])
    op.create_index("ix_signal_review_links_buy_order_id", "signal_review_links", ["buy_order_id"])
    op.create_index("ix_signal_review_links_sell_order_id", "signal_review_links", ["sell_order_id"])
    op.create_index("ix_signal_review_links_buy_fill_id", "signal_review_links", ["buy_fill_id"])
    op.create_index("ix_signal_review_links_sell_fill_id", "signal_review_links", ["sell_fill_id"])
    op.create_index("ix_signal_review_links_status", "signal_review_links", ["status"])


def downgrade() -> None:
    for name in [
        "ix_signal_review_links_status",
        "ix_signal_review_links_sell_fill_id",
        "ix_signal_review_links_buy_fill_id",
        "ix_signal_review_links_sell_order_id",
        "ix_signal_review_links_buy_order_id",
        "ix_signal_review_links_pick_id",
        "ix_signal_review_links_trade_signal_id",
        "ix_signal_review_links_tenant_id",
    ]:
        op.drop_index(name, table_name="signal_review_links")
    op.drop_table("signal_review_links")
