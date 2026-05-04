from __future__ import annotations

import os
import tempfile
import time

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



def get_auth_token(client) -> str | None:
    with client.session_transaction() as current_session:
        return current_session.get("auth_token")



def get_csrf_token(client) -> str | None:
    with client.session_transaction() as current_session:
        return current_session.get("_csrf_token")


def tenant_headers(client=None, tenant_id: int = 1, user_id: int | None = None, include_csrf: bool = False) -> dict:
    headers = {"X-Tenant-ID": str(tenant_id)}
    if user_id is not None:
        headers["X-User-ID"] = str(user_id)
    if include_csrf and client is not None:
        headers["X-CSRF-Token"] = get_csrf_token(client) or ""
    return headers


def assert_success_envelope(response, status_code=200):
    data = response.get_json()
    assert response.status_code == status_code
    assert set(data.keys()) == {"code", "message", "data"}
    assert data["code"] == 0
    assert data["message"] == "ok"
    return data["data"]



def assert_error_envelope(response, status_code, code):
    data = response.get_json()
    assert response.status_code == status_code
    assert set(data.keys()) == {"code", "message", "data"}
    assert data["code"] == code
    assert data["message"]
    return data["data"]



def wait_for_task(client, task_id: str, headers: dict, *, timeout_seconds: float = 3.0):
    deadline = time.time() + timeout_seconds
    last_payload = None
    while time.time() < deadline:
        response = client.get(f"/api/v1/tasks/{task_id}", headers=headers)
        payload = assert_success_envelope(response)
        last_payload = payload
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.05)
    return last_payload



def test_health_market_stocks_and_kline_contracts(client):
    user = login_as(client, "e2e_market")
    headers = tenant_headers(user, 1)

    health = assert_success_envelope(user.get("/api/v1/health"))
    assert health["status"] == "ok"
    assert "market_data_provider" in health

    market_health = assert_success_envelope(user.get("/api/v1/market-data/health"))
    assert market_health["provider"]
    assert market_health["ok"] is True
    assert "message" in market_health

    stocks = assert_success_envelope(user.get("/api/v1/stocks?keyword=平安&limit=1", headers=headers))
    assert stocks["total"] >= len(stocks["items"])
    assert len(stocks["items"]) <= 1
    assert stocks["items"][0]["symbol"] == "000001"

    kline = assert_success_envelope(
        user.get(
            "/api/v1/stocks/000001/kline?start_date=2026-01-01&end_date=2026-01-10&adjust=hfq",
            headers=headers,
        )
    )
    assert kline["symbol"] == "000001"
    assert kline["adjust"] == "hfq"
    assert kline["total"] == len(kline["items"])



def test_strategy_detail_and_pagination_contracts(client):
    user = login_as(client, "e2e_strategy")
    headers = tenant_headers(user, 1)

    page = assert_success_envelope(user.get("/api/v1/strategies?page=-9&page_size=500", headers=headers))
    assert page["tenant_id"] == 1
    assert page["page"] == 1
    assert page["page_size"] == 200
    assert page["total"] >= 2

    strategy = assert_success_envelope(user.get("/api/v1/strategies/1", headers=headers))
    assert strategy["id"] == 1
    assert strategy["tenant_id"] == 1

    assert_error_envelope(user.get("/api/v1/strategies/999", headers=headers), 404, 404)



