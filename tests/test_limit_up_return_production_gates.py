from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from backend import create_app
from backend.application import strategy_api_service
from backend.application.strategy_api_service import StrategyApiService
from backend.infrastructure.market_data.provider import DailyBar, QuoteSnapshot
from backend.repositories import market_data_repo, strategy_repo


@pytest.fixture
def app_db(tmp_path, monkeypatch):
    import backend.repositories.db as db_module

    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = tmp_path / "picks.db"
    monkeypatch.setenv("MARKET_DATA_REPOSITORY_BACKEND", "sqlite")
    monkeypatch.setenv("STRATEGY_REPOSITORY_BACKEND", "sqlite")
    monkeypatch.setenv("TRADING_REPOSITORY_BACKEND", "sqlite")
    create_app({"TESTING": True})
    try:
        yield
    finally:
        db_module.DB_PATH = original_db_path


def _seed_snapshot(symbol: str = "000001", *, source: str = "unit") -> None:
    market_data_repo.upsert_quote_snapshots(
        [
            QuoteSnapshot(
                symbol=symbol,
                trade_time=datetime(2026, 5, 5, 9, 30),
                last_price=Decimal("10"),
                open=Decimal("10"),
                high=Decimal("10.5"),
                low=Decimal("9.8"),
                prev_close=Decimal("9.5"),
                source=source,
            )
        ]
    )


def _seed_bar(symbol: str = "000001", *, adjust: str = "qfq", source: str = "unit") -> None:
    market_data_repo.upsert_daily_bars(
        [
            DailyBar(
                symbol=symbol,
                trade_date=date(2026, 5, 4),
                open=Decimal("9.5"),
                high=Decimal("10.5"),
                low=Decimal("9.4"),
                close=Decimal("10"),
                volume=1000,
                amount=Decimal("10000"),
                source=source,
            )
        ],
        adjust=adjust,
    )


def _limit_up_return_strategy_id() -> int:
    row = strategy_repo.get_strategy_by_code("LIMIT_UP_RETURN")
    assert row
    return int(row["id"])


def test_limit_up_return_blocks_when_raw_daily_history_is_missing(app_db):
    _seed_snapshot()
    _seed_bar(adjust="qfq")

    result = StrategyApiService().run_deployed_strategy(
        1,
        _limit_up_return_strategy_id(),
        {"sample_size": 5, "bar_interval": "1d", "adjust": "qfq", "paper_trade": False},
    )

    assert result["production_status"] == "blocked_no_raw_history"
    checks = {item["name"]: item for item in result["production_contract"]["strategy_requirements"]["checks"]}
    assert checks["qfq_history"]["passed"] is True
    assert checks["none_history"]["passed"] is False
    assert checks["limit_rule_calendar"]["passed"] is True


def test_production_run_rejects_mock_or_fallback_local_sources(app_db):
    _seed_snapshot(source="mock")
    _seed_bar(adjust="qfq", source="mock")

    strategy = strategy_repo.get_strategy_by_code("2560")
    assert strategy
    result = StrategyApiService().run_deployed_strategy(
        1,
        int(strategy["id"]),
        {"sample_size": 5, "bar_interval": "1d", "adjust": "qfq", "paper_trade": False},
    )

    assert result["production_status"] == "blocked_mock_fallback_source"
    assert result["production_contract"]["mock_or_fallback_blocked"] is True


def test_limit_up_return_requires_oos_backtest_before_production_paper(app_db, monkeypatch):
    class RuntimeStrategy:
        def scan(self, target_date=None):
            return []

    def fake_scan(self, tenant_id, strategy_code, params):
        return {"params": params, "market_data": {"sample_symbols": [{"symbol": "000001", "signal_subtype": "breakout_confirmed"}]}}

    monkeypatch.setattr(strategy_api_service.registry, "get", lambda code: RuntimeStrategy())
    monkeypatch.setattr("backend.application.scan_api_service.ScanApiService._run_scan", fake_scan)
    _seed_snapshot()
    _seed_bar(adjust="qfq")
    _seed_bar(adjust="none")

    result = StrategyApiService().run_deployed_strategy(
        1,
        _limit_up_return_strategy_id(),
        {"sample_size": 5, "bar_interval": "1d", "adjust": "qfq", "paper_trade": True},
    )

    assert result["production_status"] == "completed"
    assert result["paper_trading"]["enabled"] is False
    assert result["paper_trading"]["reason"] == "blocked_oos_backtest_required"
    assert result["paper_trading"]["live_trading"]["supported"] is False
