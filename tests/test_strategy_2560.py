from __future__ import annotations

from datetime import datetime

import pandas as pd


def _sample_2560_frame(rows: int = 90) -> pd.DataFrame:
    dates = pd.bdate_range(end=datetime(2026, 5, 5), periods=rows)
    data = []
    for index, trade_date in enumerate(dates):
        close = 10 + index * 0.01
        volume = 1000
        if index >= rows - 20:
            volume = 1400
        data.append(
            {
                "date": trade_date.strftime("%Y-%m-%d"),
                "open": close * 0.995,
                "high": close * 1.015,
                "low": close * 0.99,
                "close": close,
                "volume": volume,
                "amount": close * volume * 100,
                "turnover": 1.2,
                "source": "unit",
            }
        )
    return pd.DataFrame(data)


def test_2560_indicators_include_ma60_and_volume_phase_inputs():
    from backend.strategies.strategy_2560 import Strategy2560

    strategy = Strategy2560()
    indicators = strategy._calculate_indicators(_sample_2560_frame())
    last = indicators.iloc[-1]

    assert last["ma25"] > 0
    assert last["ma60"] > 0
    assert last["ma5_vol"] == last["mavol5"]
    assert last["ma60_vol"] == last["mavol60"]
    assert last["vol_ratio"] == last["vr5_60"]
    assert last["ma25_slope_5"] > 0
    assert last["high20"] > 0


def test_2560_analyze_stock_returns_strategy_signal_contract(monkeypatch):
    from backend.strategies.strategy_2560 import SIGNAL_SCHEMA_VERSION, Strategy2560

    strategy = Strategy2560()
    monkeypatch.setitem(strategy.config["strategy"], "price_limit", 0)
    monkeypatch.setitem(strategy.config["strategy"], "min_score", 40)
    monkeypatch.setattr(strategy, "_get_hist", lambda *args, **kwargs: _sample_2560_frame())

    matched, reason, payload = strategy._analyze_stock(
        "000001",
        "平安银行",
        "sz",
        "2026-05-05",
        security_type="stock",
        bar_interval="1d",
        adjust="qfq",
    )

    assert matched is True
    assert reason in {"缩量回踩", "做量蓄势", "温和突破", "冲量启动", "放量突破"}
    assert payload["schema_version"] == SIGNAL_SCHEMA_VERSION
    assert payload["strategy_code"] == "2560"
    assert payload["code"] == "000001"
    assert payload["security_type"] == "stock"
    assert payload["bar_interval"] == "1d"
    assert payload["adjust"] == "qfq"
    assert payload["score"] == payload["total_score"]
    assert payload["signal_subtype"]
    assert payload["volume_phase"]
    assert payload["ma60"] > 0
    assert payload["indicators"]["ma60"] == payload["ma60"]
    assert payload["phase"]["volume_phase"] == payload["volume_phase"]
    assert payload["risk"]["risk_score"] == payload["risk_score"]
    assert payload["data"]["bar_count"] >= 65
    assert payload["note"]


def test_2560_scan_results_feed_scan_explanation(monkeypatch):
    from backend.application.scan_api_service import ScanApiService
    from backend.strategies.strategy_2560 import Strategy2560

    strategy = Strategy2560()
    monkeypatch.setitem(strategy.config["strategy"], "price_limit", 0)
    monkeypatch.setitem(strategy.config["strategy"], "min_score", 40)
    monkeypatch.setattr(strategy, "_get_hist", lambda *args, **kwargs: _sample_2560_frame())
    matched, _, payload = strategy._analyze_stock("000001", "平安银行", "sz", "2026-05-05")
    assert matched is True

    service = ScanApiService()
    normalized = service._normalize_strategy_pick(
        payload,
        {"actual_provider": "local", "provider_chain": ["local"], "fallback_used": False, "data_quality": "primary"},
        "2560",
        {"bar_interval": "1d", "adjust": "qfq", "security_type": "stock"},
    )

    assert normalized["ma60"] > 0
    assert normalized["volume_phase"] == payload["volume_phase"]
    assert normalized["signal_subtype"] == payload["signal_subtype"]
    assert normalized["explanation"]["indicators"]["ma60"] == payload["ma60"]
    assert normalized["explanation"]["indicator_groups"]["technical"]["volume_phase"] == payload["volume_phase"]


