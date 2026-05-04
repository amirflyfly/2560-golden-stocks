import os
import tempfile

import pytest


V1_PICK_TARGET_COLUMNS = {
    "source_channel",
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
}


def test_sqlite_picks_schema_covers_v1_contract_fields():
    import backend.repositories.db as db_module

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = db_path
    try:
        db_module.ensure_schema()
        columns = {row["name"] for row in db_module.q("PRAGMA table_info(picks)")}
    finally:
        db_module.DB_PATH = original_db_path
        os.close(db_fd)
        os.unlink(db_path)

    required_columns = {
        "id",
        "code",
        "name",
        "pick_date",
        "source",
        "source_channel",
        "strategy_name",
        "review_status",
        "review_comment",
        "result_grade",
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
        "archived",
    }
    assert required_columns <= columns


def test_sqlite_picks_schema_documents_missing_tenant_boundary():
    import backend.repositories.db as db_module

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = db_path
    try:
        db_module.ensure_schema()
        columns = {row["name"] for row in db_module.q("PRAGMA table_info(picks)")}
    finally:
        db_module.DB_PATH = original_db_path
        os.close(db_fd)
        os.unlink(db_path)

    assert "tenant_id" not in columns


def test_sqlite_settings_schema_covers_legacy_contract():
    import backend.repositories.db as db_module

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = db_path
    try:
        db_module.ensure_schema()
        saved_filter_columns = {row["name"] for row in db_module.q("PRAGMA table_info(saved_filters)")}
        ui_setting_columns = {row["name"] for row in db_module.q("PRAGMA table_info(ui_settings)")}
    finally:
        db_module.DB_PATH = original_db_path
        os.close(db_fd)
        os.unlink(db_path)

    assert {"id", "name", "query_string", "created_at"} <= saved_filter_columns
    assert {"setting_key", "setting_value", "updated_at"} <= ui_setting_columns


def test_sqlite_operation_logs_schema_covers_legacy_contract():
    import backend.repositories.db as db_module

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = db_path
    try:
        db_module.ensure_schema()
        columns = {row["name"] for row in db_module.q("PRAGMA table_info(operation_logs)")}
    finally:
        db_module.DB_PATH = original_db_path
        os.close(db_fd)
        os.unlink(db_path)

    assert {"id", "action", "target_ids", "detail", "user_id", "username", "ip", "user_agent", "created_at"} <= columns


def test_sqlite_strategy_pool_schema_covers_legacy_contract():
    import backend.repositories.db as db_module

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = db_path
    try:
        db_module.ensure_schema()
        pool_columns = {row["name"] for row in db_module.q("PRAGMA table_info(strategy_pools)")}
        backtest_columns = {row["name"] for row in db_module.q("PRAGMA table_info(backtest_results)")}
    finally:
        db_module.DB_PATH = original_db_path
        os.close(db_fd)
        os.unlink(db_path)

    assert {"id", "strategy_code", "code", "name", "add_date", "add_price", "reason", "status", "created_at"} <= pool_columns
    assert {
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
    } <= backtest_columns


def test_sqlite_research_reports_schema_covers_legacy_contract():
    import backend.repositories.db as db_module

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = db_path
    try:
        db_module.ensure_schema()
        columns = {row["name"] for row in db_module.q("PRAGMA table_info(research_reports)")}
    finally:
        db_module.DB_PATH = original_db_path
        os.close(db_fd)
        os.unlink(db_path)

    assert {
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
    } <= columns


def test_sqlite_strategy_schema_covers_legacy_management_contract():
    import backend.repositories.db as db_module

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = db_path
    try:
        db_module.ensure_schema()
        columns = {row["name"] for row in db_module.q("PRAGMA table_info(strategies)")}
    finally:
        db_module.DB_PATH = original_db_path
        os.close(db_fd)
        os.unlink(db_path)

    assert {"id", "code", "name", "category", "description", "is_active", "sort_order", "created_at", "updated_at"} <= columns


def test_sqlalchemy_pick_model_gap_to_v1_contract_is_explicit():
    from backend.db.models.strategy import Pick

    model_columns = {column.name for column in Pick.__table__.columns}
    missing_columns = V1_PICK_TARGET_COLUMNS - model_columns

    assert "tenant_id" in model_columns
    assert missing_columns == set()


def test_sqlalchemy_settings_models_cover_legacy_contract():
    from backend.db.models import SavedFilter, UiSetting

    saved_filter_columns = {column.name for column in SavedFilter.__table__.columns}
    ui_setting_columns = {column.name for column in UiSetting.__table__.columns}

    assert {"id", "name", "query_string", "created_at"} <= saved_filter_columns
    assert {"setting_key", "setting_value", "updated_at"} <= ui_setting_columns


def test_sqlalchemy_operation_log_model_covers_legacy_contract():
    from backend.db.models import OperationLog

    columns = {column.name for column in OperationLog.__table__.columns}

    assert {"id", "action", "target_ids", "detail", "user_id", "username", "ip", "user_agent", "created_at"} <= columns


