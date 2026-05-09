"""Migrate selected legacy SQLite data into the refactored MySQL schema.

The default mode is a read-only dry run. It builds a concrete migration plan
for legacy picks, reports skipped/duplicate/unresolved rows, and exits without
touching MySQL. Use ``--apply`` only after Alembic migrations and seed data have
been validated in a staging database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from backend.db.models import BacktestResult, OperationLog, Pick, ResearchReport, SavedFilter, Strategy, StrategyPool, Tenant, UiSetting
from backend.db.session import session_scope


BASE_DIR = PROJECT_ROOT
SQLITE_DB = BASE_DIR / "data" / "picks.db"

LEGACY_TABLES = (
    "picks",
    "strategies",
    "strategy_pools",
    "backtest_results",
    "ui_settings",
    "saved_filters",
    "operation_logs",
    "research_reports",
)
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

TARGET_PICK_COLUMNS = {
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
    "created_at",
    "updated_at",
}

AUXILIARY_TARGET_COLUMNS = {
    "strategies": {
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
    },
    "ui_settings": {"setting_key", "setting_value", "updated_at"},
    "saved_filters": {"name", "query_string", "created_at"},
    "operation_logs": {
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
}

AUXILIARY_NATURAL_KEYS = {
    "strategies": ("tenant_id", "code"),
    "ui_settings": ("setting_key",),
    "saved_filters": ("name", "query_string"),
    "operation_logs": ("created_at", "action", "target_ids", "detail"),
    "strategy_pools": ("strategy_code", "code"),
    "backtest_results": ("strategy_code", "start_date", "end_date", "backtest_date"),
    "research_reports": ("pick_id", "analysis_date"),
}

APPLY_BLOCKING_ISSUE_CODES = {"invalid_row", "internal_mapping_error"}
APPLY_CONFIRMATION = "sqlite-to-mysql-picks"
RECONCILIATION_IGNORED_FIELDS = {"updated_at"}


@dataclass(frozen=True)
class MigrationIssue:
    row_id: Any
    code: str
    detail: str


@dataclass(frozen=True)
class PickPlanRow:
    legacy_id: Any
    dedupe_key: tuple[int, str, str, str]
    strategy_code: str | None
    target: dict[str, Any]
    issues: list[MigrationIssue]


@dataclass(frozen=True)
class PickMigrationPlan:
    sqlite_db: str
    tenant_id: int
    total_source_rows: int
    planned_rows: list[PickPlanRow]
    skipped_archived: int
    skipped_invalid: int
    duplicates: list[PickPlanRow]
    issues: list[MigrationIssue]

    @property
    def planned_count(self) -> int:
        return len(self.planned_rows)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicates)

    @property
    def unresolved_strategy_count(self) -> int:
        return len({issue.row_id for issue in self.issues if issue.code == "unresolved_strategy"})

    def summary(self) -> dict[str, Any]:
        return {
            "sqlite_db": self.sqlite_db,
            "tenant_id": self.tenant_id,
            "total_source_rows": self.total_source_rows,
            "planned_rows": self.planned_count,
            "skipped_archived": self.skipped_archived,
            "skipped_invalid": self.skipped_invalid,
            "duplicate_rows": self.duplicate_count,
            "unresolved_strategy_rows": self.unresolved_strategy_count,
            "issues": len(self.issues),
        }

    def to_report(self, include_rows: bool = False) -> dict[str, Any]:
        report: dict[str, Any] = {"summary": self.summary()}
        if include_rows:
            report["planned_rows"] = [_json_ready(asdict(row)) for row in self.planned_rows]
            report["duplicates"] = [_json_ready(asdict(row)) for row in self.duplicates]
        if self.issues:
            report["issues"] = [_json_ready(asdict(issue)) for issue in self.issues]
        return report


@dataclass(frozen=True)
class ApplyGateResult:
    ok: bool
    blockers: list[MigrationIssue]
    warnings: list[MigrationIssue]


@dataclass(frozen=True)
class TargetPreconditions:
    tenant_id: int
    tenant_exists: bool
    strategy_map_size: int
    issues: list[MigrationIssue]

    @property
    def ok(self) -> bool:
        return not self.issues

    def to_report(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "tenant_id": self.tenant_id,
            "tenant_exists": self.tenant_exists,
            "strategy_map_size": self.strategy_map_size,
            "issues": [_json_ready(asdict(issue)) for issue in self.issues],
        }


@dataclass(frozen=True)
class FieldMismatch:
    legacy_id: Any
    dedupe_key: tuple[int, str, str, str]
    field: str
    expected: Any
    actual: Any


@dataclass(frozen=True)
class PickReconciliation:
    expected_rows: int
    matched_rows: int
    missing_rows: int
    mismatch_rows: int
    field_mismatches: list[FieldMismatch]

    @property
    def ok(self) -> bool:
        return self.missing_rows == 0 and self.mismatch_rows == 0

    def to_report(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "expected_rows": self.expected_rows,
            "matched_rows": self.matched_rows,
            "missing_rows": self.missing_rows,
            "mismatch_rows": self.mismatch_rows,
            "field_mismatches": [_json_ready(asdict(item)) for item in self.field_mismatches],
        }


@dataclass(frozen=True)
class AuxiliaryMigrationPlan:
    sqlite_db: str
    source_counts: dict[str, int]
    rows_by_table: dict[str, list[dict[str, Any]]]

    def summary(self) -> dict[str, int]:
        return {table: len(rows) for table, rows in self.rows_by_table.items()}

    def to_report(self, include_rows: bool = False) -> dict[str, Any]:
        report: dict[str, Any] = {
            "summary": self.summary(),
            "source_counts": self.source_counts,
        }
        if include_rows:
            report["rows_by_table"] = _json_ready(self.rows_by_table)
        return report


def _quote_identifier(name: str) -> str:
    if not IDENTIFIER_RE.match(name):
        raise ValueError(f"unsafe SQLite identifier: {name!r}")
    return f'"{name}"'


def read_sqlite_rows(table_name: str, sqlite_db: str | Path = SQLITE_DB) -> list[dict[str, Any]]:
    db_path = Path(sqlite_db)
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        table = _quote_identifier(table_name)
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]
    finally:
        conn.close()


def read_sqlite_counts(sqlite_db: str | Path = SQLITE_DB, tables: tuple[str, ...] = LEGACY_TABLES) -> dict[str, int]:
    db_path = Path(sqlite_db)
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    conn = sqlite3.connect(db_path)
    try:
        counts: dict[str, int] = {}
        for table_name in tables:
            table = _quote_identifier(table_name)
            try:
                counts[table_name] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            except sqlite3.OperationalError:
                counts[table_name] = 0
        return counts
    finally:
        conn.close()


def _read_sqlite_rows_if_exists(table_name: str, sqlite_db: str | Path = SQLITE_DB) -> list[dict[str, Any]]:
    try:
        return read_sqlite_rows(table_name, sqlite_db)
    except sqlite3.OperationalError:
        return []


def sqlite_file_fingerprint(sqlite_db: str | Path = SQLITE_DB) -> dict[str, Any]:
    db_path = Path(sqlite_db)
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    digest = hashlib.sha256()
    with db_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = db_path.stat()
    return {
        "path": str(db_path),
        "size_bytes": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "sha256": digest.hexdigest(),
    }


def build_pick_migration_plan(
    sqlite_db: str | Path = SQLITE_DB,
    *,
    tenant_id: int = 1,
    strategy_id_by_code: dict[str, int] | None = None,
    include_archived: bool = False,
) -> PickMigrationPlan:
    rows = read_sqlite_rows("picks", sqlite_db)
    planned_rows: list[PickPlanRow] = []
    duplicate_rows: list[PickPlanRow] = []
    issues: list[MigrationIssue] = []
    seen_keys: set[tuple[int, str, str, str]] = set()
    skipped_archived = 0
    skipped_invalid = 0

    for row in rows:
        row_id = row.get("id")
        if _bool_or_false(row.get("archived")) and not include_archived:
            skipped_archived += 1
            continue

        target, row_issues, strategy_code = _map_pick_row(row, tenant_id, strategy_id_by_code)
        issues.extend(row_issues)
        if target is None:
            skipped_invalid += 1
            continue

        key = (
            int(target["tenant_id"]),
            target["trade_date"].isoformat(),
            str(target["symbol"]),
            str(target["source"]),
        )
        plan_row = PickPlanRow(
            legacy_id=row_id,
            dedupe_key=key,
            strategy_code=strategy_code,
            target=target,
            issues=row_issues,
        )
        if key in seen_keys:
            duplicate_rows.append(plan_row)
            duplicate_issue = MigrationIssue(row_id, "duplicate_key", f"duplicate pick key: {key!r}")
            issues.append(duplicate_issue)
            continue
        seen_keys.add(key)
        planned_rows.append(plan_row)

    return PickMigrationPlan(
        sqlite_db=str(Path(sqlite_db)),
        tenant_id=tenant_id,
        total_source_rows=len(rows),
        planned_rows=planned_rows,
        skipped_archived=skipped_archived,
        skipped_invalid=skipped_invalid,
        duplicates=duplicate_rows,
        issues=issues,
    )


def build_auxiliary_migration_plan(sqlite_db: str | Path = SQLITE_DB) -> AuxiliaryMigrationPlan:
    rows_by_table: dict[str, list[dict[str, Any]]] = {}
    for table_name in (
        "strategies",
        "strategy_pools",
        "backtest_results",
        "ui_settings",
        "saved_filters",
        "operation_logs",
        "research_reports",
    ):
        rows_by_table[table_name] = _read_sqlite_rows_if_exists(table_name, sqlite_db)
    return AuxiliaryMigrationPlan(
        sqlite_db=str(Path(sqlite_db)),
        source_counts=read_sqlite_counts(sqlite_db),
        rows_by_table=rows_by_table,
    )


def _map_pick_row(
    row: dict[str, Any],
    tenant_id: int,
    strategy_id_by_code: dict[str, int] | None,
) -> tuple[dict[str, Any] | None, list[MigrationIssue], str | None]:
    row_id = row.get("id")
    issues: list[MigrationIssue] = []
    symbol = _text_or_none(row.get("code"))
    trade_date = _date_or_none(row.get("pick_date"))
    if not symbol:
        return None, [MigrationIssue(row_id, "invalid_row", "missing code/symbol")], None
    if trade_date is None:
        return None, [MigrationIssue(row_id, "invalid_row", "missing or invalid pick_date")], None

    strategy_code = _text_or_none(row.get("strategy_name")) or _text_or_none(row.get("source"))
    strategy_id = None
    if strategy_code and strategy_id_by_code is not None:
        strategy_id = strategy_id_by_code.get(strategy_code)
        if strategy_id is None:
            issues.append(MigrationIssue(row_id, "unresolved_strategy", f"no target strategy for {strategy_code!r}"))
    elif strategy_code:
        issues.append(MigrationIssue(row_id, "unresolved_strategy", f"strategy code not resolved: {strategy_code!r}"))

    legacy_payload = _legacy_payload(row)

    created_at = _datetime_or_none(row.get("created_at")) or datetime.combine(trade_date, datetime.min.time())
    target = {
        "tenant_id": tenant_id,
        "symbol": symbol,
        "stock_name": _text_or_none(row.get("name")),
        "trade_date": trade_date,
        "strategy_id": strategy_id,
        "source": _text_or_none(row.get("source")) or "legacy_sqlite",
        "source_channel": _text_or_none(row.get("source_channel")) or "legacy_sqlite",
        "reason": _joined_reason(row),
        "score": _float_or_none(row.get("second_board_score")),
        "status": _text_or_none(row.get("review_status")) or "active",
        "review_comment": _text_or_none(row.get("review_comment")) or _text_or_none(row.get("note")),
        "risk_level": _text_or_none(row.get("result_grade")),
        "deal_status": _text_or_none(row.get("deal_status")),
        "return_pct": _float_or_none(row.get("return_pct")),
        "max_return_pct": _float_or_none(row.get("max_return_pct")),
        "drawdown_pct": _float_or_none(row.get("drawdown_pct")),
        "holding_days": _int_or_none(row.get("holding_days")),
        "watch_flag": _bool_or_false(row.get("watch_flag")),
        "validation_result": _text_or_none(row.get("validation_result")),
        "validation_note": _text_or_none(row.get("validation_note")),
        "validated_at": _datetime_or_none(row.get("validated_at")),
        "data_quality": _text_or_none(row.get("data_quality")),
        "market_data_source": _text_or_none(row.get("market_data_source")),
        "fallback_used": _bool_or_false(row.get("fallback_used")),
        "legacy_payload_json": legacy_payload,
        "created_at": created_at,
        "updated_at": created_at,
    }
    unexpected_columns = sorted(set(target) - TARGET_PICK_COLUMNS)
    if unexpected_columns:
        issues.append(MigrationIssue(row_id, "internal_mapping_error", ",".join(unexpected_columns)))
    return target, issues, strategy_code


def load_strategy_id_map(session, tenant_id: int) -> dict[str, int]:
    strategy_rows = session.execute(
        select(Strategy.id, Strategy.code, Strategy.name).where(Strategy.tenant_id == tenant_id)
    ).all()
    strategy_map: dict[str, int] = {}
    for strategy_id, code, name in strategy_rows:
        if code:
            strategy_map[str(code)] = int(strategy_id)
        if name:
            strategy_map[str(name)] = int(strategy_id)
    return strategy_map


def load_target_preconditions(session, tenant_id: int, strategy_map: dict[str, int]) -> TargetPreconditions:
    issues: list[MigrationIssue] = []
    tenant_exists = session.execute(select(Tenant.id).where(Tenant.id == tenant_id)).scalar_one_or_none() is not None
    if not tenant_exists:
        issues.append(MigrationIssue(None, "target_tenant_missing", f"target tenant_id {tenant_id} does not exist"))
    if not strategy_map:
        issues.append(MigrationIssue(None, "target_strategy_seed_missing", f"tenant_id {tenant_id} has no strategies"))
    return TargetPreconditions(
        tenant_id=tenant_id,
        tenant_exists=tenant_exists,
        strategy_map_size=len(strategy_map),
        issues=issues,
    )


def apply_pick_plan(plan: PickMigrationPlan, session) -> dict[str, int]:
    inserted = 0
    existing = 0
    backfilled_existing = 0
    for row in plan.planned_rows:
        target = row.target
        found = session.execute(
            select(Pick).where(
                Pick.tenant_id == target["tenant_id"],
                Pick.trade_date == target["trade_date"],
                Pick.symbol == target["symbol"],
                Pick.source == target["source"],
            )
        ).scalar_one_or_none()
        if found is not None:
            existing += 1
            if found.legacy_payload_json is None and target.get("legacy_payload_json") is not None:
                found.legacy_payload_json = target["legacy_payload_json"]
                backfilled_existing += 1
            continue
        session.add(Pick(**target))
        inserted += 1
    return {
        "inserted": inserted,
        "existing": existing,
        "backfilled_existing": backfilled_existing,
        "duplicates": plan.duplicate_count,
    }


def apply_auxiliary_plan(plan: AuxiliaryMigrationPlan, session, *, tenant_id: int = 1) -> dict[str, dict[str, int]]:
    return {
        "strategies": _apply_legacy_strategies(plan.rows_by_table.get("strategies", []), session, tenant_id=tenant_id),
        "ui_settings": _apply_ui_settings(plan.rows_by_table.get("ui_settings", []), session),
        "saved_filters": _apply_saved_filters(plan.rows_by_table.get("saved_filters", []), session),
        "operation_logs": _apply_operation_logs(plan.rows_by_table.get("operation_logs", []), session),
        "strategy_pools": _apply_strategy_pools(plan.rows_by_table.get("strategy_pools", []), session),
        "backtest_results": _apply_backtest_results(plan.rows_by_table.get("backtest_results", []), session),
        "research_reports": _apply_research_reports(plan.rows_by_table.get("research_reports", []), session),
    }


def _apply_legacy_strategies(rows: list[dict[str, Any]], session, *, tenant_id: int) -> dict[str, int]:
    inserted = 0
    existing = 0
    updated = 0
    for row in rows:
        code = _text_or_none(row.get("code"))
        if not code:
            continue
        found = session.execute(
            select(Strategy).where(Strategy.tenant_id == tenant_id, Strategy.code == code)
        ).scalar_one_or_none()
        is_active = _bool_or_false(row.get("is_active", 1))
        sort_order = _int_or_none(row.get("sort_order")) or 0
        if found is None:
            session.add(
                Strategy(
                    tenant_id=tenant_id,
                    code=code,
                    name=_text_or_none(row.get("name")) or code,
                    category=_text_or_none(row.get("category")) or "",
                    description=_text_or_none(row.get("description")) or "",
                    config_json=None,
                    enabled=is_active,
                    is_active=is_active,
                    sort_order=sort_order,
                    created_by=None,
                    created_at=_datetime_or_none(row.get("created_at")) or datetime.now(),
                    updated_at=_datetime_or_none(row.get("updated_at")) or datetime.now(),
                )
            )
            inserted += 1
            continue
        existing += 1
        found.name = _text_or_none(row.get("name")) or found.name
        found.category = _text_or_none(row.get("category")) or found.category
        found.description = _text_or_none(row.get("description")) or found.description
        found.enabled = is_active
        found.is_active = is_active
        found.sort_order = sort_order
        found.deleted_at = None if is_active else found.deleted_at
        updated += 1
    return {"inserted": inserted, "existing": existing, "updated": updated}


def _apply_ui_settings(rows: list[dict[str, Any]], session) -> dict[str, int]:
    inserted = 0
    updated = 0
    for row in rows:
        key = _text_or_none(row.get("setting_key"))
        if not key:
            continue
        found = session.get(UiSetting, key)
        value = str(row.get("setting_value") or "")
        updated_at = _datetime_or_none(row.get("updated_at")) or datetime.now()
        if found is None:
            session.add(UiSetting(setting_key=key, setting_value=value, updated_at=updated_at))
            inserted += 1
        else:
            found.setting_value = value
            found.updated_at = updated_at
            updated += 1
    return {"inserted": inserted, "updated": updated}


def _apply_saved_filters(rows: list[dict[str, Any]], session) -> dict[str, int]:
    inserted = 0
    existing = 0
    for row in rows:
        name = _text_or_none(row.get("name"))
        query_string = _text_or_none(row.get("query_string"))
        if not name or query_string is None:
            continue
        found = session.execute(
            select(SavedFilter).where(SavedFilter.name == name, SavedFilter.query_string == query_string)
        ).scalars().first()
        if found is not None:
            existing += 1
            continue
        session.add(
            SavedFilter(
                name=name,
                query_string=query_string,
                created_at=_datetime_or_none(row.get("created_at")) or datetime.now(),
            )
        )
        inserted += 1
    return {"inserted": inserted, "existing": existing}


def _apply_operation_logs(rows: list[dict[str, Any]], session) -> dict[str, int]:
    inserted = 0
    existing = 0
    for row in rows:
        created_at = _datetime_or_none(row.get("created_at")) or datetime.now()
        action = _text_or_none(row.get("action")) or ""
        detail = (_text_or_none(row.get("detail")) or "")[:1000]
        target_ids = (_text_or_none(row.get("target_ids")) or "")[:512]
        found = session.execute(
            select(OperationLog).where(
                OperationLog.created_at == created_at,
                OperationLog.action == action,
                OperationLog.target_ids == target_ids,
                OperationLog.detail == detail,
            )
        ).scalars().first()
        if found is not None:
            existing += 1
            continue
        session.add(
            OperationLog(
                action=action,
                target_ids=target_ids,
                detail=detail,
                user_id=_int_or_none(row.get("user_id")),
                username=(_text_or_none(row.get("username")) or "")[:64],
                ip=(_text_or_none(row.get("ip")) or "")[:64],
                user_agent=(_text_or_none(row.get("user_agent")) or "")[:200],
                created_at=created_at,
            )
        )
        inserted += 1
    return {"inserted": inserted, "existing": existing}


def _apply_strategy_pools(rows: list[dict[str, Any]], session) -> dict[str, int]:
    inserted = 0
    existing = 0
    updated = 0
    for row in rows:
        strategy_code = _text_or_none(row.get("strategy_code"))
        code = _text_or_none(row.get("code"))
        if not strategy_code or not code:
            continue
        found = session.execute(
            select(StrategyPool).where(StrategyPool.strategy_code == strategy_code, StrategyPool.code == code)
        ).scalar_one_or_none()
        if found is None:
            session.add(
                StrategyPool(
                    strategy_code=strategy_code,
                    code=code,
                    name=_text_or_none(row.get("name")) or code,
                    add_date=_text_or_none(row.get("add_date")) or "",
                    add_price=_float_or_none(row.get("add_price")),
                    reason=_text_or_none(row.get("reason")) or "",
                    status=_text_or_none(row.get("status")) or "active",
                    created_at=_datetime_or_none(row.get("created_at")) or datetime.now(),
                )
            )
            inserted += 1
            continue
        existing += 1
        found.name = _text_or_none(row.get("name")) or found.name
        found.add_date = _text_or_none(row.get("add_date")) or found.add_date
        found.add_price = _float_or_none(row.get("add_price"))
        found.reason = _text_or_none(row.get("reason")) or ""
        found.status = _text_or_none(row.get("status")) or "active"
        updated += 1
    return {"inserted": inserted, "existing": existing, "updated": updated}


def _apply_backtest_results(rows: list[dict[str, Any]], session) -> dict[str, int]:
    inserted = 0
    existing = 0
    for row in rows:
        strategy_code = _text_or_none(row.get("strategy_code"))
        start_date = _text_or_none(row.get("start_date"))
        end_date = _text_or_none(row.get("end_date"))
        if not strategy_code or not start_date or not end_date:
            continue
        backtest_date = _datetime_or_none(row.get("backtest_date")) or datetime.now()
        found = session.execute(
            select(BacktestResult).where(
                BacktestResult.strategy_code == strategy_code,
                BacktestResult.start_date == start_date,
                BacktestResult.end_date == end_date,
                BacktestResult.backtest_date == backtest_date,
            )
        ).scalars().first()
        if found is not None:
            existing += 1
            continue
        session.add(
            BacktestResult(
                strategy_code=strategy_code,
                start_date=start_date,
                end_date=end_date,
                total_trades=_int_or_none(row.get("total_trades")),
                win_rate=_float_or_none(row.get("win_rate")),
                avg_return=_float_or_none(row.get("avg_return")),
                max_return=_float_or_none(row.get("max_return")),
                max_drawdown=_float_or_none(row.get("max_drawdown")),
                sharpe_ratio=_float_or_none(row.get("sharpe_ratio")),
                total_return=_float_or_none(row.get("total_return")),
                backtest_date=backtest_date,
            )
        )
        inserted += 1
    return {"inserted": inserted, "existing": existing}


def _apply_research_reports(rows: list[dict[str, Any]], session) -> dict[str, int]:
    inserted = 0
    existing = 0
    updated = 0
    for row in rows:
        pick_id = _int_or_none(row.get("pick_id"))
        analysis_date = _text_or_none(row.get("analysis_date"))
        if pick_id is None or not analysis_date:
            continue
        found = session.execute(
            select(ResearchReport).where(
                ResearchReport.pick_id == pick_id,
                ResearchReport.analysis_date == analysis_date,
            )
        ).scalar_one_or_none()
        now = datetime.now()
        if found is None:
            found = ResearchReport(
                pick_id=pick_id,
                code=_text_or_none(row.get("code")) or "",
                pick_date=_text_or_none(row.get("pick_date")) or "",
                analysis_date=analysis_date,
                created_at=_datetime_or_none(row.get("created_at")) or now,
                updated_at=_datetime_or_none(row.get("updated_at")) or now,
            )
            session.add(found)
            inserted += 1
        else:
            existing += 1
            updated += 1
        found.code = _text_or_none(row.get("code")) or found.code
        found.pick_date = _text_or_none(row.get("pick_date")) or found.pick_date
        found.technical_score = _float_or_none(row.get("technical_score"))
        found.momentum_score = _float_or_none(row.get("momentum_score"))
        found.risk_score = _float_or_none(row.get("risk_score"))
        found.liquidity_score = _float_or_none(row.get("liquidity_score"))
        found.timing_score = _float_or_none(row.get("timing_score"))
        found.total_score = _float_or_none(row.get("total_score"))
        found.research_summary = _text_or_none(row.get("research_summary")) or ""
        found.action_suggestion = _text_or_none(row.get("action_suggestion")) or ""
        found.risk_warning = _text_or_none(row.get("risk_warning")) or ""
        found.data_snapshot = _text_or_none(row.get("data_snapshot")) or ""
        found.updated_at = _datetime_or_none(row.get("updated_at")) or now
    return {"inserted": inserted, "existing": existing, "updated": updated}


def validate_apply_gate(
    plan: PickMigrationPlan,
    *,
    target_preconditions: TargetPreconditions | None = None,
    allow_unresolved_strategies: bool = False,
    allow_skipped_invalid: bool = False,
) -> ApplyGateResult:
    blockers: list[MigrationIssue] = []
    warnings: list[MigrationIssue] = []
    if target_preconditions is not None:
        blockers.extend(target_preconditions.issues)
    for issue in plan.issues:
        if issue.code == "invalid_row" and allow_skipped_invalid:
            warnings.append(issue)
        elif issue.code in APPLY_BLOCKING_ISSUE_CODES:
            blockers.append(issue)
        elif issue.code == "unresolved_strategy" and not allow_unresolved_strategies:
            blockers.append(issue)
        else:
            warnings.append(issue)
    if plan.skipped_invalid and not allow_skipped_invalid:
        blockers.append(MigrationIssue(None, "skipped_invalid_rows", f"{plan.skipped_invalid} invalid source rows skipped"))
    return ApplyGateResult(ok=not blockers, blockers=blockers, warnings=warnings)


def reconcile_pick_plan(plan: PickMigrationPlan, session) -> PickReconciliation:
    matched_rows = 0
    missing_rows = 0
    mismatched_keys: set[tuple[int, str, str, str]] = set()
    field_mismatches: list[FieldMismatch] = []
    for row in plan.planned_rows:
        target = row.target
        existing = session.execute(
            select(Pick).where(
                Pick.tenant_id == target["tenant_id"],
                Pick.trade_date == target["trade_date"],
                Pick.symbol == target["symbol"],
                Pick.source == target["source"],
            )
        ).scalar_one_or_none()
        if existing is None:
            missing_rows += 1
            mismatched_keys.add(row.dedupe_key)
            field_mismatches.append(FieldMismatch(row.legacy_id, row.dedupe_key, "__row__", "present", "missing"))
            continue
        matched_rows += 1
        for field, expected in target.items():
            if field in RECONCILIATION_IGNORED_FIELDS:
                continue
            actual = getattr(existing, field)
            if not _values_equal(expected, actual):
                mismatched_keys.add(row.dedupe_key)
                field_mismatches.append(FieldMismatch(row.legacy_id, row.dedupe_key, field, expected, actual))
    return PickReconciliation(
        expected_rows=plan.planned_count,
        matched_rows=matched_rows,
        missing_rows=missing_rows,
        mismatch_rows=len(mismatched_keys),
        field_mismatches=field_mismatches,
    )


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_or_false(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _date_or_none(value: Any) -> date | None:
    text = _text_or_none(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10] if fmt != "%Y%m%d" else text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _datetime_or_none(value: Any) -> datetime | None:
    text = _text_or_none(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed_date = _date_or_none(text)
        if parsed_date is None:
            return None
        return datetime.combine(parsed_date, datetime.min.time())
    return parsed.replace(tzinfo=None)


def _joined_reason(row: dict[str, Any]) -> str | None:
    parts: list[str] = []
    for key in ("reason_tag", "signal", "theme_reason", "second_board_expectation", "prediction_reason"):
        value = _text_or_none(row.get(key))
        if value:
            parts.append(value)
    return " | ".join(parts) or None


def _has_any(row: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(_text_or_none(row.get(key)) for key in keys)


def _legacy_payload(row: dict[str, Any]) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}
    for key in (
        "pick_price",
        "ma25",
        "vol_ratio",
        "content_title",
        "content_ref",
        "inquiry_count",
        "secondary_spread",
        "last_price",
        "quote_time",
        "first_board_time",
        "second_board_expectation",
    ):
        value = row.get(key)
        if value not in (None, ""):
            payload[key] = value
    return payload or None


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _values_equal(expected: Any, actual: Any) -> bool:
    if expected == actual:
        return True
    if isinstance(actual, Decimal) and isinstance(expected, (float, int)):
        return Decimal(str(expected)) == actual
    if isinstance(expected, Decimal) and isinstance(actual, (float, int)):
        return expected == Decimal(str(actual))
    if isinstance(expected, datetime) and isinstance(actual, datetime):
        return expected.replace(microsecond=0) == actual.replace(microsecond=0)
    if isinstance(expected, date) and isinstance(actual, datetime):
        return expected == actual.date()
    if isinstance(expected, datetime) and isinstance(actual, date):
        return expected.date() == actual
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-db", default=str(SQLITE_DB), help="legacy SQLite database path")
    parser.add_argument("--tenant-id", type=int, default=1, help="target tenant id for migrated legacy rows")
    parser.add_argument("--include-archived", action="store_true", help="include archived legacy picks")
    parser.add_argument("--resolve-strategies", action="store_true", help="read target MySQL strategies to resolve ids")
    parser.add_argument("--verify", action="store_true", help="compare planned picks with existing target rows")
    parser.add_argument("--apply", action="store_true", help="write planned picks into MySQL")
    parser.add_argument(
        "--confirm-apply",
        default="",
        help=f"required confirmation token for --apply: {APPLY_CONFIRMATION}",
    )
    parser.add_argument(
        "--allow-unresolved-strategies",
        action="store_true",
        help="allow --apply when strategy_id cannot be resolved",
    )
    parser.add_argument("--allow-skipped-invalid", action="store_true", help="allow --apply when invalid rows were skipped")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--rows", action="store_true", help="include planned row details in output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    strategy_map = None
    target_preconditions = None
    apply_result = None
    auxiliary_plan = None
    auxiliary_apply_result = None
    apply_gate = None
    reconciliation = None

    if args.apply and args.confirm_apply != APPLY_CONFIRMATION:
        error = {
            "error": "missing_apply_confirmation",
            "detail": f"--apply requires --confirm-apply {APPLY_CONFIRMATION}",
        }
        if args.json:
            print(json.dumps(error, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(error["detail"])
        return 2

    if args.apply or args.verify:
        args.resolve_strategies = True

    if args.resolve_strategies:
        with session_scope() as session:
            strategy_map = load_strategy_id_map(session, args.tenant_id)
            target_preconditions = load_target_preconditions(session, args.tenant_id, strategy_map)
            plan = build_pick_migration_plan(
                args.sqlite_db,
                tenant_id=args.tenant_id,
                strategy_id_by_code=strategy_map,
                include_archived=args.include_archived,
            )
            if args.apply:
                apply_gate = validate_apply_gate(
                    plan,
                    target_preconditions=target_preconditions,
                    allow_unresolved_strategies=args.allow_unresolved_strategies,
                    allow_skipped_invalid=args.allow_skipped_invalid,
                )
                if not apply_gate.ok:
                    output = plan.to_report(include_rows=args.rows)
                    output["legacy_counts"] = read_sqlite_counts(args.sqlite_db)
                    output["sqlite_fingerprint"] = sqlite_file_fingerprint(args.sqlite_db)
                    output["auxiliary_plan"] = build_auxiliary_migration_plan(args.sqlite_db).to_report(include_rows=args.rows)
                    output["strategy_map_size"] = len(strategy_map)
                    output["target_preconditions"] = target_preconditions.to_report()
                    output["apply_gate"] = _apply_gate_report(apply_gate)
                    _emit_output(output, args.json, applied=False)
                    return 1
                apply_result = apply_pick_plan(plan, session)
                auxiliary_plan = build_auxiliary_migration_plan(args.sqlite_db)
                auxiliary_apply_result = apply_auxiliary_plan(auxiliary_plan, session, tenant_id=args.tenant_id)
                session.flush()
            if args.verify or args.apply:
                reconciliation = reconcile_pick_plan(plan, session)
    else:
        plan = build_pick_migration_plan(
            args.sqlite_db,
            tenant_id=args.tenant_id,
            include_archived=args.include_archived,
        )

    output = plan.to_report(include_rows=args.rows)
    output["legacy_counts"] = read_sqlite_counts(args.sqlite_db)
    output["sqlite_fingerprint"] = sqlite_file_fingerprint(args.sqlite_db)
    if auxiliary_plan is None:
        auxiliary_plan = build_auxiliary_migration_plan(args.sqlite_db)
    output["auxiliary_plan"] = auxiliary_plan.to_report(include_rows=args.rows)
    if strategy_map is not None:
        output["strategy_map_size"] = len(strategy_map)
    if target_preconditions is not None:
        output["target_preconditions"] = target_preconditions.to_report()
    if apply_gate is not None:
        output["apply_gate"] = _apply_gate_report(apply_gate)
    if apply_result is not None:
        output["apply_result"] = apply_result
    if auxiliary_apply_result is not None:
        output["auxiliary_apply_result"] = auxiliary_apply_result
    if reconciliation is not None:
        output["reconciliation"] = reconciliation.to_report()

    _emit_output(output, args.json, applied=args.apply)
    return 0


def _apply_gate_report(result: ApplyGateResult) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "blockers": [_json_ready(asdict(issue)) for issue in result.blockers],
        "warnings": [_json_ready(asdict(issue)) for issue in result.warnings],
    }


def _emit_output(output: dict[str, Any], as_json: bool, *, applied: bool) -> None:
    if as_json:
        print(json.dumps(_json_ready(output), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text_report(output, applied=applied)


def _print_text_report(output: dict[str, Any], *, applied: bool) -> None:
    mode = "apply" if applied else "dry-run"
    print(f"sqlite -> mysql picks migration {mode}")
    for key, value in output["summary"].items():
        print(f"{key}: {value}")
    if "legacy_counts" in output:
        print("legacy table counts:")
        for table, count in output["legacy_counts"].items():
            print(f"  {table}: {count}")
    if "auxiliary_plan" in output:
        print("auxiliary migration plan:")
        for table, count in output["auxiliary_plan"]["summary"].items():
            print(f"  {table}: {count}")
    if "apply_result" in output:
        print("apply result:")
        for key, value in output["apply_result"].items():
            print(f"  {key}: {value}")
    if "auxiliary_apply_result" in output:
        print("auxiliary apply result:")
        for table, result in output["auxiliary_apply_result"].items():
            detail = ", ".join(f"{key}={value}" for key, value in result.items())
            print(f"  {table}: {detail}")
    if "apply_gate" in output:
        print("apply gate:")
        print(f"  ok: {output['apply_gate']['ok']}")
        print(f"  blockers: {len(output['apply_gate']['blockers'])}")
        print(f"  warnings: {len(output['apply_gate']['warnings'])}")
    if "reconciliation" in output:
        print("reconciliation:")
        for key, value in output["reconciliation"].items():
            if key != "field_mismatches":
                print(f"  {key}: {value}")
    if output.get("issues"):
        print("issues:")
        for issue in output["issues"][:20]:
            print(f"  row {issue['row_id']}: {issue['code']} - {issue['detail']}")
        if len(output["issues"]) > 20:
            print(f"  ... {len(output['issues']) - 20} more")


if __name__ == "__main__":
    sys.exit(main())