def test_stock_data_service_passes_bar_interval_to_local_source(tmp_path):
    from backend.services.stock_data_service import StockDataService

    class LocalSource:
        name = "local-test"

        def __init__(self):
            self.calls = []

        def get_stock_list(self):
            return pd.DataFrame()

        def get_stock_hist(self, symbol, start_date, end_date, adjust="qfq", interval="1d"):
            self.calls.append((symbol, start_date, end_date, adjust, interval))
            return pd.DataFrame(
                [
                    {
                        "date": "2026-05-05",
                        "open": 10,
                        "high": 11,
                        "low": 9,
                        "close": 10.5,
                        "volume": 1000,
                        "interval": interval,
                    }
                ]
            )

        def get_trading_dates(self, start_date, end_date):
            return []

    service = StockDataService(cache_dir=str(tmp_path))
    local_source = LocalSource()
    service.data_sources["local"] = local_source

    df = service.get_stock_hist("123001", "2026-05-05", "2026-05-05", adjust="none", interval="15m")

    assert local_source.calls == [("123001", "2026-05-05", "2026-05-05", "none", "15m")]
    assert df.iloc[0]["interval"] == "15m"


def test_stock_data_service_local_only_prevents_external_history_fallback(tmp_path, monkeypatch):
    from backend.services.stock_data_service import StockDataService

    class EmptyLocalSource:
        name = "local-empty"

        def get_stock_list(self):
            return pd.DataFrame()

        def get_stock_hist(self, symbol, start_date, end_date, adjust="qfq", interval="1d"):
            return pd.DataFrame()

        def get_trading_dates(self, start_date, end_date):
            return []

    class ExternalSource:
        name = "external"

        def __init__(self):
            self.calls = []

        def get_stock_list(self):
            return pd.DataFrame([{"code": "000001", "name": "Ping An"}])

        def get_stock_hist(self, symbol, start_date, end_date, adjust="qfq", interval="1d"):
            self.calls.append((symbol, start_date, end_date, adjust, interval))
            return pd.DataFrame([{"date": "2026-05-05", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}])

        def get_trading_dates(self, start_date, end_date):
            return ["2026-05-05"]

    service = StockDataService(cache_dir=str(tmp_path))
    external_source = ExternalSource()
    service.data_sources["local"] = EmptyLocalSource()
    service.data_sources["akshare"] = external_source
    monkeypatch.setenv("MARKET_DATA_LOCAL_ONLY", "1")

    df = service.get_stock_hist("000001", "2026-05-05", "2026-05-05", adjust="qfq", interval="1d")

    assert df.empty
    assert external_source.calls == []


def test_backtest_summary_groups_returns_by_2560_signal_subtype():
    from backend.application.backtest_api_service import BacktestApiService

    summary = BacktestApiService()._normalize_summary(
        {
            "results": {
                "trades": [
                    {"code": "000001", "signal": "缩量回踩", "signal_subtype": "volume_lock_shrink", "volume_phase": "lock_shrink", "return_pct": 0.05, "entry_price": 10, "exit_price": 10.5},
                    {"code": "000002", "signal": "缩量回踩", "signal_subtype": "volume_lock_shrink", "volume_phase": "lock_shrink", "return_pct": -0.02, "entry_price": 10, "exit_price": 9.8},
                    {"code": "000003", "signal": "放量突破", "signal_subtype": "breakout_volume", "volume_phase": "breakout_expand", "return_pct": 0.03, "entry_price": 10, "exit_price": 10.3},
                ]
            }
        },
        include_trades=True,
        trade_limit=10,
        request_options={"benchmark_return_pct": 0, "_provided_fields": ["benchmark_return_pct"]},
    )

    items = {item["signal_subtype"]: item for item in summary["signal_attribution"]["items"]}
    assert summary["signal_attribution"]["schema_version"] == "signal-attribution/v1"
    assert items["volume_lock_shrink"]["trade_count"] == 2
    assert items["volume_lock_shrink"]["win_rate"] == 0.5
    assert items["volume_lock_shrink"]["volume_phases"] == {"lock_shrink": 2}
    assert items["breakout_volume"]["trade_count"] == 1
    assert summary["trade_page"]["items"][0]["signal_subtype"] == "volume_lock_shrink"
    holding_days = {item["holding_days"]: item for item in summary["holding_day_distribution"]["items"]}
    assert summary["holding_day_distribution"]["schema_version"] == "holding-day-distribution/v1"
    assert holding_days[0]["trade_count"] == 3
    assert holding_days[0]["win_rate"] == 0.666667
    assert holding_days[0]["avg_return"] == 0.02