def test_sqlalchemy_strategy_pool_models_cover_legacy_contract():
    from backend.db.models import BacktestResult, StrategyPool

    pool_columns = {column.name for column in StrategyPool.__table__.columns}
    backtest_columns = {column.name for column in BacktestResult.__table__.columns}

    assert {"id", "strategy_code", "code", "name", "add_date", "add_price", "reason", "status", "created_at"} <= pool_columns
    assert {
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
    } <= backtest_columns


def test_sqlalchemy_research_report_model_covers_legacy_contract():
    from backend.db.models import ResearchReport

    columns = {column.name for column in ResearchReport.__table__.columns}

    assert {"pick_id", "code", "pick_date", "analysis_date", "technical_score", "total_score", "research_summary"} <= columns


def test_sqlalchemy_strategy_model_covers_legacy_management_contract():
    from backend.db.models import Strategy

    columns = {column.name for column in Strategy.__table__.columns}

    assert {"id", "tenant_id", "code", "name", "category", "description", "enabled", "is_active", "sort_order"} <= columns


def test_alembic_mysql_picks_gap_to_v1_contract_is_explicit():
    from pathlib import Path

    migration_source = "\n".join(path.read_text(encoding="utf-8") for path in Path("alembic/versions").glob("*.py"))
    missing_columns = {column for column in V1_PICK_TARGET_COLUMNS if f'"{column}"' not in migration_source}

    assert '"tenant_id"' in migration_source
    assert missing_columns == set()


def test_alembic_mysql_settings_contract_is_explicit():
    from pathlib import Path

    migration_source = "\n".join(path.read_text(encoding="utf-8") for path in Path("alembic/versions").glob("*.py"))

    for table_name in ("saved_filters", "ui_settings"):
        assert f'"{table_name}"' in migration_source
    for column_name in ("name", "query_string", "created_at", "setting_key", "setting_value", "updated_at"):
        assert f'"{column_name}"' in migration_source


def test_alembic_mysql_operation_logs_contract_is_explicit():
    from pathlib import Path

    migration_source = "\n".join(path.read_text(encoding="utf-8") for path in Path("alembic/versions").glob("*.py"))

    assert '"operation_logs"' in migration_source
    for column_name in ("action", "target_ids", "detail", "user_id", "username", "ip", "user_agent", "created_at"):
        assert f'"{column_name}"' in migration_source


def test_alembic_mysql_strategy_pool_contract_is_explicit():
    from pathlib import Path

    migration_source = "\n".join(path.read_text(encoding="utf-8") for path in Path("alembic/versions").glob("*.py"))

    for table_name in ("strategy_pools", "backtest_results"):
        assert f'"{table_name}"' in migration_source
    for column_name in (
        "strategy_code",
        "code",
        "name",
        "add_date",
        "add_price",
        "reason",
        "status",
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
    ):
        assert f'"{column_name}"' in migration_source


def test_alembic_mysql_research_reports_contract_is_explicit():
    from pathlib import Path

    migration_source = "\n".join(path.read_text(encoding="utf-8") for path in Path("alembic/versions").glob("*.py"))

    assert '"research_reports"' in migration_source
    for column_name in ("pick_id", "analysis_date", "technical_score", "total_score", "research_summary"):
        assert f'"{column_name}"' in migration_source


def test_alembic_mysql_strategy_legacy_management_contract_is_explicit():
    from pathlib import Path

    migration_source = "\n".join(path.read_text(encoding="utf-8") for path in Path("alembic/versions").glob("*.py"))

    assert '"strategies"' in migration_source
    assert '"is_active"' in migration_source
    assert '"sort_order"' in migration_source


def test_mysql_schema_validator_requires_picks_v1_contract():
    from scripts.validate_mysql_schema import (
        EXPECTED_ALEMBIC_REVISION,
        EXPECTED_COLUMNS,
        EXPECTED_UNIQUE_CONSTRAINTS,
    )

    assert EXPECTED_ALEMBIC_REVISION == "0011_user_engagement_fields"
    assert {"points", "last_checkin"} <= EXPECTED_COLUMNS["users"]
    assert V1_PICK_TARGET_COLUMNS <= EXPECTED_COLUMNS["picks"]
    assert "tenant_id" in EXPECTED_COLUMNS["picks"]
    assert {"id", "name", "query_string", "created_at"} <= EXPECTED_COLUMNS["saved_filters"]
    assert {"setting_key", "setting_value", "updated_at"} <= EXPECTED_COLUMNS["ui_settings"]
    assert {"id", "action", "target_ids", "detail", "user_id", "username", "ip", "user_agent", "created_at"} <= EXPECTED_COLUMNS["operation_logs"]
    assert {"strategy_code", "code", "name", "add_date", "add_price", "reason", "status"} <= EXPECTED_COLUMNS["strategy_pools"]
    assert {"strategy_code", "start_date", "end_date", "total_trades", "win_rate", "avg_return", "max_return", "max_drawdown", "sharpe_ratio", "total_return"} <= EXPECTED_COLUMNS["backtest_results"]
    assert {"pick_id", "analysis_date", "technical_score", "total_score", "research_summary"} <= EXPECTED_COLUMNS["research_reports"]
    assert {"code", "name", "category", "description", "enabled", "is_active", "sort_order"} <= EXPECTED_COLUMNS["strategies"]
    assert "uk_picks_tenant_date_symbol_source" in EXPECTED_UNIQUE_CONSTRAINTS["picks"]
    assert "uk_strategy_pools_strategy_code" in EXPECTED_UNIQUE_CONSTRAINTS["strategy_pools"]
    assert "uk_research_reports_pick_analysis" in EXPECTED_UNIQUE_CONSTRAINTS["research_reports"]