def test_scan_task_results_and_task_visibility_flow(app):
    tenant1_client = app.test_client()
    tenant2_client = app.test_client()

    user1 = login_as(tenant1_client, "e2e_scan_one")
    user2 = login_as(tenant2_client, "e2e_scan_two")
    from backend.repositories import users_repo

    users_repo.create_tenant("e2e-scan-two", "E2E Scan Two")
    tenant2 = users_repo.get_tenant_by_code("e2e-scan-two")
    user2_row = users_repo.get_user_by_username("e2e_scan_two")
    users_repo.bind_user_tenant(user2_row["id"], tenant2["id"], "editor")

    headers1 = tenant_headers(user1, 1)
    headers2 = tenant_headers(user2, tenant2["id"])

    created = assert_success_envelope(
        user1.post(
            "/api/v1/scans",
            json={"strategy_code": "2560", "params": {"trade_date": "2026-05-02"}},
            headers=tenant_headers(user1, 1, include_csrf=True),
        ),
        status_code=202,
    )
    assert created["tenant_id"] == 1
    assert created["strategy_code"] == "2560"
    assert created["task_id"]

    task = wait_for_task(user1, created["task_id"], headers1)
    assert task["tenant_id"] == 1
    assert task["name"] == "scan.run"
    assert task["status"] in {"completed", "running", "pending"}

    scans = assert_success_envelope(user1.get("/api/v1/scans", headers=headers1))
    assert scans["tenant_id"] == 1
    assert any(item["id"] == created["task_id"] for item in scans["items"])

    results = assert_success_envelope(user1.get(f"/api/v1/scans/{created['task_id']}/results", headers=headers1))
    assert results["tenant_id"] == 1
    assert results["scan_id"] == created["task_id"]
    assert "items" in results

    assert_error_envelope(user2.get(f"/api/v1/tasks/{created['task_id']}", headers=headers2), 404, 404)
    assert_error_envelope(user2.get(f"/api/v1/scans/{created['task_id']}/results", headers=headers2), 404, 404)



def test_pick_and_report_create_list_detail_flow(client):
    user = login_as(client, "e2e_pick_report")
    headers = tenant_headers(user, 1)

    pick = assert_success_envelope(
        user.post(
            "/api/v1/picks",
            json={"symbol": "000001", "stock_name": "平安银行", "trade_date": "2026-05-02", "source": "manual"},
            headers=tenant_headers(user, 1, include_csrf=True),
        ),
        status_code=201,
    )
    assert pick["tenant_id"] == 1
    assert pick["symbol"] == "000001"
    assert pick["status"] == "accepted"

    picks = assert_success_envelope(user.get("/api/v1/picks?page=abc&page_size=0", headers=headers))
    assert picks["tenant_id"] == 1
    assert picks["page"] == 1
    assert picks["page_size"] == 1

    report = assert_success_envelope(
        user.post(
            "/api/v1/reports",
            json={"symbol": "000001", "title": "平安银行研究", "content": "test"},
            headers=tenant_headers(user, 1, include_csrf=True),
        ),
        status_code=201,
    )
    assert report["tenant_id"] == 1
    assert report["id"]

    reports = assert_success_envelope(user.get("/api/v1/reports?symbol=000001", headers=headers))
    assert reports["tenant_id"] == 1
    assert reports["filters"] == {"symbol": "000001"}

    detail = assert_success_envelope(user.get(f"/api/v1/reports/{report['id']}", headers=headers))
    assert detail["tenant_id"] == 1
    assert detail["id"] == report["id"]



def test_market_sync_task_and_task_list_flow(client):
    admin = login_as(client, "e2e_admin_sync", role="admin")
    headers = tenant_headers(admin, 1)

    created = assert_success_envelope(
        admin.post(
            "/api/v1/market-data/sync",
            json={"symbols": ["000001"], "start_date": "2026-01-01", "end_date": "2026-01-05"},
            headers=tenant_headers(admin, 1, include_csrf=True),
        ),
        status_code=202,
    )
    assert created["tenant_id"] == 1
    assert created["name"] == "market.sync"
    assert created["payload"]["symbols"] == ["000001"]

    task = wait_for_task(admin, created["id"], headers)
    assert task["id"] == created["id"]
    assert task["tenant_id"] == 1

    tasks = assert_success_envelope(admin.get("/api/v1/tasks?page=1&page_size=20", headers=headers))
    assert tasks["tenant_id"] == 1
    assert "cache" in tasks
    assert any(item["id"] == created["id"] for item in tasks["items"])



