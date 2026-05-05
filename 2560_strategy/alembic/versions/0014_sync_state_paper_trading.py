"""Add market sync state and paper trading ledger.

Revision ID: 0014_sync_state_paper_trading
Revises: 0013_market_snapshots_adjust_unique
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0014_sync_state_paper_trading"
down_revision = "0013_market_snapshots_adjust_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_sync_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="auto"),
        sa.Column("adjust", sa.String(length=16), nullable=False, server_default="qfq"),
        sa.Column("coverage_start_date", sa.Date(), nullable=True),
        sa.Column("coverage_end_date", sa.Date(), nullable=True),
        sa.Column("last_success_trade_date", sa.Date(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "symbol", "source", "adjust", name="uk_market_sync_state_symbol_source_adjust"),
    )
    op.create_index("ix_market_sync_states_tenant_id", "market_sync_states", ["tenant_id"])
    op.create_index("ix_market_sync_states_symbol", "market_sync_states", ["symbol"])
    op.create_index("ix_market_sync_states_source", "market_sync_states", ["source"])
    op.create_index("ix_market_sync_states_adjust", "market_sync_states", ["adjust"])
    op.create_index("ix_market_sync_states_status", "market_sync_states", ["status"])
    op.create_index("ix_market_sync_states_coverage_end_date", "market_sync_states", ["coverage_end_date"])
    op.create_index("ix_market_sync_states_last_success_trade_date", "market_sync_states", ["last_success_trade_date"])

    op.create_table(
        "market_sync_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("run_no", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="incremental"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="auto"),
        sa.Column("adjust", sa.String(length=16), nullable=False, server_default="qfq"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("requested_symbols", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("synced_symbols", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_symbols", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("persisted_bars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_no", name="uk_market_sync_runs_run_no"),
    )
    op.create_index("ix_market_sync_runs_tenant_id", "market_sync_runs", ["tenant_id"])
    op.create_index("ix_market_sync_runs_run_no", "market_sync_runs", ["run_no"])
    op.create_index("ix_market_sync_runs_mode", "market_sync_runs", ["mode"])
    op.create_index("ix_market_sync_runs_source", "market_sync_runs", ["source"])
    op.create_index("ix_market_sync_runs_adjust", "market_sync_runs", ["adjust"])
    op.create_index("ix_market_sync_runs_status", "market_sync_runs", ["status"])

    op.create_table(
        "market_sync_run_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("bars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("persisted_bars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="auto"),
        sa.Column("adjust", sa.String(length=16), nullable=False, server_default="qfq"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_sync_run_items_tenant_id", "market_sync_run_items", ["tenant_id"])
    op.create_index("ix_market_sync_run_items_run_id", "market_sync_run_items", ["run_id"])
    op.create_index("ix_market_sync_run_items_symbol", "market_sync_run_items", ["symbol"])
    op.create_index("ix_market_sync_run_items_status", "market_sync_run_items", ["status"])
    op.create_index("ix_market_sync_run_items_source", "market_sync_run_items", ["source"])
    op.create_index("ix_market_sync_run_items_adjust", "market_sync_run_items", ["adjust"])

    op.create_table(
        "trade_signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("strategy_id", sa.Integer(), nullable=True),
        sa.Column("strategy_code", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("signal_date", sa.Date(), nullable=True),
        sa.Column("signal_type", sa.String(length=16), nullable=False, server_default="BUY"),
        sa.Column("score", sa.Numeric(12, 4), nullable=True),
        sa.Column("price_ref", sa.Numeric(18, 4), nullable=True),
        sa.Column("data_quality", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("source_hash", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "source_hash", name="uk_trade_signals_source_hash"),
    )
    op.create_index("ix_trade_signals_tenant_id", "trade_signals", ["tenant_id"])
    op.create_index("ix_trade_signals_account_id", "trade_signals", ["account_id"])
    op.create_index("ix_trade_signals_strategy_id", "trade_signals", ["strategy_id"])
    op.create_index("ix_trade_signals_strategy_code", "trade_signals", ["strategy_code"])
    op.create_index("ix_trade_signals_symbol", "trade_signals", ["symbol"])
    op.create_index("ix_trade_signals_signal_date", "trade_signals", ["signal_date"])
    op.create_index("ix_trade_signals_signal_type", "trade_signals", ["signal_type"])
    op.create_index("ix_trade_signals_status", "trade_signals", ["status"])

    op.create_table(
        "paper_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="paper"),
        sa.Column("broker_type", sa.String(length=32), nullable=False, server_default="paper"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("currency", sa.String(length=16), nullable=False, server_default="CNY"),
        sa.Column("initial_cash", sa.Numeric(24, 4), nullable=False, server_default="1000000"),
        sa.Column("cash", sa.Numeric(24, 4), nullable=False, server_default="1000000"),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uk_paper_accounts_tenant_name"),
    )
    op.create_index("ix_paper_accounts_tenant_id", "paper_accounts", ["tenant_id"])
    op.create_index("ix_paper_accounts_mode", "paper_accounts", ["mode"])
    op.create_index("ix_paper_accounts_status", "paper_accounts", ["status"])

    op.create_table(
        "paper_positions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("market_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("market_value", sa.Numeric(24, 4), nullable=False, server_default="0"),
        sa.Column("realized_pnl", sa.Numeric(24, 4), nullable=False, server_default="0"),
        sa.Column("unrealized_pnl", sa.Numeric(24, 4), nullable=False, server_default="0"),
        sa.Column("opened_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "account_id", "symbol", name="uk_paper_positions_account_symbol"),
    )
    op.create_index("ix_paper_positions_tenant_id", "paper_positions", ["tenant_id"])
    op.create_index("ix_paper_positions_account_id", "paper_positions", ["account_id"])
    op.create_index("ix_paper_positions_symbol", "paper_positions", ["symbol"])

    op.create_table(
        "paper_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.Integer(), nullable=True),
        sa.Column("strategy_code", sa.String(length=64), nullable=True),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("order_type", sa.String(length=32), nullable=False, server_default="market"),
        sa.Column("requested_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("limit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="filled"),
        sa.Column("filled_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_fill_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("source_signal_hash", sa.String(length=128), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uk_paper_orders_idempotency"),
    )
    op.create_index("ix_paper_orders_tenant_id", "paper_orders", ["tenant_id"])
    op.create_index("ix_paper_orders_account_id", "paper_orders", ["account_id"])
    op.create_index("ix_paper_orders_strategy_id", "paper_orders", ["strategy_id"])
    op.create_index("ix_paper_orders_strategy_code", "paper_orders", ["strategy_code"])
    op.create_index("ix_paper_orders_symbol", "paper_orders", ["symbol"])
    op.create_index("ix_paper_orders_side", "paper_orders", ["side"])
    op.create_index("ix_paper_orders_status", "paper_orders", ["status"])

    op.create_table(
        "paper_fills",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(18, 4), nullable=False),
        sa.Column("amount", sa.Numeric(24, 4), nullable=False),
        sa.Column("fee", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("filled_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_fills_tenant_id", "paper_fills", ["tenant_id"])
    op.create_index("ix_paper_fills_account_id", "paper_fills", ["account_id"])
    op.create_index("ix_paper_fills_order_id", "paper_fills", ["order_id"])
    op.create_index("ix_paper_fills_symbol", "paper_fills", ["symbol"])
    op.create_index("ix_paper_fills_side", "paper_fills", ["side"])
    op.create_index("ix_paper_fills_filled_at", "paper_fills", ["filled_at"])


def downgrade() -> None:
    for name, table in [
        ("ix_paper_fills_filled_at", "paper_fills"),
        ("ix_paper_fills_side", "paper_fills"),
        ("ix_paper_fills_symbol", "paper_fills"),
        ("ix_paper_fills_order_id", "paper_fills"),
        ("ix_paper_fills_account_id", "paper_fills"),
        ("ix_paper_fills_tenant_id", "paper_fills"),
    ]:
        op.drop_index(name, table_name=table)
    op.drop_table("paper_fills")

    for name in [
        "ix_paper_orders_status",
        "ix_paper_orders_side",
        "ix_paper_orders_symbol",
        "ix_paper_orders_strategy_code",
        "ix_paper_orders_strategy_id",
        "ix_paper_orders_account_id",
        "ix_paper_orders_tenant_id",
    ]:
        op.drop_index(name, table_name="paper_orders")
    op.drop_table("paper_orders")

    for name in ["ix_paper_positions_symbol", "ix_paper_positions_account_id", "ix_paper_positions_tenant_id"]:
        op.drop_index(name, table_name="paper_positions")
    op.drop_table("paper_positions")

    for name in ["ix_paper_accounts_status", "ix_paper_accounts_mode", "ix_paper_accounts_tenant_id"]:
        op.drop_index(name, table_name="paper_accounts")
    op.drop_table("paper_accounts")

    for name in [
        "ix_trade_signals_status",
        "ix_trade_signals_signal_type",
        "ix_trade_signals_signal_date",
        "ix_trade_signals_symbol",
        "ix_trade_signals_strategy_code",
        "ix_trade_signals_strategy_id",
        "ix_trade_signals_account_id",
        "ix_trade_signals_tenant_id",
    ]:
        op.drop_index(name, table_name="trade_signals")
    op.drop_table("trade_signals")

    for name in [
        "ix_market_sync_run_items_adjust",
        "ix_market_sync_run_items_source",
        "ix_market_sync_run_items_status",
        "ix_market_sync_run_items_symbol",
        "ix_market_sync_run_items_run_id",
        "ix_market_sync_run_items_tenant_id",
    ]:
        op.drop_index(name, table_name="market_sync_run_items")
    op.drop_table("market_sync_run_items")

    for name in [
        "ix_market_sync_runs_status",
        "ix_market_sync_runs_adjust",
        "ix_market_sync_runs_source",
        "ix_market_sync_runs_mode",
        "ix_market_sync_runs_run_no",
        "ix_market_sync_runs_tenant_id",
    ]:
        op.drop_index(name, table_name="market_sync_runs")
    op.drop_table("market_sync_runs")

    for name in [
        "ix_market_sync_states_last_success_trade_date",
        "ix_market_sync_states_coverage_end_date",
        "ix_market_sync_states_status",
        "ix_market_sync_states_adjust",
        "ix_market_sync_states_source",
        "ix_market_sync_states_symbol",
        "ix_market_sync_states_tenant_id",
    ]:
        op.drop_index(name, table_name="market_sync_states")
    op.drop_table("market_sync_states")
