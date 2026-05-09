import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.db.base import Base
from backend.db.models import BacktestResult, OperationLog, Pick, ResearchReport, SavedFilter, Strategy, StrategyPool, Tenant, UiSetting
from scripts.migrate_sqlite_to_mysql import (
    APPLY_CONFIRMATION,
    AUXILIARY_NATURAL_KEYS,
    AUXILIARY_TARGET_COLUMNS,
    TARGET_PICK_COLUMNS,
    apply_auxiliary_plan,
    apply_pick_plan,
    build_auxiliary_migration_plan,
    build_pick_migration_plan,
    load_strategy_id_map,
    load_target_preconditions,
    main,
    read_sqlite_counts,
    read_sqlite_rows,
    reconcile_pick_plan,
    sqlite_file_fingerprint,
    validate_apply_gate,
)


def _create_legacy_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE picks (
                id INTEGER PRIMARY KEY,
                pick_date TEXT,
                code TEXT,
                name TEXT,
                source TEXT,
                source_channel TEXT,
                strategy_name TEXT,
                review_status TEXT,
                review_comment TEXT,
                result_grade TEXT,
                deal_status TEXT,
                return_pct REAL,
                max_return_pct REAL,
                drawdown_pct REAL,
                holding_days INTEGER,
                watch_flag INTEGER,
                validation_result TEXT,
                validation_note TEXT,
                validated_at TEXT,
                data_quality TEXT,
                market_data_source TEXT,
                fallback_used INTEGER,
                reason_tag TEXT,
                signal TEXT,
                theme_reason TEXT,
                second_board_expectation TEXT,
                prediction_reason TEXT,
                second_board_score INTEGER,
                archived INTEGER,
                created_at TEXT,
                content_title TEXT,
                pick_price REAL
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO picks (
                id, pick_date, code, name, source, source_channel, strategy_name,
                review_status, review_comment, result_grade, deal_status,
                return_pct, max_return_pct, drawdown_pct, holding_days,
                watch_flag, validation_result, validation_note, validated_at,
                data_quality, market_data_source, fallback_used, reason_tag,
                signal, theme_reason, second_board_expectation, prediction_reason,
                second_board_score, archived, created_at, content_title, pick_price
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    1,
                    "2026-05-01",
                    "000001",
                    "Ping An Bank",
                    "2560",
                    "scan",
                    "2560",
                    "validated",
                    "review ok",
                    "medium",
                    "filled",
                    3.5,
                    5.0,
                    -1.2,
                    3,
                    1,
                    "win",
                    "confirmed",
                    "2026-05-02T09:30:00",
                    "ok",
                    "akshare",
                    1,
                    "ma-cross",
                    "breakout",
                    "theme",
                    "next board",
                    "volume",
                    88,
                    0,
                    "2026-05-01T15:00:00",
                    "legacy article",
                    10.23,
                ),
                (
                    2,
                    "2026-05-01",
                    "000001",
                    "Ping An Bank",
                    "2560",
                    "scan",
                    "2560",
                    "validated",
                    "duplicate",
                    "medium",
                    "filled",
                    1.0,
                    2.0,
                    -0.5,
                    2,
                    0,
                    "win",
                    "",
                    "",
                    "ok",
                    "akshare",
                    0,
                    "",
                    "",
                    "",
                    "",
                    "",
                    50,
                    0,
                    "2026-05-01T15:01:00",
                    "",
                    None,
                ),
                (
                    3,
                    "2026-05-02",
                    "000002",
                    "Archived",
                    "2560",
                    "scan",
                    "2560",
                    "",
                    "",
                    "",
                    "",
                    None,
                    None,
                    None,
                    None,
                    0,
                    "",
                    "",
                    "",
                    "",
                    "",
                    0,
                    "",
                    "",
                    "",
                    "",
                    "",
                    None,
                    1,
                    "2026-05-02T15:00:00",
                    "",
                    None,
                ),
                (
                    4,
                    "",
                    "000003",
                    "Invalid",
                    "2560",
                    "scan",
                    "2560",
                    "",
                    "",
                    "",
                    "",
                    None,
                    None,
                    None,
                    None,
                    0,
                    "",
                    "",
                    "",
                    "",
                    "",
                    0,
                    "",
                    "",
                    "",
                    "",
                    "",
                    None,
                    0,
                    "",
                    "",
                    None,
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _create_legacy_auxiliary_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE strategies (
                id INTEGER PRIMARY KEY,
                code TEXT,
                name TEXT,
                category TEXT,
                description TEXT,
                is_active INTEGER,
                sort_order INTEGER,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE ui_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE saved_filters (
                id INTEGER PRIMARY KEY,
                name TEXT,
                query_string TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE operation_logs (
                id INTEGER PRIMARY KEY,
                action TEXT,
                target_ids TEXT,
                detail TEXT,
                user_id INTEGER,
                username TEXT,
                ip TEXT,
                user_agent TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE strategy_pools (
                id INTEGER PRIMARY KEY,
                strategy_code TEXT,
                code TEXT,
                name TEXT,
                add_date TEXT,
                add_price REAL,
                reason TEXT,
                status TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE backtest_results (
                id INTEGER PRIMARY KEY,
                strategy_code TEXT,
                start_date TEXT,
                end_date TEXT,
                total_trades INTEGER,
                win_rate REAL,
                avg_return REAL,
                max_return REAL,
                max_drawdown REAL,
                sharpe_ratio REAL,
                total_return REAL,
                backtest_date TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE research_reports (
                id INTEGER PRIMARY KEY,
                pick_id INTEGER,
                code TEXT,
                pick_date TEXT,
                analysis_date TEXT,
                technical_score REAL,
                momentum_score REAL,
                risk_score REAL,
                liquidity_score REAL,
                timing_score REAL,
                total_score REAL,
                research_summary TEXT,
                action_suggestion TEXT,
                risk_warning TEXT,
                data_snapshot TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO strategies VALUES (1, 'legacy_strategy', 'Legacy Strategy', 'cat', 'desc', 1, 9, '2026-05-01 09:00:00', '2026-05-01 10:00:00')"
        )
        conn.execute("INSERT INTO ui_settings VALUES ('dashboard_order', 'kpi,records', '2026-05-01 09:00:00')")
        conn.execute("INSERT INTO saved_filters VALUES (1, 'active picks', 'status=active', '2026-05-01 09:00:00')")
        conn.execute(
            "INSERT INTO operation_logs VALUES (1, 'import', '1,2', 'detail', 7, 'admin', '127.0.0.1', 'agent', '2026-05-01 09:00:00')"
        )
        conn.execute(
            "INSERT INTO operation_logs VALUES (2, 'import', '1,2', 'detail', 7, 'admin', '127.0.0.1', 'agent', '2026-05-01 09:00:00')"
        )
        conn.execute(
            "INSERT INTO strategy_pools VALUES (1, 'legacy_strategy', '000001', 'Ping An Bank', '2026-05-01', 10.25, 'reason', 'active', '2026-05-01 09:00:00')"
        )
        conn.execute(
            "INSERT INTO backtest_results VALUES (1, 'legacy_strategy', '2026-01-01', '2026-05-01', 3, 0.5, 0.01, 0.03, 0.02, 1.2, 0.04, '2026-05-01 09:00:00')"
        )
        conn.execute(
            "INSERT INTO research_reports VALUES (1, 1, '000001', '2026-05-01', '2026-05-02', 1, 2, 3, 4, 5, 88, 'summary', 'watch', 'risk', '{}', '2026-05-02 09:00:00', '2026-05-02 10:00:00')"
        )
        conn.commit()
    finally:
        conn.close()


def test_pick_migration_plan_maps_legacy_fields(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)

    plan = build_pick_migration_plan(db_path, tenant_id=1, strategy_id_by_code={"2560": 88})

    assert plan.total_source_rows == 4
    assert plan.planned_count == 1
    assert plan.duplicate_count == 1
    assert plan.skipped_archived == 1
    assert plan.skipped_invalid == 1
    assert plan.unresolved_strategy_count == 0

    target = plan.planned_rows[0].target
    assert set(target) == TARGET_PICK_COLUMNS
    assert target["tenant_id"] == 1
    assert target["symbol"] == "000001"
    assert target["stock_name"] == "Ping An Bank"
    assert target["trade_date"].isoformat() == "2026-05-01"
    assert target["strategy_id"] == 88
    assert target["status"] == "validated"
    assert target["risk_level"] == "medium"
    assert target["watch_flag"] is True
    assert target["fallback_used"] is True
    assert target["return_pct"] == 3.5
    assert target["max_return_pct"] == 5.0
    assert target["drawdown_pct"] == -1.2
    assert target["holding_days"] == 3
    assert target["validation_result"] == "win"
    assert target["validated_at"].isoformat() == "2026-05-02T09:30:00"
    assert target["reason"] == "ma-cross | breakout | theme | next board | volume"
    assert target["legacy_payload_json"]["pick_price"] == 10.23
    assert target["legacy_payload_json"]["content_title"] == "legacy article"


def test_auxiliary_migration_plan_counts_legacy_tables(tmp_path):
    db_path = tmp_path / "legacy_aux.db"
    _create_legacy_auxiliary_db(db_path)

    plan = build_auxiliary_migration_plan(db_path)

    assert plan.summary() == {
        "strategies": 1,
        "strategy_pools": 1,
        "backtest_results": 1,
        "ui_settings": 1,
        "saved_filters": 1,
        "operation_logs": 2,
        "research_reports": 1,
    }
    assert plan.source_counts["strategies"] == 1
    assert plan.rows_by_table["ui_settings"][0]["setting_key"] == "dashboard_order"


def test_auxiliary_migration_contract_is_explicit():
    assert AUXILIARY_NATURAL_KEYS == {
        "strategies": ("tenant_id", "code"),
        "ui_settings": ("setting_key",),
        "saved_filters": ("name", "query_string"),
        "operation_logs": ("created_at", "action", "target_ids", "detail"),
        "strategy_pools": ("strategy_code", "code"),
        "backtest_results": ("strategy_code", "start_date", "end_date", "backtest_date"),
        "research_reports": ("pick_id", "analysis_date"),
    }
    assert {"enabled", "is_active", "sort_order"} <= AUXILIARY_TARGET_COLUMNS["strategies"]
    assert {"setting_key", "setting_value", "updated_at"} == AUXILIARY_TARGET_COLUMNS["ui_settings"]
    assert {"strategy_code", "code", "status"} <= AUXILIARY_TARGET_COLUMNS["strategy_pools"]
    assert {"total_trades", "win_rate", "total_return"} <= AUXILIARY_TARGET_COLUMNS["backtest_results"]
    assert {"pick_id", "analysis_date", "technical_score", "total_score"} <= AUXILIARY_TARGET_COLUMNS["research_reports"]


def test_apply_auxiliary_plan_is_idempotent_and_maps_legacy_fields(tmp_path):
    db_path = tmp_path / "legacy_aux.db"
    _create_legacy_auxiliary_db(db_path)
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        plan = build_auxiliary_migration_plan(db_path)
        first = apply_auxiliary_plan(plan, session, tenant_id=1)
        session.commit()
        second = apply_auxiliary_plan(plan, session, tenant_id=1)
        session.commit()

        strategy = session.execute(select(Strategy).where(Strategy.code == "legacy_strategy")).scalar_one()
        setting = session.get(UiSetting, "dashboard_order")
        saved_filter = session.execute(select(SavedFilter)).scalar_one()
        operation_log = session.execute(select(OperationLog).limit(1)).scalar_one()
        pool = session.execute(select(StrategyPool)).scalar_one()
        backtest = session.execute(select(BacktestResult)).scalar_one()
        research_report = session.execute(select(ResearchReport)).scalar_one()

    assert first["strategies"]["inserted"] == 1
    assert first["ui_settings"]["inserted"] == 1
    assert first["saved_filters"]["inserted"] == 1
    assert first["operation_logs"]["inserted"] == 1
    assert first["operation_logs"]["existing"] == 1
    assert first["strategy_pools"]["inserted"] == 1
    assert first["backtest_results"]["inserted"] == 1
    assert first["research_reports"]["inserted"] == 1
    assert second["strategies"]["existing"] == 1
    assert second["ui_settings"]["updated"] == 1
    assert second["saved_filters"]["existing"] == 1
    assert second["operation_logs"]["existing"] == 2
    assert second["strategy_pools"]["existing"] == 1
    assert second["backtest_results"]["existing"] == 1
    assert second["research_reports"]["existing"] == 1

    assert strategy.name == "Legacy Strategy"
    assert strategy.is_active is True
    assert strategy.sort_order == 9
    assert setting.setting_value == "kpi,records"
    assert saved_filter.query_string == "status=active"
    assert operation_log.username == "admin"
    assert pool.code == "000001"
    assert float(pool.add_price) == 10.25
    assert backtest.total_trades == 3
    assert research_report.research_summary == "summary"
    assert float(research_report.total_score) == 88


def test_pick_migration_plan_reports_unresolved_strategy_without_mysql_lookup(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)

    plan = build_pick_migration_plan(db_path, tenant_id=1)

    assert plan.unresolved_strategy_count == 2
    assert any(issue.code == "unresolved_strategy" for issue in plan.issues)
    assert plan.planned_rows[0].target["strategy_id"] is None


def test_pick_migration_plan_dry_run_does_not_mutate_sqlite(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        before = conn.execute("SELECT COUNT(*) FROM picks").fetchone()[0]
    finally:
        conn.close()
    build_pick_migration_plan(db_path, tenant_id=1, strategy_id_by_code={"2560": 88})
    conn = sqlite3.connect(db_path)
    try:
        after = conn.execute("SELECT COUNT(*) FROM picks").fetchone()[0]
    finally:
        conn.close()

    assert after == before


def test_apply_pick_plan_inserts_once_and_skips_existing(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            Strategy(
                tenant_id=1,
                code="2560",
                name="2560",
                enabled=True,
                created_at=datetime(2026, 5, 1, 9, 0, 0),
                updated_at=datetime(2026, 5, 1, 9, 0, 0),
            )
        )
        session.commit()

        strategy_map = load_strategy_id_map(session, tenant_id=1)
        plan = build_pick_migration_plan(db_path, tenant_id=1, strategy_id_by_code=strategy_map)

        first_result = apply_pick_plan(plan, session)
        session.commit()
        second_result = apply_pick_plan(plan, session)
        session.commit()

        picks = session.execute(select(Pick)).scalars().all()

    assert first_result == {"inserted": 1, "existing": 0, "backfilled_existing": 0, "duplicates": 1}
    assert second_result == {"inserted": 0, "existing": 1, "backfilled_existing": 0, "duplicates": 1}
    assert len(picks) == 1
    assert picks[0].symbol == "000001"


def test_apply_gate_blocks_unresolved_strategy_by_default(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)

    plan = build_pick_migration_plan(db_path, tenant_id=1)
    blocked = validate_apply_gate(plan)
    allowed = validate_apply_gate(plan, allow_unresolved_strategies=True, allow_skipped_invalid=True)

    assert blocked.ok is False
    assert {issue.code for issue in blocked.blockers} == {"unresolved_strategy", "invalid_row", "skipped_invalid_rows"}
    assert allowed.ok is True
    assert {issue.code for issue in allowed.warnings} >= {"unresolved_strategy", "duplicate_key"}


def test_apply_gate_blocks_missing_target_tenant(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        plan = build_pick_migration_plan(db_path, tenant_id=1, strategy_id_by_code={"2560": 88})
        preconditions = load_target_preconditions(session, tenant_id=1, strategy_map={"2560": 88})
        gate = validate_apply_gate(plan, target_preconditions=preconditions)

    assert preconditions.ok is False
    assert gate.ok is False
    assert any(issue.code == "target_tenant_missing" for issue in gate.blockers)


def test_target_preconditions_pass_with_tenant_and_strategy_seed(tmp_path):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(Tenant(id=1, code="default", name="Default Tenant", status="active", plan="default"))
        session.add(
            Strategy(
                tenant_id=1,
                code="2560",
                name="2560",
                enabled=True,
                created_at=datetime(2026, 5, 1, 9, 0, 0),
                updated_at=datetime(2026, 5, 1, 9, 0, 0),
            )
        )
        session.commit()

        strategy_map = load_strategy_id_map(session, tenant_id=1)
        preconditions = load_target_preconditions(session, tenant_id=1, strategy_map=strategy_map)

    assert strategy_map["2560"] > 0
    assert preconditions.ok is True
    assert preconditions.tenant_exists is True


def test_reconcile_pick_plan_reports_missing_and_mismatched_rows(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        plan = build_pick_migration_plan(db_path, tenant_id=1, strategy_id_by_code={"2560": 88})

        missing = reconcile_pick_plan(plan, session)
        apply_pick_plan(plan, session)
        session.flush()
        ok = reconcile_pick_plan(plan, session)
        pick = session.execute(select(Pick)).scalar_one()
        pick.updated_at = datetime(2026, 5, 4, 12, 0, 0)
        session.flush()
        ignored_timestamp = reconcile_pick_plan(plan, session)
        pick.return_pct = 99
        session.flush()
        mismatched = reconcile_pick_plan(plan, session)

    assert missing.ok is False
    assert missing.missing_rows == 1
    assert ok.ok is True
    assert ok.matched_rows == 1
    assert ignored_timestamp.ok is True
    assert mismatched.ok is False
    assert mismatched.mismatch_rows == 1
    assert any(item.field == "return_pct" for item in mismatched.field_mismatches)


def test_apply_cli_requires_confirmation(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        ["migrate_sqlite_to_mysql.py", "--apply", "--json", "--confirm-apply", "wrong-token"],
    )

    exit_code = main()
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["error"] == "missing_apply_confirmation"
    assert APPLY_CONFIRMATION in output["detail"]


def test_sqlite_reader_rejects_unsafe_table_names(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)

    with pytest.raises(ValueError):
        read_sqlite_rows("picks; drop table picks", db_path)


def test_sqlite_counts_missing_tables_as_zero(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)

    counts = read_sqlite_counts(db_path, tables=("picks", "missing_table"))

    assert counts == {"picks": 4, "missing_table": 0}


def test_sqlite_file_fingerprint_is_stable_for_unchanged_source(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)

    first = sqlite_file_fingerprint(db_path)
    second = sqlite_file_fingerprint(db_path)

    assert first == second
    assert first["path"] == str(db_path)
    assert first["size_bytes"] > 0
    assert len(first["sha256"]) == 64
