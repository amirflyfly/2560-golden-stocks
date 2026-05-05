from __future__ import annotations

import os
import tempfile

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


def test_alert_evaluation_creates_and_marks_in_app_notifications(client):
    authed = login_as(client, "editor_alert_pick")
    write_headers = tenant_headers(authed, include_csrf=True)
    read_headers = tenant_headers(authed)

    pick = authed.post(
        "/api/v1/picks",
        json={
            "symbol": "009901",
            "stock_name": "Alert Pick",
            "trade_date": "2026-05-04",
            "source": "manual-alert",
        },
        headers=write_headers,
    ).get_json()["data"]
    authed.patch(
        f"/api/v1/picks/{pick['id']}/review",
        json={"risk_level": "high", "drawdown_pct": -0.08, "status": "watching", "watch_flag": True},
        headers=write_headers,
    )
    alert = authed.post(
        "/api/v1/settings/alerts",
        json={
            "name": "Drawdown alert",
            "scope": "picks",
            "target": "009901",
            "rule": {"field": "drawdown_pct", "operator": "<=", "value": -0.05},
            "channels": ["in_app"],
        },
        headers=write_headers,
    ).get_json()["data"]

    evaluate_response = authed.post(
        "/api/v1/settings/alerts/evaluate",
        json={"limit_per_rule": 10},
        headers=write_headers,
    )
    evaluation = evaluate_response.get_json()["data"]

    assert evaluate_response.status_code == 200
    assert evaluation["rules_evaluated"] == 1
    assert evaluation["matches"] == 1
    assert evaluation["by_scope"]["picks"]["notifications"] == 1

    notifications_response = authed.get("/api/v1/settings/notifications", headers=read_headers)
    notifications = notifications_response.get_json()["data"]
    notification = notifications["items"][0]

    assert notifications_response.status_code == 200
    assert notifications["unread_count"] == 1
    assert notification["rule_id"] == alert["id"]
    assert notification["entity"]["type"] == "pick"
    assert notification["entity"]["symbol"] == "009901"
    assert notification["match"]["field"] == "drawdown_pct"
    assert notification["read_at"] is None

    read_response = authed.patch(
        f"/api/v1/settings/notifications/{notification['id']}",
        json={"read": True},
        headers=write_headers,
    )
    assert read_response.status_code == 200
    assert read_response.get_json()["data"]["read_at"]

    unread_response = authed.get(
        "/api/v1/settings/notifications?unread_only=1",
        headers=read_headers,
    )
    assert unread_response.get_json()["data"]["items"] == []

    authed.post("/api/v1/settings/alerts/evaluate", json={}, headers=write_headers)
    after_repeat = authed.get("/api/v1/settings/notifications", headers=read_headers).get_json()["data"]
    assert len(after_repeat["items"]) == 1
    assert after_repeat["items"][0]["occurrence_count"] == 2
    assert after_repeat["items"][0]["read_at"]


def test_alert_evaluation_supports_scan_result_rules(client):
    from backend.infrastructure.tasks.queue import save_task

    authed = login_as(client, "editor_alert_scan")
    write_headers = tenant_headers(authed, include_csrf=True)

    save_task(
        {
            "id": "scan-alert-task-1",
            "name": "scan.run",
            "tenant_id": 1,
            "status": "completed",
            "payload": {},
            "idempotency_key": "scan-alert-task-1",
            "retry_count": 0,
            "max_retries": 0,
            "created_at": "2026-05-04T09:00:00",
            "started_at": "2026-05-04T09:00:00",
            "finished_at": "2026-05-04T09:00:01",
            "result": {
                "market_data": {
                    "provider": "mock",
                    "actual_provider": "mock",
                    "data_quality": "mock",
                    "fallback_used": False,
                    "sample_symbols": [
                        {
                            "symbol": "009902",
                            "name": "Alert Scan",
                            "data_quality": "mock",
                            "explanation": {"score": 92, "confidence": 0.7, "risk_level": "high"},
                        }
                    ],
                }
            },
            "error": None,
            "events": [],
        }
    )
    alert = authed.post(
        "/api/v1/settings/alerts",
        json={
            "name": "High score scan",
            "scope": "scan_results",
            "target": "009902",
            "rule": {"metric": "score_gte", "threshold": 90},
            "channels": ["in_app"],
            "metadata": {"page": "scans"},
        },
        headers=write_headers,
    ).get_json()["data"]

    response = authed.post("/api/v1/settings/alerts/evaluate", json={}, headers=write_headers)
    data = response.get_json()["data"]
    notification = authed.get(
        "/api/v1/settings/notifications",
        headers=tenant_headers(authed),
    ).get_json()["data"]["items"][0]

    assert response.status_code == 200
    assert data["by_scope"]["scan_results"]["matches"] == 1
    assert notification["rule_id"] == alert["id"]
    assert notification["entity"]["type"] == "scan_result"
    assert notification["entity"]["scan_id"] == "scan-alert-task-1"
    assert notification["entity"]["symbol"] == "009902"
    assert notification["match"]["metric"] == "score_gte"


def test_alert_evaluation_supports_limit_up_return_state_transition(client):
    from backend.infrastructure.tasks.queue import save_task

    authed = login_as(client, "editor_alert_limit_return")
    write_headers = tenant_headers(authed, include_csrf=True)

    save_task(
        {
            "id": "scan-alert-limit-return-1",
            "name": "scan.run",
            "tenant_id": 1,
            "status": "completed",
            "payload": {},
            "idempotency_key": "scan-alert-limit-return-1",
            "retry_count": 0,
            "max_retries": 0,
            "result": {
                "market_data": {
                    "sample_symbols": [
                        {
                            "symbol": "009903",
                            "name": "Limit Return",
                            "strategy_code": "LIMIT_UP_RETURN",
                            "previous_signal_subtype": "pullback_setup",
                            "signal_subtype": "breakout_confirmed",
                        }
                    ]
                }
            },
        }
    )
    alert = authed.post(
        "/api/v1/settings/alerts",
        json={
            "name": "Limit return confirmed",
            "scope": "scan_results",
            "target": "009903",
            "rule": {
                "metric": "signal_state_transition",
                "strategy_code": "LIMIT_UP_RETURN",
                "from": "pullback_setup",
                "to": "breakout_confirmed",
            },
            "channels": ["in_app"],
        },
        headers=write_headers,
    ).get_json()["data"]

    response = authed.post("/api/v1/settings/alerts/evaluate", json={}, headers=write_headers)
    data = response.get_json()["data"]
    notification = authed.get(
        "/api/v1/settings/notifications",
        headers=tenant_headers(authed),
    ).get_json()["data"]["items"][0]

    assert response.status_code == 200
    assert data["matches"] == 1
    assert notification["rule_id"] == alert["id"]
    assert notification["entity"]["symbol"] == "009903"
    assert notification["match"]["metric"] == "signal_state_transition"
    assert notification["match"]["actual"]["from"] == "pullback_setup"
    assert notification["match"]["actual"]["to"] == "breakout_confirmed"
