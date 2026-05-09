"""Add MySQL legacy strategy pool and backtest tables.

Revision ID: 0008_strategy_pool_backtests
Revises: 0007_operation_logs
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008_strategy_pool_backtests"
down_revision = "0007_operation_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_pools",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("strategy_code", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("add_date", sa.String(length=16), nullable=False),
        sa.Column("add_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("strategy_code", "code", name="uk_strategy_pools_strategy_code"),
    )
    op.create_index("ix_strategy_pools_strategy_code", "strategy_pools", ["strategy_code"])
    op.create_index("ix_strategy_pools_status", "strategy_pools", ["status"])

    op.create_table(
        "backtest_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("strategy_code", sa.String(length=64), nullable=False),
        sa.Column("start_date", sa.String(length=16), nullable=False),
        sa.Column("end_date", sa.String(length=16), nullable=False),
        sa.Column("total_trades", sa.Integer(), nullable=True),
        sa.Column("win_rate", sa.Numeric(12, 6), nullable=True),
        sa.Column("avg_return", sa.Numeric(12, 6), nullable=True),
        sa.Column("max_return", sa.Numeric(12, 6), nullable=True),
        sa.Column("max_drawdown", sa.Numeric(12, 6), nullable=True),
        sa.Column("sharpe_ratio", sa.Numeric(12, 6), nullable=True),
        sa.Column("total_return", sa.Numeric(12, 6), nullable=True),
        sa.Column("backtest_date", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backtest_results_strategy_code", "backtest_results", ["strategy_code"])


def downgrade() -> None:
    op.drop_index("ix_backtest_results_strategy_code", table_name="backtest_results")
    op.drop_table("backtest_results")
    op.drop_index("ix_strategy_pools_status", table_name="strategy_pools")
    op.drop_index("ix_strategy_pools_strategy_code", table_name="strategy_pools")
    op.drop_table("strategy_pools")
