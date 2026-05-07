from __future__ import annotations

from decimal import Decimal


def _scan(candidates: list[dict]) -> dict:
    return {"market_data": {"sample_symbols": candidates}}


def _install_repo(monkeypatch, *, snapshots: dict[str, dict | None] | None = None, positions: list[dict] | None = None):
    from backend.application import paper_trading_service as module

    orders: list[dict] = []
    signals: list[dict] = []
    account = {"id": 7, "tenant_id": 1, "cash": 100000.0, "initial_cash": 100000.0}
    snapshots = snapshots or {}
    positions = positions or []

    monkeypatch.setattr(module.paper_trading_repo, "ensure_default_account", lambda *args, **kwargs: account)
    monkeypatch.setattr(module.paper_trading_repo, "get_account", lambda account_id: account)
    monkeypatch.setattr(
        module.paper_trading_repo,
        "summary",
        lambda tenant_id, account_id=None: {"tenant_id": tenant_id, "active_positions": len(positions), "cash": account["cash"]},
    )
    monkeypatch.setattr(module.paper_trading_repo, "list_positions", lambda *args, **kwargs: positions)
    monkeypatch.setattr(module.market_data_repo, "get_latest_snapshot", lambda symbol: snapshots.get(symbol))

    def upsert_trade_signal(*args, **kwargs):
        signal = {"id": len(signals) + 1, **kwargs}
        signals.append(signal)
        return signal

    def create_filled_order(*args, **kwargs):
        order = {
            "id": len(orders) + 1,
            "symbol": kwargs["symbol"],
            "side": kwargs["side"],
            "quantity": kwargs["quantity"],
            "price": float(Decimal(str(kwargs["price"]))),
            "reason": kwargs.get("reason") or "",
            "security_type": kwargs.get("security_type") or "stock",
            "bar_interval": kwargs.get("bar_interval") or "1d",
        }
        orders.append(order)
        return {"created": True, "order": order}

    monkeypatch.setattr(module.paper_trading_repo, "upsert_trade_signal", upsert_trade_signal)
    monkeypatch.setattr(module.paper_trading_repo, "create_filled_order", create_filled_order)
    monkeypatch.setattr(module.market_data_repo, "get_daily_bars", lambda *args, **kwargs: [])
    return orders, signals


def test_limit_up_return_only_breakout_confirmed_can_buy(monkeypatch):
    from backend.application.paper_trading_service import PaperTradingService

    _install_repo(
        monkeypatch,
        snapshots={
            "000001": {"symbol": "000001", "last_price": Decimal("10.80")},
            "000002": {"symbol": "000002", "last_price": Decimal("10.50")},
            "000003": {"symbol": "000003", "last_price": Decimal("9.80")},
        },
    )

    result = PaperTradingService().apply_strategy_scan(
        1,
        {"id": 1, "code": "LIMIT_UP_RETURN"},
        _scan(
            [
                {"symbol": "000001", "trade_date": "2026-05-05", "signal_subtype": "breakout_confirmed", "total_score": 90},
                {"symbol": "000002", "trade_date": "2026-05-05", "signal_subtype": "pullback_setup", "total_score": 95},
                {"symbol": "000003", "trade_date": "2026-05-05", "signal_subtype": "failed_pullback", "total_score": 80},
            ]
        ),
        {"cash_per_trade": 10000, "max_paper_positions": 5},
    )

    assert [order["symbol"] for order in result["orders"]] == ["000001"]
    assert result["skipped_reasons"] == {
        "limit_up_return_observation_only": 1,
        "limit_up_return_failed_pullback": 1,
    }
    assert result["non_executable_sample_ratio"] == 0.6667


def test_first_limit_up_only_auction_confirmed_can_buy(monkeypatch):
    from backend.application.paper_trading_service import PaperTradingService

    _install_repo(
        monkeypatch,
        snapshots={
            "000001": {"symbol": "000001", "last_price": Decimal("11.45")},
            "000002": {"symbol": "000002", "last_price": Decimal("10.95")},
            "000003": {"symbol": "000003", "last_price": Decimal("10.20")},
        },
    )

    result = PaperTradingService().apply_strategy_scan(
        1,
        {"id": 1, "code": "FIRST_LIMIT_UP"},
        _scan(
            [
                {"symbol": "000001", "trade_date": "2026-05-05", "signal_subtype": "auction_confirmed", "total_score": 88},
                {"symbol": "000002", "trade_date": "2026-05-05", "signal_subtype": "preopen_watch", "total_score": 91},
                {"symbol": "000003", "trade_date": "2026-05-05", "signal_subtype": "auction_rejected", "total_score": 80},
            ]
        ),
        {"cash_per_trade": 10000, "max_paper_positions": 5},
    )

    assert [order["symbol"] for order in result["orders"]] == ["000001"]
    assert result["skipped_reasons"] == {
        "first_limit_up_auction_pending": 1,
        "first_limit_up_auction_rejected": 1,
    }


