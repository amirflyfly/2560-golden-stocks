"""Track market sync state by bar interval.

Revision ID: 0016_sync_state_intervals
Revises: 0015_security_types_bar_interval
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0016_sync_state_intervals"
down_revision = "0015_security_types_bar_interval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_sync_states", sa.Column("interval", sa.String(length=16), nullable=False, server_default="1d"))
    op.create_index("ix_market_sync_states_interval", "market_sync_states", ["interval"])
    op.drop_constraint("uk_market_sync_state_symbol_source_adjust", "market_sync_states", type_="unique")
    op.create_unique_constraint(
        "uk_market_sync_state_symbol_source_adjust_interval",
        "market_sync_states",
        ["tenant_id", "symbol", "source", "adjust", "interval"],
    )

    op.add_column("market_sync_runs", sa.Column("interval", sa.String(length=16), nullable=False, server_default="1d"))
    op.create_index("ix_market_sync_runs_interval", "market_sync_runs", ["interval"])

    op.add_column("market_sync_run_items", sa.Column("interval", sa.String(length=16), nullable=False, server_default="1d"))
    op.create_index("ix_market_sync_run_items_interval", "market_sync_run_items", ["interval"])


def downgrade() -> None:
    op.drop_index("ix_market_sync_run_items_interval", table_name="market_sync_run_items")
    op.drop_column("market_sync_run_items", "interval")

    op.drop_index("ix_market_sync_runs_interval", table_name="market_sync_runs")
    op.drop_column("market_sync_runs", "interval")

    op.drop_constraint("uk_market_sync_state_symbol_source_adjust_interval", "market_sync_states", type_="unique")
    op.create_unique_constraint(
        "uk_market_sync_state_symbol_source_adjust",
        "market_sync_states",
        ["tenant_id", "symbol", "source", "adjust"],
    )
    op.drop_index("ix_market_sync_states_interval", table_name="market_sync_states")
    op.drop_column("market_sync_states", "interval")