def test_protected_routes_require_login_and_tenant_header(client):
    protected_requests = [
        ("GET", "/api/v1/strategies"),
        ("GET", "/api/v1/stocks"),
        ("POST", "/api/v1/scans"),
        ("GET", "/api/v1/picks"),
        ("GET", "/api/v1/reports"),
        ("GET", "/api/v1/tasks"),
        ("POST", "/api/v1/market-data/sync"),
    ]
    for method, path in protected_requests:
        response = client.open(path, method=method, json={}, headers={"X-Tenant-ID": "1"})
        assert_error_envelope(response, 401, 401)

    user = login_as(client, "e2e_missing_tenant")
    for method, path in protected_requests:
        response = user.open(path, method=method, json={})
        expected_status = 400 if method == "GET" else 403
        expected_code = 10400 if method == "GET" else 403
        assert_error_envelope(response, expected_status, expected_code)

    assert_error_envelope(user.get("/api/v1/strategies", headers={"X-Tenant-ID": "abc"}), 400, 10400)



def test_post_endpoints_reject_missing_csrf_token(client):
    user = login_as(client, "e2e_missing_csrf")

    scan_response = user.post(
        "/api/v1/scans",
        json={"strategy_code": "2560", "params": {}},
        headers=tenant_headers(user, 1),
    )
    assert_error_envelope(scan_response, 403, 403)

    sync_admin = client.application.test_client()
    login_as(sync_admin, "e2e_missing_csrf_admin", role="admin")
    sync_response = sync_admin.post(
        "/api/v1/market-data/sync",
        json={"symbols": ["000001"]},
        headers=tenant_headers(sync_admin, 1),
    )
    assert_error_envelope(sync_response, 403, 403)


def test_user_id_header_mismatch_is_rejected(client):
    user = login_as(client, "e2e_uid_mismatch")

    response = user.get(
        "/api/v1/strategies",
        headers=tenant_headers(user, 1, user_id=999),
    )
    assert_error_envelope(response, 401, 401)



def test_logout_and_relogin_flow_for_protected_api(client):
    user = login_as(client, "e2e_logout_relogin")
    headers = tenant_headers(user, 1)
    assert get_auth_token(user)

    protected_before_logout = user.get("/api/v1/tasks", headers=headers)
    assert_success_envelope(protected_before_logout)

    logout_response = user.get("/logout", follow_redirects=True)
    assert logout_response.status_code == 200
    assert get_auth_token(user) is None

    protected_after_logout = user.get("/api/v1/tasks", headers=headers)
    assert_error_envelope(protected_after_logout, 401, 401)

    relogged = login_as(user, "e2e_logout_relogin")
    protected_after_relogin = relogged.get("/api/v1/tasks", headers=headers)
    assert_success_envelope(protected_after_relogin)



def test_expired_session_cannot_access_scan_results(client):
    from backend.repositories import sessions_repo, users_repo

    user = login_as(client, "e2e_expired_results")
    headers = tenant_headers(user, 1)

    created = assert_success_envelope(
        user.post(
            "/api/v1/scans",
            json={"strategy_code": "2560", "params": {}},
            headers=tenant_headers(user, 1, include_csrf=True),
        ),
        status_code=202,
    )

    current_token = get_auth_token(user)
    current_user = users_repo.get_user_by_username("e2e_expired_results")
    sessions_repo.create_session("expired-scan-token", current_user["id"], "2000-01-01 00:00:00")
    sessions_repo.delete_session(current_token)
    with user.session_transaction() as current_session:
        current_session["auth_token"] = "expired-scan-token"

    response = user.get(f"/api/v1/scans/{created['task_id']}/results", headers=headers)
    assert_error_envelope(response, 401, 401)
    assert sessions_repo.get_session("expired-scan-token") is None