def test_mysql_research_reports_path_fails_closed_when_schema_is_missing(monkeypatch):
    from contextlib import contextmanager

    from backend.repositories import picks_repo

    @contextmanager
    def broken_session_scope():
        raise RuntimeError("missing table")
        yield

    monkeypatch.setattr(picks_repo, "_MYSQL_RESEARCH_REPORTS_SUPPORTED", None)
    monkeypatch.setattr(picks_repo, "session_scope", broken_session_scope)

    with pytest.raises(RuntimeError, match="research_reports table is required"):
        picks_repo._mysql_research_reports_supported()

    with pytest.raises(RuntimeError, match="research_reports table is required"):
        picks_repo._mysql_research_reports_supported()


class _FakeInspector:
    def __init__(self, *, tables=None, indexes=None, columns=None, unique_constraints=None):
        self._tables = set(tables or [])
        self._indexes = indexes or {}
        self._columns = columns or {}
        self._unique_constraints = unique_constraints or {}

    def get_table_names(self):
        return sorted(self._tables)

    def get_indexes(self, table):
        return [{"name": name} for name in self._indexes.get(table, set())]

    def get_columns(self, table):
        return [{"name": name} for name in self._columns.get(table, set())]

    def get_unique_constraints(self, table):
        return [{"name": name} for name in self._unique_constraints.get(table, set())]


class _FakeScalar:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class _FakeRows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _FakeConnection:
    def __init__(self, version, *, tenant_id=1, strategy_codes=None):
        self.version = version
        self.tenant_id = tenant_id
        self.strategy_codes = strategy_codes or {"2560", "first_limit_up"}

    def execute(self, statement, _params=None):
        sql = str(statement)
        if "FROM tenants" in sql:
            return _FakeScalar(self.tenant_id)
        if "FROM strategies" in sql:
            return _FakeRows([(code,) for code in self.strategy_codes])
        return _FakeScalar(self.version)


def test_mysql_schema_validator_reports_missing_contract_parts():
    from scripts.validate_mysql_schema import (
        EXPECTED_ALEMBIC_REVISION,
        EXPECTED_COLUMNS,
        EXPECTED_INDEXES,
        EXPECTED_STRATEGY_CODES,
        EXPECTED_TABLES,
        EXPECTED_UNIQUE_CONSTRAINTS,
        check_columns,
        check_indexes,
        check_seed_data,
        check_tables,
        check_unique_constraints,
        check_version,
    )

    ok_inspector = _FakeInspector(
        tables=EXPECTED_TABLES,
        indexes=EXPECTED_INDEXES,
        columns=EXPECTED_COLUMNS,
        unique_constraints=EXPECTED_UNIQUE_CONSTRAINTS,
    )
    assert check_tables(ok_inspector).ok is True
    assert check_indexes(ok_inspector).ok is True
    assert check_columns(ok_inspector).ok is True
    assert check_unique_constraints(ok_inspector).ok is True
    assert check_version(_FakeConnection(EXPECTED_ALEMBIC_REVISION)).ok is True
    assert check_seed_data(_FakeConnection(EXPECTED_ALEMBIC_REVISION)).ok is True

    assert check_tables(_FakeInspector(tables={"picks"})).ok is False
    assert check_indexes(_FakeInspector(indexes={"picks": set()})).ok is False
    assert check_columns(_FakeInspector(columns={"picks": {"tenant_id"}})).ok is False
    assert check_unique_constraints(_FakeInspector(unique_constraints={"picks": set()})).ok is False
    assert check_version(_FakeConnection("0001_initial_mysql_schema")).ok is False
    assert check_seed_data(_FakeConnection(EXPECTED_ALEMBIC_REVISION, tenant_id=None)).ok is False
    assert check_seed_data(
        _FakeConnection(EXPECTED_ALEMBIC_REVISION, strategy_codes=EXPECTED_STRATEGY_CODES - {"2560"})
    ).ok is False
