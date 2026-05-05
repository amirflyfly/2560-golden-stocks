from __future__ import annotations

from datetime import datetime

import pandas as pd


def _limit_up_return_frame(signal: str = "pullback_setup") -> pd.DataFrame:
    dates = pd.bdate_range(end=datetime(2026, 5, 5), periods=32)
    rows = []
    close = 10.0
    for index, trade_date in enumerate(dates):
        if index < 20:
            close = 10.0
            row = {
                "date": trade_date.strftime("%Y-%m-%d"),
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 1000,
                "amount": close * 1000,
                "turnover": 1.0,
                "source": "unit",
            }
        elif index == 20:
            close = 11.0
            row = {
                "date": trade_date.strftime("%Y-%m-%d"),
                "open": 10.2,
                "high": 11.0,
                "low": 10.15,
                "close": 11.0,
                "volume": 3000,
                "amount": 11.0 * 3000,
                "turnover": 3.0,
                "source": "unit",
            }
        elif index < 31:
            close = 10.72 + (index - 21) * 0.015
            row = {
                "date": trade_date.strftime("%Y-%m-%d"),
                "open": close * 1.002,
                "high": close * 1.01,
                "low": min(10.58, close * 0.99),
                "close": close,
                "volume": 850,
                "amount": close * 850,
                "turnover": 1.0,
                "source": "unit",
            }
        else:
            if signal == "breakout_confirmed":
                close = 11.35
                volume = 1800
                low = 10.98
                high = 11.42
            elif signal == "failed_pullback":
                close = 9.60
                volume = 1700
                low = 9.55
                high = 10.05
            else:
                close = 10.88
                volume = 780
                low = 10.62
                high = 10.95
            row = {
                "date": trade_date.strftime("%Y-%m-%d"),
                "open": close * 0.995,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "amount": close * volume,
                "turnover": 1.2,
                "source": "unit",
            }
        rows.append(row)
    return pd.DataFrame(rows)


def test_limit_up_rule_infers_main_chinext_bj_and_st():
    from backend.strategies.strategy_limit_up_return import infer_limit_up_rule

    assert infer_limit_up_rule("000001", "Ping An", "sz", "stock").percent == 0.10
    assert infer_limit_up_rule("300001", "ChiNext", "sz", "stock").percent == 0.20
    assert infer_limit_up_rule("688001", "STAR", "sh", "stock").percent == 0.20
    assert infer_limit_up_rule("830001", "BSE", "bj", "stock").percent == 0.30
    st_rule = infer_limit_up_rule("600001", "*ST Test", "sh", "stock")
    assert st_rule.percent == 0.05
    unknown = infer_limit_up_rule("", "", "", "stock")
    assert unknown.confirmed is False
    assert "limit_rule_unconfirmed" in unknown.risk_flags


def test_limit_up_return_analyze_returns_pullback_setup(monkeypatch):
    from backend.strategies.strategy_limit_up_return import SIGNAL_SCHEMA_VERSION, StrategyLimitUpReturn

    strategy = StrategyLimitUpReturn()
    monkeypatch.setattr(strategy, "_get_hist", lambda *args, **kwargs: _limit_up_return_frame("pullback_setup"))

    matched, reason, payload = strategy._analyze_stock("000001", "Ping An", "sz", "2026-05-05")

    assert matched is True
    assert reason == "pullback_setup"
    assert payload["schema_version"] == SIGNAL_SCHEMA_VERSION
    assert payload["strategy_code"] == "LIMIT_UP_RETURN"
    assert payload["signal_subtype"] == "pullback_setup"
    assert payload["phase"]["LimitUpEvent"] is True
    assert payload["phase"]["PullbackValid"] is True
    assert payload["phase"]["SupportConfirmed"] is True
    assert payload["phase"]["ReAttackTrigger"] is False
    assert payload["indicators"]["limit_rule"]["percent"] == 0.10


def test_limit_up_return_analyze_returns_breakout_confirmed(monkeypatch):
    from backend.strategies.strategy_limit_up_return import StrategyLimitUpReturn

    strategy = StrategyLimitUpReturn()
    monkeypatch.setattr(strategy, "_get_hist", lambda *args, **kwargs: _limit_up_return_frame("breakout_confirmed"))

    matched, reason, payload = strategy._analyze_stock("000001", "Ping An", "sz", "2026-05-05")

    assert matched is True
    assert reason == "breakout_confirmed"
    assert payload["signal"] == "breakout_confirmed"
    assert payload["phase"]["ReAttackTrigger"] is True
    assert payload["indicators"]["limit_rule"]["percent"] == 0.10


def test_limit_up_return_analyze_returns_failed_pullback(monkeypatch):
    from backend.strategies.strategy_limit_up_return import StrategyLimitUpReturn

    strategy = StrategyLimitUpReturn()
    monkeypatch.setattr(strategy, "_get_hist", lambda *args, **kwargs: _limit_up_return_frame("failed_pullback"))

    matched, reason, payload = strategy._analyze_stock("000001", "Ping An", "sz", "2026-05-05")

    assert matched is True
    assert reason == "failed_pullback"
    assert payload["signal_type"] == "RISK"
    assert "support_broken" in payload["risk_flags"]


def test_limit_up_return_uses_stock_data_service_and_registers(monkeypatch):
    import backend.services.stock_data_service as stock_data_service
    from backend.strategies import registry
    from backend.strategies.strategy_limit_up_return import StrategyLimitUpReturn

    class StubStockDataService:
        def __init__(self):
            self.calls = []

        def get_stock_hist(self, symbol, start_date, end_date, adjust="qfq", interval="1d"):
            self.calls.append((symbol, start_date, end_date, adjust, interval))
            return _limit_up_return_frame("pullback_setup")

    service = StubStockDataService()
    monkeypatch.setattr(stock_data_service, "get_stock_data_service", lambda: service)

    strategy = StrategyLimitUpReturn()
    matched, _, _ = strategy._analyze_stock("000001", "Ping An", "sz", "2026-05-05", bar_interval="1d", adjust="qfq")

    assert matched is True
    assert service.calls
    assert service.calls[0][0] == "000001"
    assert service.calls[0][3:] == ("qfq", "1d")
    assert registry.get("LIMIT_UP_RETURN") is not None
