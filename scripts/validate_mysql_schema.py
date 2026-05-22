"""Validate the refactored MySQL schema after Alembic migration.

Usage:
    APP_ENV=production DATABASE_URL=mysql+pymysql://... python scripts/validate_mysql_schema.py

The script is read-only. It checks that expected tables, indexes and core seed
preconditions exist, and exits non-zero on validation failure.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import inspect, text

from backend.db.session import get_engine


EXPECTED_TABLES = {
    "alembic_version",
    "tenants",
    "users",
    "roles",
    "permissions",
    "role_permissions",
    "user_tenants",
    "sessions",
    "audit_logs",
    "operation_logs",
    "saved_filters",
    "ui_settings",
    "stocks",
    "limit_rule_calendar",
    "stock_daily_bars",
    "stock_auction_snapshots",
    "live_broker_requests",
    "live_broker_fills",
    "live_broker_reconciliations",
    "external_push_deliveries",
    "strategies",
    "strategy_pools",
    "backtest_results",
    "research_reports",
    "scan_tasks",
    "scan_results",
    "picks",
    "signal_review_links",
}

EXPECTED_INDEXES = {
    "roles": {"ix_roles_tenant_id"},
    "user_tenants": {"ix_user_tenants_user_id", "ix_user_tenants_tenant_id", "ix_user_tenants_role_id"},
    "sessions": {"ix_sessions_user_id", "ix_sessions_expires_at"},
    "audit_logs": {"ix_audit_logs_tenant_id", "ix_audit_logs_action", "ix_audit_logs_result"},
    "operation_logs": {"ix_operation_logs_created_at"},
    "saved_filters": {"ix_saved_filters_created_at"},
    "strategies": {"ix_strategies_tenant_id", "ix_strategies_is_active", "ix_strategies_sort_order"},
    "strategy_pools": {"ix_strategy_pools_strategy_code", "ix_strategy_pools_status"},
    "backtest_results": {"ix_backtest_results_strategy_code"},
    "research_reports": {
        "ix_research_reports_pick_id",
        "ix_research_reports_analysis_date",
        "ix_research_reports_code_date",
    },
    "scan_tasks": {"ix_scan_tasks_tenant_id", "ix_scan_tasks_status", "ix_scan_tasks_strategy_id"},
    "scan_results": {
        "ix_scan_results_tenant_id",
        "ix_scan_results_scan_task_id",
        "ix_scan_results_strategy_id",
        "ix_scan_results_symbol",
        "ix_scan_results_trade_date",
    },
    "picks": {"ix_picks_tenant_id", "ix_picks_symbol", "ix_picks_trade_date", "ix_picks_strategy_id"},
    "signal_review_links": {
        "ix_signal_review_links_tenant_id",
        "ix_signal_review_links_trade_signal_id",
        "ix_signal_review_links_pick_id",
        "ix_signal_review_links_buy_order_id",
        "ix_signal_review_links_sell_order_id",
        "ix_signal_review_links_buy_fill_id",
        "ix_signal_review_links_sell_fill_id",
        "ix_signal_review_links_status",
    },
    "stocks": {"ix_stocks_exchange", "ix_stocks_name", "ix_stocks_security_type", "ix_stocks_board_type"},
    "stock_daily_bars": {"ix_stock_daily_bars_symbol", "ix_stock_daily_bars_trade_date"},
    "stock_auction_snapshots": {
        "ix_stock_auction_snapshots_symbol",
        "ix_stock_auction_snapshots_trade_date",
        "ix_stock_auction_snapshots_auction_time",
        "ix_stock_auction_snapshots_phase",
        "ix_stock_auction_snapshots_source",
    },
    "limit_rule_calendar": {"ix_limit_rule_calendar_profile", "ix_limit_rule_calendar_effective_from"},
    "live_broker_requests": {
        "ix_live_broker_requests_tenant_id",
        "ix_live_broker_requests_action",
        "ix_live_broker_requests_status",
        "ix_live_broker_requests_created_at",
        "ix_live_broker_requests_rate_window",
    },
    "live_broker_fills": {
        "ix_live_broker_fills_tenant_id",
        "ix_live_broker_fills_account_id",
        "ix_live_broker_fills_symbol",
        "ix_live_broker_fills_filled_at",
        "ix_live_broker_fills_account_created",
    },
    "live_broker_reconciliations": {
        "ix_live_broker_reconciliations_tenant_id",
        "ix_live_broker_reconciliations_status",
    },
    "external_push_deliveries": {
        "ix_external_push_deliveries_tenant_id",
        "ix_external_push_deliveries_status",
        "ix_external_push_deliveries_task_id",
        "ix_external_push_deliveries_tenant_created",
    },
}

EXPECTED_COLUMNS = {
    "users": {
        "id",
        "username",
        "email",
        "password_hash",
        "status",
        "last_login_at",
        "points",
        "last_checkin",
        "created_at",
        "updated_at",
    },
    "saved_filters": {"id", "name", "query_string", "created_at"},
    "ui_settings": {"setting_key", "setting_value", "updated_at"},
    "operation_logs": {
        "id",
        "action",
        "target_ids",
        "detail",
        "user_id",
        "username",
        "ip",
        "user_agent",
        "created_at",
    },
    "strategy_pools": {
        "id",
        "strategy_code",
        "code",
        "name",
        "add_date",
        "add_price",
        "reason",
        "status",
        "created_at",
    },
    "backtest_results": {
        "id",
        "strategy_code",
        "start_date",
        "end_date",
        "total_trades",
        "win_rate",
        "avg_return",
        "max_return",
        "max_drawdown",
        "sharpe_ratio",
        "total_return",
        "backtest_date",
    },
    "research_reports": {
        "id",
        "pick_id",
        "code",
        "pick_date",
        "analysis_date",
        "technical_score",
        "momentum_score",
        "risk_score",
        "liquidity_score",
        "timing_score",
        "total_score",
        "research_summary",
        "action_suggestion",
        "risk_warning",
        "data_snapshot",
        "created_at",
        "updated_at",
    },
    "strategies": {
        "id",
        "tenant_id",
        "code",
        "name",
        "category",
        "description",
        "config_json",
        "enabled",
        "is_active",
        "sort_order",
        "created_by",
        "created_at",
        "updated_at",
        "deleted_at",
    },
    "stocks": {
        "id",
        "symbol",
        "exchange",
        "name",
        "market",
        "security_type",
        "industry",
        "listing_date",
        "status",
        "is_st",
        "board_type",
        "limit_rule_profile",
        "is_suspended",
        "is_delisting",
        "created_at",
        "updated_at",
    },
    "stock_daily_bars": {
        "id",
        "symbol",
        "trade_date",
        "trade_time",
        "interval",
        "adjust",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "turnover_rate",
        "source",
        "created_at",
        "updated_at",
    },
    "limit_rule_calendar": {
        "id",
        "exchange",
        "board_type",
        "security_type",
        "risk_warning",
        "effective_from",
        "effective_to",
        "limit_up_rate",
        "limit_down_rate",
        "no_limit_first_days",
        "status",
        "notes",
        "created_at",
        "updated_at",
    },
    "stock_auction_snapshots": {
        "id",
        "symbol",
        "trade_date",
        "auction_time",
        "phase",
        "prev_close",
        "indicative_price",
        "matched_volume",
        "matched_amount",
        "unmatched_buy_volume",
        "unmatched_sell_volume",
        "bid_price",
        "bid_volume",
        "ask_price",
        "ask_volume",
        "order_book",
        "withdrawal_buy_volume",
        "withdrawal_sell_volume",
        "withdrawal_buy_amount",
        "withdrawal_sell_amount",
        "seal_price",
        "seal_volume",
        "seal_amount",
        "seal_side",
        "source",
        "created_at",
        "updated_at",
    },
    "live_broker_requests": {
        "id",
        "tenant_id",
        "action",
        "adapter",
        "account_id",
        "idempotency_key",
        "request_hash",
        "status",
        "reason",
        "broker_order_id",
        "client_order_id",
        "payload_json",
        "response_json",
        "created_at",
        "updated_at",
    },
    "live_broker_fills": {
        "id",
        "tenant_id",
        "account_id",
        "broker_order_id",
        "client_order_id",
        "symbol",
        "side",
        "quantity",
        "price",
        "amount",
        "fee",
        "currency",
        "filled_at",
        "fill_key",
        "source",
        "payload_json",
        "created_at",
        "updated_at",
    },
    "live_broker_reconciliations": {
        "id",
        "tenant_id",
        "account_id",
        "idempotency_key",
        "status",
        "differences_count",
        "request_json",
        "result_json",
        "created_at",
        "updated_at",
    },
    "external_push_deliveries": {
        "id",
        "tenant_id",
        "user_id",
        "delivery_key",
        "status",
        "task_id",
        "retry_count",
        "last_error",
        "channel_id",
        "channel_type",
        "notification_summary",
        "notification_payload",
        "queued_at",
        "sent_at",
        "failed_at",
        "skipped_at",
        "created_at",
        "updated_at",
    },
    "picks": {
        "tenant_id",
        "symbol",
        "stock_name",
        "trade_date",
        "strategy_id",
        "source",
        "source_channel",
        "reason",
        "score",
        "status",
        "review_comment",
        "risk_level",
        "deal_status",
        "return_pct",
        "max_return_pct",
        "drawdown_pct",
        "holding_days",
        "watch_flag",
        "validation_result",
        "validation_note",
        "validated_at",
        "data_quality",
        "market_data_source",
        "fallback_used",
        "legacy_payload_json",
    },
    "signal_review_links": {
        "id",
        "tenant_id",
        "source_signal_hash",
        "trade_signal_id",
        "pick_id",
        "buy_order_id",
        "sell_order_id",
        "buy_fill_id",
        "sell_fill_id",
        "status",
        "opened_at",
        "closed_at",
        "realized_return_pct",
        "metadata_json",
        "created_at",
        "updated_at",
    }
}

EXPECTED_UNIQUE_CONSTRAINTS = {
    "picks": {"uk_picks_tenant_date_symbol_source"},
    "strategy_pools": {"uk_strategy_pools_strategy_code"},
    "research_reports": {"uk_research_reports_pick_analysis"},
    "limit_rule_calendar": {"uk_limit_rule_calendar_profile_start"},
    "stock_auction_snapshots": {"uk_auction_symbol_date_time_source"},
    "live_broker_requests": {"uk_live_broker_requests_idempotency"},
    "live_broker_fills": {"uk_live_broker_fills_key"},
    "live_broker_reconciliations": {"uk_live_broker_reconciliations_idempotency"},
    "external_push_deliveries": {"uk_external_push_deliveries_key"},
    "signal_review_links": {"uk_signal_review_links_source_hash"},
}

EXPECTED_ALEMBIC_REVISION = "0023_signal_review_links"
EXPECTED_TENANT_CODE = "default"
EXPECTED_STRATEGY_CODES = {"2560", "first_limit_up", "LIMIT_UP_RETURN", "CONVERTIBLE_BOND_LOW_PREMIUM"}


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def check_tables(inspector) -> CheckResult:
    tables = set(inspector.get_table_names())
    missing = sorted(EXPECTED_TABLES - tables)
    if missing:
        return CheckResult("tables", False, f"missing tables: {', '.join(missing)}")
    return CheckResult("tables", True, f"found {len(EXPECTED_TABLES)} expected tables")


def check_indexes(inspector) -> CheckResult:
    missing: list[str] = []
    for table, expected in EXPECTED_INDEXES.items():
        actual = {item["name"] for item in inspector.get_indexes(table)}
        for name in expected - actual:
            missing.append(f"{table}.{name}")
    if missing:
        return CheckResult("indexes", False, f"missing indexes: {', '.join(sorted(missing))}")
    return CheckResult("indexes", True, "expected indexes found")


def check_columns(inspector) -> CheckResult:
    missing: list[str] = []
    for table, expected in EXPECTED_COLUMNS.items():
        actual = {item["name"] for item in inspector.get_columns(table)}
        for name in expected - actual:
            missing.append(f"{table}.{name}")
    if missing:
        return CheckResult("columns", False, f"missing columns: {', '.join(sorted(missing))}")
    return CheckResult("columns", True, "expected columns found")


def check_unique_constraints(inspector) -> CheckResult:
    missing: list[str] = []
    for table, expected in EXPECTED_UNIQUE_CONSTRAINTS.items():
        actual = {item["name"] for item in inspector.get_unique_constraints(table)}
        for name in expected - actual:
            missing.append(f"{table}.{name}")
    if missing:
        return CheckResult("unique_constraints", False, f"missing constraints: {', '.join(sorted(missing))}")
    return CheckResult("unique_constraints", True, "expected unique constraints found")


def check_version(connection) -> CheckResult:
    try:
        version = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one()
    except Exception as exc:  # pragma: no cover - depends on external DB state
        return CheckResult("alembic_version", False, str(exc))
    if version != EXPECTED_ALEMBIC_REVISION:
        return CheckResult("alembic_version", False, f"unexpected revision: {version}")
    return CheckResult("alembic_version", True, version)


def check_seed_data(connection) -> CheckResult:
    tenant_id = connection.execute(
        text("SELECT id FROM tenants WHERE code = :code LIMIT 1"),
        {"code": EXPECTED_TENANT_CODE},
    ).scalar_one_or_none()
    if tenant_id is None:
        return CheckResult("seed_data", False, f"missing tenant: {EXPECTED_TENANT_CODE}")

    strategy_codes = {
        row[0]
        for row in connection.execute(
            text("SELECT code FROM strategies WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        ).all()
    }
    missing_strategies = sorted(EXPECTED_STRATEGY_CODES - strategy_codes)
    if missing_strategies:
        return CheckResult("seed_data", False, f"missing strategies: {', '.join(missing_strategies)}")
    return CheckResult("seed_data", True, "expected tenant and strategies found")


def main() -> int:
    engine = get_engine()
    inspector = inspect(engine)
    results: list[CheckResult] = [
        check_tables(inspector),
        check_indexes(inspector),
        check_columns(inspector),
        check_unique_constraints(inspector),
    ]
    with engine.connect() as connection:
        results.append(check_version(connection))
        results.append(check_seed_data(connection))

    for result in results:
        status = "OK" if result.ok else "FAIL"
        print(f"[{status}] {result.name}: {result.detail}")

    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
