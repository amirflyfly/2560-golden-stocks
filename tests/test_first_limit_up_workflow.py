from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from backend import create_app
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
    monkeypatch.setenv("SETTINGS_REPOSITORY_BACKEND", "sqlite")
    app = create_app({"TESTING": True})
    try:
        yield app
    finally:
        db_module.DB_PATH = original_db_path


@pytest.fixture
def client(app_db):
    return app_db.test_client()


def get_csrf_token(client) -> str | None:
    with client.session_transaction() as current_session:
        return current_session.get("_csrf_token")


def tenant_headers(client, tenant_id: int = 1, *, include_csrf: bool = False) -> dict:
    headers = {"X-Tenant-ID": str(tenant_id)}
    if include_csrf:
        headers["X-CSRF-Token"] = get_csrf_token(client) or ""
    return headers


def login_as(client, username: str, role: str = "editor", password: str = "testpass"):
    from backend.services.multiuser_auth_service import create_user as create_auth_user

    create_auth_user(username, password, role)
    client.get("/login")
    response = client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": get_csrf_token(client)},
        follow_redirects=True,
    )
    assert response.status_code == 200
    return client


def _seed_local_market_data() -> None:
    market_data_repo.upsert_daily_bars(
        [
            DailyBar(
                symbol="000001",
                trade_date=date(2026, 5, 4),
                open=Decimal("9.30"),
                high=Decimal("10.10"),
                low=Decimal("9.20"),
                close=Decimal("9.80"),
                volume=100000,
                amount=Decimal("980000"),
                source="unit",
            )
        ],
        adjust="qfq",
    )
    market_data_repo.upsert_quote_snapshots(
        [
            QuoteSnapshot(
                symbol="000001",
                trade_time=datetime(2026, 5, 5, 9, 25),
                last_price=Decimal("10.20"),
                open=Decimal("10.05"),
                high=Decimal("10.25"),
                low=Decimal("10.00"),
                prev_close=Decimal("9.80"),
                volume=120000,
                amount=Decimal("1224000"),
                source="unit",
            )
        ]
    )


def test_first_limit_up_production_run_buys_only_auction_confirmed_signal(client, monkeypatch):
    from backend.application.scan_api_service import ScanApiService

    def fake_run_scan(self, tenant_id, strategy_code, params):
        return {
            "tenant_id": tenant_id,
            "strategy_code": strategy_code,
            "params": params,
            "strategy_runner": "registry",
            "market_data": {
                "provider": "local",
                "actual_provider": "local",
                "data_quality": "primary",
                "fallback_used": False,
                "sample_symbols": [
                    {
                        "symbol": "000001",
                        "code": "000001",
                        "name": "Confirmed First Board",
                        "trade_date": "2026-05-05",
                        "signal": "auction_entry_confirmed",
                        "signal_type": "BUY",
                        "signal_subtype": "auction_confirmed",
                        "total_score": 91,
                        "last_price": 10.20,
                        "security_type": "stock",
                        "bar_interval": "1d",
                        "data_quality": "primary",
                    },
                    {
                        "symbol": "000002",
                        "code": "000002",
                        "name": "Pending First Board",
                        "trade_date": "2026-05-05",
                        "signal": "first_limit_watch",
                        "signal_type": "WATCH",
                        "signal_subtype": "preopen_watch",
                        "total_score": 88,
                        "last_price": 10.10,
                        "security_type": "stock",
                        "bar_interval": "1d",
                        "data_quality": "primary",
                    },
                    {
                        "symbol": "000003",
                        "code": "000003",
                        "name": "Rejected First Board",
                        "trade_date": "2026-05-05",
                        "signal": "auction_rejected",
                        "signal_type": "WATCH",
                        "signal_subtype": "auction_rejected",
                        "total_score": 84,
                        "last_price": 10.00,
                        "security_type": "stock",
                        "bar_interval": "1d",
                        "data_quality": "primary",
                    },
                ],
            },
            "matched_count": 3,
        }

    _seed_local_market_data()
    monkeypatch.setattr(ScanApiService, "_run_scan", fake_run_scan)

    strategy = strategy_repo.get_strategy_by_code("first_limit_up")
    assert strategy
    authed = login_as(client, "editor_first_limit_workflow", role="editor")
    response = authed.post(
        f"/api/v1/strategies/{strategy['id']}/production-run",
        json={
            "params": {
                "sample_size": 3,
                "bar_interval": "1d",
                "adjust": "qfq",
                "paper_trade": True,
                "cash_per_trade": 10000,
                "max_paper_positions": 5,
            }
        },
        headers=tenant_headers(authed, include_csrf=True),
    )
    data = response.get_json()["data"]
    result = data["task"]["result"]
    paper = result["paper_trading"]

    assert response.status_code == 202
    assert data["task"]["status"] == "completed"
    assert result["production_status"] == "completed"
    assert paper["enabled"] is True
    assert [order["symbol"] for order in paper["orders"]] == ["000001"]
    assert paper["skipped_reasons"] == {
        "first_limit_up_auction_pending": 1,
        "first_limit_up_auction_rejected": 1,
    }

    orders = authed.get("/api/v1/trading/paper/orders", headers=tenant_headers(authed)).get_json()["data"]
    signals = authed.get("/api/v1/trading/signals", headers=tenant_headers(authed)).get_json()["data"]

    assert orders["total"] == 1
    assert orders["items"][0]["symbol"] == "000001"
    assert signals["total"] == 1
    assert signals["items"][0]["signal_type"] == "BUY"
