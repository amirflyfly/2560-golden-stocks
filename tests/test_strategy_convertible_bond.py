from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import os
import tempfile

import pytest

from backend.infrastructure.market_data.provider import DailyBar


@pytest.fixture
def temp_market_db(monkeypatch):
    import backend.repositories.db as db_module

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.ensure_schema()
    try:
        yield db_path
    finally:
        db_module.DB_PATH = original_db_path
        os.close(db_fd)
        os.unlink(db_path)


def _business_dates(start: str, end: str) -> list[date]:
    current = date.fromisoformat(start)
    stop = date.fromisoformat(end)
    items = []
    while current <= stop:
        if current.weekday() < 5:
            items.append(current)
        current += timedelta(days=1)
    return items


def _bar(symbol: str, trade_date: date, close: float, *, source: str = "unit", amount: float = 50_000_000) -> DailyBar:
    return DailyBar(
        symbol=symbol,
        trade_date=trade_date,
        trade_time=datetime.combine(trade_date, datetime.min.time()),
        interval="1d",
        open=Decimal(str(round(close * 0.998, 4))),
        high=Decimal(str(round(close * 1.01, 4))),
        low=Decimal(str(round(close * 0.99, 4))),
        close=Decimal(str(round(close, 4))),
        volume=100_000,
        amount=Decimal(str(round(amount, 2))),
        turnover_rate=Decimal("2.0"),
        source=source,
    )


def _seed_convertible_bond_market():
    from backend.repositories import market_data_repo

    dates = _business_dates("2026-03-16", "2026-05-05")
    bars = []
    for index, item in enumerate(dates):
        good_close = 108.0 + min(index, 35) * 0.25
        bars.append(_bar("123001", item, good_close, amount=55_000_000))
        bars.append(_bar("123002", item, 138.0, amount=80_000_000))
        bars.append(_bar("113001", item, 112.0, amount=60_000_000))
        bars.append(_bar("000001", item, 10.8 + min(index, 35) * 0.03, amount=100_000_000))
        bars.append(_bar("000002", item, 10.0, amount=90_000_000))

    market_data_repo.upsert_daily_bars([bar for bar in bars if bar.symbol.startswith(("000", "600"))], adjust="qfq")
    market_data_repo.upsert_daily_bars([bar for bar in bars if not bar.symbol.startswith(("000", "600"))], adjust="none")
    market_data_repo.upsert_stocks(
        [
            {"symbol": "000001", "name": "Underlying Good", "exchange": "SZ", "security_type": "stock"},
            {"symbol": "000002", "name": "Underlying Flat", "exchange": "SZ", "security_type": "stock"},
            {
                "symbol": "123001",
                "name": "Good CB",
                "exchange": "SZ",
                "security_type": "convertible_bond",
                "limit_rule_profile": {
                    "convertible_bond": {
                        "underlying_symbol": "000001",
                        "conversion_price": 10.0,
                        "remaining_size_yi": 5.0,
                        "redeem_status": "none",
                        "rating_status": "stable",
                    }
                },
            },
            {
                "symbol": "123002",
                "name": "High Premium CB",
                "exchange": "SZ",
                "security_type": "convertible_bond",
                "limit_rule_profile": {
                    "convertible_bond": {
                        "underlying_symbol": "000002",
                        "conversion_price": 10.0,
                        "remaining_size_yi": 8.0,
                        "redeem_status": "none",
                    }
                },
            },
            {
                "symbol": "113001",
                "name": "Redeem Risk CB",
                "exchange": "SH",
                "security_type": "convertible_bond",
                "limit_rule_profile": {
                    "convertible_bond": {
                        "underlying_symbol": "000001",
                        "conversion_price": 10.0,
                        "remaining_size_yi": 6.0,
                        "redeem_status": "announced",
                    }
                },
            },
        ]
    )


def test_convertible_bond_strategy_filters_and_scores_local_terms(temp_market_db):
    from backend.strategies.strategy_convertible_bond import ConvertibleBondLowPremiumStrategy, SIGNAL_SCHEMA_VERSION

    _seed_convertible_bond_market()

    strategy = ConvertibleBondLowPremiumStrategy()
    picks = strategy.scan("2026-05-05")

    assert [item["code"] for item in picks] == ["123001"]
    pick = picks[0]
    assert pick["schema_version"] == SIGNAL_SCHEMA_VERSION
    assert pick["security_type"] == "convertible_bond"
    assert pick["premium_rate"] <= strategy.params["max_entry_premium_rate"]
    assert pick["double_low"] <= strategy.params["max_double_low"]
    assert pick["remaining_size_yi"] >= strategy.params["min_remaining_size_yi"]
    assert pick["metadata"]["buy_model"]["max_entry_price"] == strategy.params["max_entry_price"]
    assert pick["metadata"]["sell_model"]["stop_loss_pct"] == strategy.params["stop_loss_pct"]
    assert pick["risk"]["event_flags"] == []


def test_convertible_bond_backtest_runs_through_service(temp_market_db, monkeypatch):
    from backend.application.backtest_api_service import BacktestApiService
    from backend.services.strategy_pool_service import run_backtest
    from backend.strategies import registry

    _seed_convertible_bond_market()
    monkeypatch.setenv("MARKET_DATA_LOCAL_ONLY", "1")

    assert registry.get("convertible_bond_low_premium")
    raw = run_backtest(
        "CONVERTIBLE_BOND_LOW_PREMIUM",
        "2026-04-20",
        "2026-05-05",
        holding_days=5,
        max_positions_per_day=1,
    )
    assert raw["success"] is True
    assert raw["results"]["total_trades"] > 0
    assert raw["results"]["execution_summary"]["allow_t0"] is True
    assert raw["results"]["trades"][0]["metadata"]["exit_reason"]

    response = BacktestApiService().run(
        1,
        "CONVERTIBLE_BOND_LOW_PREMIUM",
        {
            "start_date": "2026-04-20",
            "end_date": "2026-05-05",
            "holding_days": 5,
            "max_positions_per_day": 1,
            "security_type": "convertible_bond",
            "adjust": "none",
            "benchmark_return_pct": 0,
            "include_trades": True,
        },
    )
    summary = response["summary"]
    assert summary["total_trades"] > 0
    assert summary["data_contract"]["security_type"] == "convertible_bond"
    assert summary["data_contract"]["adjust"] == "none"
    assert summary["trade_page"]["items"][0]["code"] == "123001"
    assert summary["trade_page"]["items"][0]["metadata"]["exit_reason"]
