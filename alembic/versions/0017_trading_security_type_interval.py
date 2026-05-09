"""Track paper trading security type and bar interval.

Revision ID: 0017_trading_security_type_interval
Revises: 0016_sync_state_intervals
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0017_trading_security_type_interval"
down_revision = "0016_sync_state_intervals"
branch_labels = None
depends_on = None


TABLES = ("trade_signals", "paper_positions", "paper_orders", "paper_fills")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("security_type", sa.String(length=32), nullable=False, server_default="stock"))
        op.add_column(table, sa.Column("bar_interval", sa.String(length=16), nullable=False, server_default="1d"))
        op.create_index(f"ix_{table}_security_type", table, ["security_type"])
        op.create_index(f"ix_{table}_bar_interval", table, ["bar_interval"])


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_index(f"ix_{table}_bar_interval", table_name=table)
        op.drop_index(f"ix_{table}_security_type", table_name=table)
        op.drop_column(table, "bar_interval")
        op.drop_column(table, "security_type")
