"""Initial MySQL schema for the refactored multi-tenant API.

Revision ID: 0001_initial_mysql_schema
Revises:
Create Date: 2026-05-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0001_initial_mysql_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("plan", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "stocks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("exchange", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("market", sa.String(length=32), nullable=True),
        sa.Column("industry", sa.String(length=128), nullable=True),
        sa.Column("listing_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol"),
    )
    op.create_index("ix_stocks_exchange", "stocks", ["exchange"])
    op.create_index("ix_stocks_name", "stocks", ["name"])

    op.create_table(
        "stock_daily_bars",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(18, 4), nullable=True),
        sa.Column("high", sa.Numeric(18, 4), nullable=True),
        sa.Column("low", sa.Numeric(18, 4), nullable=True),
        sa.Column("close", sa.Numeric(18, 4), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(24, 4), nullable=True),
        sa.Column("turnover_rate", sa.Numeric(12, 4), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "trade_date", "source", name="uk_daily_symbol_date_source"),
    )
    op.create_index("ix_stock_daily_bars_symbol", "stock_daily_bars", ["symbol"])
    op.create_index("ix_stock_daily_bars_trade_date", "stock_daily_bars", ["trade_date"])

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uk_roles_tenant_code"),
    )
    op.create_index("ix_roles_tenant_id", "roles", ["tenant_id"])

    op.create_table(
        "role_permissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "permission_id", name="uk_role_permission"),
    )
    op.create_index("ix_role_permissions_permission_id", "role_permissions", ["permission_id"])
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])

    op.create_table(
        "user_tenants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "tenant_id", name="uk_user_tenant"),
    )
    op.create_index("ix_user_tenants_role_id", "user_tenants", ["role_id"])
    op.create_index("ix_user_tenants_tenant_id", "user_tenants", ["tenant_id"])
    op.create_index("ix_user_tenants_user_id", "user_tenants", ["user_id"])

    op.create_table(
        "strategies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uk_strategies_tenant_code"),
    )
    op.create_index("ix_strategies_tenant_id", "strategies", ["tenant_id"])

    op.create_table(
        "scan_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("strategy_id", sa.Integer(), nullable=False),
        sa.Column("task_no", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("params_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_no"),
    )
    op.create_index("ix_scan_tasks_status", "scan_tasks", ["status"])
    op.create_index("ix_scan_tasks_strategy_id", "scan_tasks", ["strategy_id"])
    op.create_index("ix_scan_tasks_tenant_id", "scan_tasks", ["tenant_id"])

    op.create_table(
        "scan_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_task_id", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("stock_name", sa.String(length=128), nullable=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("score", sa.Numeric(12, 4), nullable=True),
        sa.Column("signals_json", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["scan_task_id"], ["scan_tasks.id"]),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scan_results_scan_task_id", "scan_results", ["scan_task_id"])
    op.create_index("ix_scan_results_strategy_id", "scan_results", ["strategy_id"])
    op.create_index("ix_scan_results_symbol", "scan_results", ["symbol"])
    op.create_index("ix_scan_results_tenant_id", "scan_results", ["tenant_id"])
    op.create_index("ix_scan_results_trade_date", "scan_results", ["trade_date"])

    op.create_table(
        "picks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("stock_name", sa.String(length=128), nullable=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("strategy_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("score", sa.Numeric(12, 4), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_picks_strategy_id", "picks", ["strategy_id"])
    op.create_index("ix_picks_symbol", "picks", ["symbol"])
    op.create_index("ix_picks_tenant_id", "picks", ["tenant_id"])
    op.create_index("ix_picks_trade_date", "picks", ["trade_date"])


def downgrade() -> None:
    op.drop_index("ix_picks_trade_date", table_name="picks")
    op.drop_index("ix_picks_tenant_id", table_name="picks")
    op.drop_index("ix_picks_symbol", table_name="picks")
    op.drop_index("ix_picks_strategy_id", table_name="picks")
    op.drop_table("picks")

    op.drop_index("ix_scan_results_trade_date", table_name="scan_results")
    op.drop_index("ix_scan_results_tenant_id", table_name="scan_results")
    op.drop_index("ix_scan_results_symbol", table_name="scan_results")
    op.drop_index("ix_scan_results_strategy_id", table_name="scan_results")
    op.drop_index("ix_scan_results_scan_task_id", table_name="scan_results")
    op.drop_table("scan_results")

    op.drop_index("ix_scan_tasks_tenant_id", table_name="scan_tasks")
    op.drop_index("ix_scan_tasks_strategy_id", table_name="scan_tasks")
    op.drop_index("ix_scan_tasks_status", table_name="scan_tasks")
    op.drop_table("scan_tasks")

    op.drop_index("ix_strategies_tenant_id", table_name="strategies")
    op.drop_table("strategies")

    op.drop_index("ix_user_tenants_user_id", table_name="user_tenants")
    op.drop_index("ix_user_tenants_tenant_id", table_name="user_tenants")
    op.drop_index("ix_user_tenants_role_id", table_name="user_tenants")
    op.drop_table("user_tenants")

    op.drop_index("ix_role_permissions_role_id", table_name="role_permissions")
    op.drop_index("ix_role_permissions_permission_id", table_name="role_permissions")
    op.drop_table("role_permissions")

    op.drop_index("ix_roles_tenant_id", table_name="roles")
    op.drop_table("roles")

    op.drop_index("ix_stock_daily_bars_trade_date", table_name="stock_daily_bars")
    op.drop_index("ix_stock_daily_bars_symbol", table_name="stock_daily_bars")
    op.drop_table("stock_daily_bars")

    op.drop_index("ix_stocks_name", table_name="stocks")
    op.drop_index("ix_stocks_exchange", table_name="stocks")
    op.drop_table("stocks")

    op.drop_table("permissions")
    op.drop_table("users")
    op.drop_table("tenants")