def test_strategy_kill_switch_prefers_config_over_environment(monkeypatch):
    from backend.application.paper_trading_service import PaperTradingService

    _install_repo(monkeypatch, snapshots={"000001": {"symbol": "000001", "last_price": Decimal("10.50")}})
    monkeypatch.setenv("PAPER_TRADING_KILL_SWITCH_LIMIT_UP_RETURN", "1")
    scan = _scan([{"symbol": "000001", "trade_date": "2026-05-05", "signal_subtype": "breakout_confirmed"}])

    config_allows = PaperTradingService().apply_strategy_scan(
        1,
        {"id": 1, "code": "LIMIT_UP_RETURN", "config": {"paper_trading_kill_switch": False}},
        scan,
        {"cash_per_trade": 10000},
    )
    env_blocks = PaperTradingService().apply_strategy_scan(1, {"id": 1, "code": "LIMIT_UP_RETURN"}, scan, {"cash_per_trade": 10000})
    config_blocks = PaperTradingService().apply_strategy_scan(
        1,
        {"id": 1, "code": "LIMIT_UP_RETURN", "config": {"paper_trading_kill_switch": True}},
        scan,
        {"cash_per_trade": 10000},
    )

    assert config_allows["enabled"] is True
    assert config_allows["orders"]
    assert env_blocks["enabled"] is False
    assert env_blocks["reason"] == "strategy_kill_switch"
    assert config_blocks["enabled"] is False
    assert config_blocks["blocked_reasons"] == {"strategy_kill_switch": 1}


def test_daily_open_limit_blocks_extra_confirmed_signals(monkeypatch):
    from backend.application.paper_trading_service import PaperTradingService

    _install_repo(
        monkeypatch,
        snapshots={
            "000001": {"symbol": "000001", "last_price": Decimal("10.50")},
            "000002": {"symbol": "000002", "last_price": Decimal("10.80")},
        },
    )

    result = PaperTradingService().apply_strategy_scan(
        1,
        {"id": 1, "code": "LIMIT_UP_RETURN"},
        _scan(
            [
                {"symbol": "000001", "trade_date": "2026-05-05", "signal_subtype": "breakout_confirmed", "total_score": 90},
                {"symbol": "000002", "trade_date": "2026-05-05", "signal_subtype": "breakout_confirmed", "total_score": 88},
            ]
        ),
        {"cash_per_trade": 10000, "max_paper_positions": 5, "max_daily_opens": 1},
    )

    assert [order["symbol"] for order in result["orders"]] == ["000001"]
    assert result["skipped_reasons"] == {"max_daily_opens_reached": 1}
    assert result["limits"]["max_daily_opens"] == 1


def test_buy_blocks_suspended_limit_up_and_missing_snapshot_in_production(monkeypatch):
    from backend.application.paper_trading_service import PaperTradingService

    _install_repo(
        monkeypatch,
        snapshots={
            "000001": {"symbol": "000001", "last_price": Decimal("10"), "status": "suspended"},
            "000002": {"symbol": "000002", "last_price": Decimal("11"), "is_limit_up": True},
        },
    )

    result = PaperTradingService().apply_strategy_scan(
        1,
        {"id": 2, "code": "2560"},
        _scan(
            [
                {"symbol": "000001", "trade_date": "2026-05-05", "total_score": 90},
                {"symbol": "000002", "trade_date": "2026-05-05", "total_score": 90},
                {"symbol": "000003", "trade_date": "2026-05-05", "last_price": 10.2, "total_score": 90},
            ]
        ),
        {"cash_per_trade": 10000, "mode": "production"},
    )

    assert result["orders"] == []
    assert result["blocked_reasons"] == {"suspended": 1, "limit_up": 1, "missing_realtime_snapshot": 1}
    assert result["execution_report"]["blocked_count"] == 3


def test_sell_blocks_suspended_and_limit_down(monkeypatch):
    from backend.application.paper_trading_service import PaperTradingService

    positions = [
        {"symbol": "000001", "quantity": 100, "avg_cost": 10.0, "market_price": 8.8, "opened_at": "2026-04-01"},
        {"symbol": "000002", "quantity": 100, "avg_cost": 10.0, "market_price": 8.8, "opened_at": "2026-04-01"},
    ]
    orders, _ = _install_repo(
        monkeypatch,
        positions=positions,
        snapshots={
            "000001": {"symbol": "000001", "last_price": Decimal("8.80"), "status": "suspended"},
            "000002": {"symbol": "000002", "last_price": Decimal("9.00"), "is_limit_down": True},
        },
    )

    result = PaperTradingService().evaluate_exits(1, 7, {"allow_t0": True, "technical_exit_enabled": False})

    assert orders == []
    assert result["orders"] == []
    assert result["blocked_reasons"] == {"suspended": 1, "limit_down": 1}
    assert result["non_executable_sample_ratio"] == 1.0
