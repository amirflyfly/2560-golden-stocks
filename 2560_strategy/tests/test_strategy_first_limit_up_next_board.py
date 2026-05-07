from __future__ import annotations

from datetime import datetime

import pandas as pd


def _first_limit_frame(rows: int = 42) -> pd.DataFrame:
    dates = pd.bdate_range(end=datetime(2026, 5, 5), periods=rows)
    data = []
    for index, trade_date in enumerate(dates):
        if index == rows - 2:
            close = 10.0
            row = {
                "date": trade_date.strftime("%Y-%m-%d"),
                "open": 9.95,
                "high": 10.08,
                "low": 9.90,
                "close": close,
                "volume": 2800,
                "amount": 30_000_000,
                "turnover": 4.0,
                "source": "unit",
            }
        elif index == rows - 1:
            row = {
                "date": trade_date.strftime("%Y-%m-%d"),
                "open": 10.35,
                "high": 11.00,
                "low": 10.20,
                "close": 11.00,
                "volume": 6500,
                "amount": 95_000_000,
                "turnover": 8.0,
                "source": "unit",
            }
        else:
            close = 9.60 + index * 0.01
            row = {
                "date": trade_date.strftime("%Y-%m-%d"),
                "open": close * 0.998,
                "high": close * 1.012,
                "low": close * 0.990,
                "close": close,
                "volume": 2200 + index * 10,
                "amount": 28_000_000 + index * 100_000,
                "turnover": 3.5,
                "source": "unit",
            }
        data.append(row)
    return pd.DataFrame(data)


def _strategy(monkeypatch, snapshot=None):
    from backend.strategies.strategy_first_limit_up import StrategyFirstLimitUp

    strategy = StrategyFirstLimitUp()
    strategy.config["min_amount"] = 0
    strategy.config["exclude_bj"] = False
    monkeypatch.setattr(strategy, "_get_hist", lambda *args, **kwargs: _first_limit_frame())
    monkeypatch.setattr(strategy, "_get_auction_snapshot", lambda symbol: None)
    monkeypatch.setattr(strategy, "_get_snapshot", lambda symbol: snapshot)
    return strategy


def test_first_limit_up_preselect_returns_observation_payload(monkeypatch):
    from backend.strategies.strategy_first_limit_up import SIGNAL_SCHEMA_VERSION

    strategy = _strategy(monkeypatch, snapshot=None)

    matched, reason, payload = strategy._analyze_stock("000001", "Ping An", "SZ", "2026-05-05")

    assert matched is True
    assert reason == "preopen_watch"
    assert payload["schema_version"] == SIGNAL_SCHEMA_VERSION
    assert payload["strategy_code"] == "FIRST_LIMIT_UP"
    assert payload["signal_subtype"] == "preopen_watch"
    assert payload["second_board_expectation"] == "watch_only"
    assert payload["preselect_score"] >= 70
    assert payload["auction_score"] is None
    assert "auction_pending" in payload["risk_flags"]
    assert payload["indicators"]["first_limit_up"]["limit_up_price"] == 11.0
    assert payload["recommend_reason"]


def test_first_limit_up_auction_confirmation_becomes_entry_signal(monkeypatch):
    strategy = _strategy(
        monkeypatch,
        snapshot={
            "symbol": "000001",
            "trade_time": "2026-05-06T09:25:00",
            "prev_close": 11.0,
            "open": 11.42,
            "last_price": 11.46,
            "volume": 260,
            "amount": 3_600_000,
            "source": "unit",
        },
    )

    matched, reason, payload = strategy._analyze_stock("000001", "Ping An", "SZ", "2026-05-05")

    assert matched is True
    assert reason == "auction_confirmed"
    assert payload["signal_type"] == "BUY"
    assert payload["signal_subtype"] == "auction_confirmed"
    assert payload["auction_score"] >= 70
    assert payload["second_board_expectation"] == "confirmed_entry"
    assert payload["phase"]["AuctionConfirmation"] is True
    assert payload["indicators"]["auction"]["amount_ratio_to_limit_day"] > 0.03


def test_first_limit_up_prefers_auction_model_over_open_snapshot(monkeypatch):
    strategy = _strategy(
        monkeypatch,
        snapshot={
            "symbol": "000001",
            "trade_time": "2026-05-06T09:25:00",
            "prev_close": 11.0,
            "open": 12.05,
            "last_price": 12.04,
            "volume": 50,
            "amount": 700_000,
            "source": "unit_snapshot",
        },
    )
    monkeypatch.setattr(
        strategy,
        "_get_auction_snapshot",
        lambda symbol: {
            "symbol": symbol,
            "trade_date": "2026-05-06",
            "auction_time": "2026-05-06T09:25:00",
            "phase": "call_auction_0920_0925",
            "prev_close": 11.0,
            "indicative_price": 11.42,
            "matched_volume": 280,
            "matched_amount": 3_900_000,
            "unmatched_buy_volume": 900,
            "unmatched_sell_volume": 120,
            "withdrawal_buy_volume": 40,
            "withdrawal_sell_volume": 20,
            "seal_side": "buy",
            "seal_volume": 600,
            "seal_amount": 6_800_000,
            "source": "unit_auction",
        },
    )

    matched, reason, payload = strategy._analyze_stock("000001", "Ping An", "SZ", "2026-05-05")

    assert matched is True
    assert reason == "auction_confirmed"
    assert payload["indicators"]["auction"]["auction_data_source"] == "auction_model"
    assert payload["indicators"]["auction"]["order_book_imbalance"] > 0
    assert payload["data"]["auction_snapshot"]["source"] == "unit_auction"


def test_first_limit_up_registered_by_builtin_registry():
    from backend.strategies import registry

    assert registry.get("FIRST_LIMIT_UP") is not None
    assert registry.get("first_limit_up") is registry.get("FIRST_LIMIT_UP")
