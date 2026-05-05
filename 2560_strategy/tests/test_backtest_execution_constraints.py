from backend.application.backtest_api_service import BacktestApiService


def _summary(raw_results):
    return BacktestApiService()._normalize_summary(
        {"results": raw_results},
        include_trades=True,
        trade_limit=20,
        request_options={"benchmark_return_pct": 0, "_provided_fields": ["benchmark_return_pct"]},
    )


def test_backtest_execution_constraints_expose_t1_limit_suspend_and_ratios():
    summary = _summary(
        {
            "trades": [
                {
                    "code": "000001",
                    "name": "Valid",
                    "signal_date": "2026-01-02",
                    "entry_date": "2026-01-05",
                    "exit_date": "2026-01-08",
                    "entry_price": 10,
                    "exit_price": 10.4,
                    "return_pct": 0.04,
                    "t_plus_one": True,
                },
                {
                    "code": "000002",
                    "name": "Limit Up",
                    "signal_date": "2026-01-02",
                    "entry_date": "2026-01-05",
                    "entry_price": 8,
                    "exit_price": 8.8,
                    "return_pct": 0.1,
                    "entry_limit_up": True,
                },
                {
                    "code": "000003",
                    "name": "Limit Down",
                    "signal_date": "2026-01-02",
                    "entry_date": "2026-01-05",
                    "entry_price": 7,
                    "exit_price": 6.3,
                    "return_pct": -0.1,
                    "exit_limit_down": True,
                },
            ],
            "skipped_trades": [
                {
                    "code": "000004",
                    "name": "Suspended",
                    "signal_date": "2026-01-02",
                    "intended_entry_date": "2026-01-05",
                    "reason": "suspended",
                    "action": "suspended_trade",
                }
            ],
        }
    )

    constraints = summary["execution_constraints"]

    assert summary["total_trades"] == 1
    assert summary["raw_trade_count"] == 3
    assert summary["skipped_trade_count"] == 1
    assert constraints["candidate_count"] == 4
    assert constraints["included_count"] == 1
    assert constraints["excluded_count"] == 3
    assert constraints["skipped_count"] == 3
    assert constraints["excluded_ratio"] == 0.75
    assert constraints["skipped_ratio"] == 0.75
    assert constraints["reasons"]["limit_up"] == 1
    assert constraints["reasons"]["limit_down"] == 1
    assert constraints["reasons"]["suspended"] == 1
    assert constraints["blocked_actions"]["limit_up_buy"] == 1
    assert constraints["blocked_actions"]["limit_down_sell"] == 1
    assert constraints["blocked_actions"]["suspended_trade"] == 1
    assert constraints["t_plus_one"]["mode"] == "next_trading_day_entry"
    assert constraints["t_plus_one"]["executed_count"] == 4


def test_backtest_factor_attribution_aggregates_trade_metadata_dimensions():
    summary = _summary(
        {
            "trades": [
                {
                    "code": "000001",
                    "entry_price": 10,
                    "exit_price": 10.5,
                    "return_pct": 0.05,
                    "metadata": {
                        "pullback_days": 3,
                        "volume_shrink_ratio": 0.62,
                        "drawdown_depth": 0.06,
                        "market_sentiment": "warm",
                    },
                },
                {
                    "code": "000002",
                    "entry_price": 10,
                    "exit_price": 9.8,
                    "return_pct": -0.02,
                    "phase": {"pullback_days": 3},
                    "indicators": {"volume_shrink_ratio": 0.7, "drawdown_depth": 0.1},
                    "risk": {"market_sentiment": "warm"},
                },
                {
                    "code": "000003",
                    "entry_price": 10,
                    "exit_price": 10.2,
                    "return_pct": 0.02,
                    "pullback_days": 6,
                    "vol_ratio": 0.92,
                    "dist25": 0.02,
                    "sentiment": "cold",
                },
            ]
        }
    )

    attribution = summary["factor_attribution"]
    pullback = {item["bucket"]: item for item in attribution["pullback_days"]["items"]}
    shrink = {item["bucket"]: item for item in attribution["volume_shrink_ratio"]["items"]}
    drawdown = {item["bucket"]: item for item in attribution["drawdown_depth"]["items"]}
    sentiment = {item["bucket"]: item for item in attribution["market_sentiment"]["items"]}

    assert attribution["schema_version"] == "backtest-attribution/v1"
    assert pullback["3"]["trade_count"] == 2
    assert pullback["3"]["win_rate"] == 0.5
    assert pullback["3"]["avg_return"] == 0.015
    assert pullback["6"]["trade_count"] == 1
    assert shrink["0.50-0.80"]["trade_count"] == 2
    assert shrink["0.80-1.00"]["trade_count"] == 1
    assert drawdown["3%-8%"]["trade_count"] == 1
    assert drawdown["8%-15%"]["trade_count"] == 1
    assert drawdown["<=3%"]["trade_count"] == 1
    assert sentiment["warm"]["trade_count"] == 2
    assert sentiment["cold"]["trade_count"] == 1
    assert summary["trade_page"]["items"][0]["pullback_days"] == 3
