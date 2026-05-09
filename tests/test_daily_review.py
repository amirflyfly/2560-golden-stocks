from __future__ import annotations

import os
import tempfile
from datetime import date

import pytest

from backend import create_app


@pytest.fixture
def app():
    import backend.repositories.db as db_module

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = db_path
    app = create_app({"TESTING": True})

    try:
        yield app
    finally:
        db_module.DB_PATH = original_db_path
        os.close(db_fd)
        os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


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


def get_csrf_token(client) -> str | None:
    with client.session_transaction() as current_session:
        return current_session.get("_csrf_token")


def tenant_headers(client, tenant_id: int = 1, *, include_csrf: bool = False) -> dict:
    headers = {"X-Tenant-ID": str(tenant_id)}
    if include_csrf:
        headers["X-CSRF-Token"] = get_csrf_token(client) or ""
    return headers


def _seed_paper_trade(tenant_id: int = 1) -> dict:
    from backend.repositories import paper_trading_repo

    account = paper_trading_repo.ensure_default_account(tenant_id)
    paper_trading_repo.create_filled_order(
        tenant_id,
        account_id=account["id"],
        symbol="009907",
        side="BUY",
        quantity=100,
        price=10.5,
        strategy_code="FIRST_LIMIT_UP",
        idempotency_key=f"daily-review-buy-{tenant_id}",
        reason="daily review test",
    )
    return account


def test_daily_review_api_returns_trade_summary_and_template(client):
    account = _seed_paper_trade()
    authed = login_as(client, "editor_daily_review")

    response = authed.post(
        "/api/v1/reports/daily-review",
        json={"trade_date": date.today().isoformat(), "account_id": account["id"], "push": False},
        headers=tenant_headers(authed, include_csrf=True),
    )
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["schema_version"] == "daily-review/v1"
    assert data["paper_trading"]["orders_count"] == 1
    assert data["paper_trading"]["buy_orders"] == 1
    assert data["paper_trading"]["traded_symbols"] == ["009907"]
    assert "每日交易复盘" in data["message"]
    assert "report-attribution/v1" == data["attribution"]["schema_version"]
    assert data["notification"]["status"] == "created"
    assert data["push"]["status"] == "skipped"


def test_daily_review_dispatches_configured_external_channel(app, monkeypatch):
    from backend.application import report_api_service
    from backend.application.report_api_service import ReportApiService
    from backend.repositories import settings_repo

    _seed_paper_trade()
    sent = []

    class FakePushService:
        def enqueue_dispatch(self, tenant_id, user_id, config, notification, *, delivery_key=None, retry_count=0):
            sent.append({"config": config, "notification": notification, "delivery_key": delivery_key})
            return {"ok": True, "status": "queued", "channel_id": config["id"], "channel_type": config["type"], "task_id": "daily-review-task"}

    monkeypatch.setattr(report_api_service, "external_push_service", FakePushService())
    settings_repo.upsert_external_push_channel(
        1,
        1,
        {
            "id": "daily-review-webhook",
            "name": "Daily review webhook",
            "type": "webhook",
            "config": {"webhook_url": "https://alerts.example.com/daily-review"},
        },
    )

    result = ReportApiService().daily_review(
        1,
        date.today().isoformat(),
        push=True,
        channels=["webhook"],
        user_id=1,
        source="test",
    )

    assert result["push"]["status"] == "queued"
    assert result["push"]["queued"] == 1
    assert result["push"]["sent"] == 0
    assert sent[0]["config"]["id"] == "daily-review-webhook"
    assert sent[0]["delivery_key"].startswith("daily-review:1:1:")
    assert sent[0]["notification"]["entity"]["trade_date"] == date.today().isoformat()
