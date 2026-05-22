from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import os
import tempfile

import pytest

from backend import create_app
from backend.infrastructure.market_data.provider import DailyBar, HealthCheckResult, QuoteSnapshot, StockInfo


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



def tenant_headers(client, tenant_id: int = 1, *, include_csrf: bool = False, extra: dict | None = None) -> dict:
    headers = {"X-Tenant-ID": str(tenant_id)}
    if include_csrf:
        headers["X-CSRF-Token"] = get_csrf_token(client) or ""
    if extra:
        headers.update(extra)
    return headers


class TestMarketProvider:
    name = "akshare"

    def get_stock_list(self):
        return [
            StockInfo("000001", "Ping An", "SZ"),
            StockInfo("000002", "Vanke", "SZ"),
            StockInfo("000003", "Test A", "SZ"),
            StockInfo("600000", "SPDB", "SH"),
            StockInfo("600519", "Moutai", "SH"),
        ]

    def get_daily_bars(self, symbol, start_date, end_date, adjust="qfq", interval="1d"):
        current = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        bars = []
        while current <= end:
            if current.weekday() < 5:
                trade_time = datetime.combine(current, datetime.min.time())
                bars.append(
                    DailyBar(
                        symbol=symbol,
                        trade_date=current,
                        trade_time=trade_time,
                        interval=interval,
                        open=Decimal("10"),
                        high=Decimal("11"),
                        low=Decimal("9"),
                        close=Decimal("10.5"),
                        volume=100,
                        amount=Decimal("1050"),
                        source=self.name,
                    )
                )
            current += timedelta(days=1)
        return bars

    def get_quote_snapshots(self, symbols):
        return [
            QuoteSnapshot(
                symbol=symbol,
                trade_time="2026-05-08T09:30:00",
                last_price=Decimal("10"),
                open=Decimal("10"),
                high=Decimal("10"),
                low=Decimal("10"),
                source=self.name,
            )
            for symbol in symbols
        ]

    def get_trading_dates(self, start_date, end_date):
        current = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        dates = []
        while current <= end:
            if current.weekday() < 5:
                dates.append(current.isoformat())
            current += timedelta(days=1)
        return dates

    def health_check(self):
        return HealthCheckResult(provider=self.name, ok=True)


def test_api_v1_health_response_shape():
    app = create_app({"TESTING": True})
    client = app.test_client()

    response = client.get("/api/v1/health")
    data = response.get_json()

    assert response.status_code == 200
    assert data["code"] == 0
    assert data["message"] == "ok"
    assert data["data"]["status"] == "ok"


def test_market_data_health_exposes_provider_usage_metadata():
    app = create_app({"TESTING": True})
    client = app.test_client()

    response = client.get("/api/v1/market-data/health")
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["provider"]
    assert data["actual_provider"]
    assert isinstance(data["provider_chain"], list)
    assert "fallback_used" in data
    assert data["data_quality"] in {"primary", "fallback", "unknown"}



def test_security_headers_and_cookie_attributes_are_set(client):
    response = client.get("/login")

    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert "object-src 'none'" in response.headers["Content-Security-Policy"]
    assert "camera=()" in response.headers["Permissions-Policy"]

    set_cookie_headers = response.headers.getlist("Set-Cookie")
    csrf_cookie = next(cookie for cookie in set_cookie_headers if cookie.startswith("promo_panel_csrf="))
    session_cookie = next(cookie for cookie in set_cookie_headers if cookie.startswith("promo_panel_auth="))

    assert "SameSite=Lax" in csrf_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "HttpOnly" in session_cookie
    assert "SameSite=Lax" in session_cookie



def test_strategies_requires_login(client):
    response = client.get("/api/v1/strategies", headers={"X-Tenant-ID": "1"})
    data = response.get_json()

    assert response.status_code == 401
    assert data["code"] == 401



def test_strategies_requires_tenant_header_even_after_login(client):
    authed = login_as(client, "editor_no_tenant")

    response = authed.get("/api/v1/strategies")
    data = response.get_json()

    assert response.status_code == 400
    assert data["code"] == 10400



def test_login_rejects_missing_csrf_token(client):
    client.get("/login")
    response = client.post(
        "/login",
        data={"username": "admin", "password": "admin123"},
        follow_redirects=True,
    )

    assert response.status_code == 403
    assert "请求校验失败" in response.get_data(as_text=True)


def test_auth_bootstrap_reports_initialized_admin(client):
    response = client.get("/api/v1/auth/bootstrap")
    data = response.get_json()

    assert response.status_code == 200
    assert data["code"] == 0
    assert data["data"]["has_users"] is True
    assert data["data"]["admin_initialized"] is True
    assert data["data"]["admin_init_required"] is False


def test_json_login_establishes_react_session_and_me(client):
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    data = response.get_json()

    assert response.status_code == 200
    assert data["code"] == 0
    assert data["data"]["username"] == "admin"
    assert data["data"]["role"] == "admin"
    assert data["data"]["tenant_id"] == 1
    assert get_auth_token(client)

    me_response = client.get("/api/v1/me", headers=tenant_headers(client))
    me_data = me_response.get_json()

    assert me_response.status_code == 200
    assert me_data["data"]["role"] == "admin"
    assert me_data["data"]["permissions"]["can_admin"] is True


def test_json_login_rejects_invalid_credentials(client):
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong-password"})
    data = response.get_json()

    assert response.status_code == 401
    assert data["code"] == 401


def test_json_logout_revokes_react_session(client):
    login_response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert login_response.status_code == 200
    assert get_auth_token(client)

    logout_response = client.post("/api/v1/auth/logout", json={}, headers=tenant_headers(client, include_csrf=True))
    logout_data = logout_response.get_json()

    assert logout_response.status_code == 200
    assert logout_data["data"]["logged_out"] is True
    assert get_auth_token(client) is None

    me_response = client.get("/api/v1/me", headers=tenant_headers(client))
    assert me_response.status_code == 401



def test_scan_write_requires_csrf_token(client):
    authed = login_as(client, "editor_no_csrf")

    response = authed.post(
        "/api/v1/scans",
        json={"strategy_code": "2560", "params": {}},
        headers=tenant_headers(authed),
    )
    data = response.get_json()

    assert response.status_code == 403
    assert data["code"] == 403
    assert data["message"] == "csrf token invalid"



def test_scan_write_rejects_cross_site_sec_fetch(client):
    authed = login_as(client, "editor_cross_site")

    response = authed.post(
        "/api/v1/scans",
        json={"strategy_code": "2560", "params": {}},
        headers=tenant_headers(authed, include_csrf=True, extra={"Sec-Fetch-Site": "cross-site"}),
    )
    data = response.get_json()

    assert response.status_code == 403
    assert data["code"] == 403
    assert data["message"] == "forbidden"



def test_scan_write_rejects_cross_origin_header(client):
    authed = login_as(client, "editor_cross_origin")

    response = authed.post(
        "/api/v1/scans",
        json={"strategy_code": "2560", "params": {}},
        headers=tenant_headers(
            authed,
            include_csrf=True,
            extra={"Origin": "https://attacker.example"},
        ),
    )
    data = response.get_json()

    assert response.status_code == 403
    assert data["code"] == 403
    assert data["message"] == "forbidden"


def test_scan_write_accepts_loopback_dev_proxy_origin_with_valid_csrf(client):
    authed = login_as(client, "editor_dev_proxy_origin")

    response = authed.post(
        "/api/v1/scans",
        json={"strategy_code": "2560", "params": {}},
        headers=tenant_headers(
            authed,
            include_csrf=True,
            extra={"Origin": "http://127.0.0.1:5176", "Sec-Fetch-Site": "same-site"},
        ),
    )
    data = response.get_json()

    assert response.status_code == 202
    assert data["code"] == 0



def test_scan_write_rejects_cross_site_referer_without_origin(client):
    authed = login_as(client, "editor_cross_referer")

    response = authed.post(
        "/api/v1/scans",
        json={"strategy_code": "2560", "params": {}},
        headers=tenant_headers(
            authed,
            include_csrf=True,
            extra={"Referer": "https://attacker.example/form"},
        ),
    )
    data = response.get_json()

    assert response.status_code == 403
    assert data["code"] == 403
    assert data["message"] == "forbidden"



def test_scan_write_accepts_same_origin_with_valid_csrf(client):
    authed = login_as(client, "editor_same_origin")

    response = authed.post(
        "/api/v1/scans",
        json={"strategy_code": "2560", "params": {}},
        headers=tenant_headers(
            authed,
            include_csrf=True,
            extra={"Origin": "http://localhost/", "Sec-Fetch-Site": "same-origin"},
        ),
    )
    data = response.get_json()

    assert response.status_code == 202
    assert data["code"] == 0
    assert data["data"]["tenant_id"] == 1



def test_strategies_list_returns_paginated_data_with_auth(client):
    authed = login_as(client, "editor_list")

    response = authed.get("/api/v1/strategies", headers={"X-Tenant-ID": "1"})
    data = response.get_json()

    assert response.status_code == 200
    assert data["code"] == 0
    assert data["data"]["tenant_id"] == 1
    assert data["data"]["items"]
    assert data["data"]["workflow"]["data_policy"]["backtest"] == "local_market_data_first"


def test_strategy_lifecycle_create_edit_test_and_deploy(client):
    authed = login_as(client, "editor_strategy_lifecycle")
    headers = tenant_headers(authed, include_csrf=True)

    create_response = authed.post(
        "/api/v1/strategies",
        json={
            "code": "custom_life",
            "name": "Custom Lifecycle",
            "category": "自定义策略",
            "description": "draft strategy",
            "config": {"target_security_type": "convertible_bond", "bar_interval": "15m", "adjust": "none", "allow_t0": True},
            "code_body": "from backend.strategies import BaseStrategy\n\nclass CustomLife(BaseStrategy):\n    def get_code(self):\n        return 'custom_life'\n    def get_name(self):\n        return 'Custom Lifecycle'\n    def get_description(self):\n        return 'draft'\n    def scan(self, date=None):\n        return []\n",
        },
        headers=headers,
    )
    created = create_response.get_json()["data"]

    assert create_response.status_code == 201
    assert created["lifecycle_status"] == "draft"
    assert created["runtime_registered"] is False
    assert created["target_security_type"] == "convertible_bond"
    assert created["bar_interval"] == "15m"
    assert created["data_requirements"]["t0_supported"] is True

    update_response = authed.patch(
        f"/api/v1/strategies/{created['id']}",
        json={"description": "edited strategy", "enabled": False},
        headers=headers,
    )
    updated = update_response.get_json()["data"]

    assert update_response.status_code == 200
    assert updated["description"] == "edited strategy"

    test_response = authed.post(f"/api/v1/strategies/{created['id']}/test", json={}, headers=headers)
    tested = test_response.get_json()["data"]

    assert test_response.status_code == 200
    assert tested["result"]["passed"] is True
    assert tested["strategy"]["last_test_status"] == "passed"

    deploy_response = authed.post(f"/api/v1/strategies/{created['id']}/deploy", json={}, headers=headers)
    deployed = deploy_response.get_json()["data"]

    assert deploy_response.status_code == 200
    assert deployed["strategy"]["lifecycle_status"] == "deployed"
    assert deployed["strategy"]["enabled"] is True


def test_me_returns_effective_tenant_role_and_permissions(client):
    editor = login_as(client, "editor_me", role="editor")

    response = editor.get("/api/v1/me", headers=tenant_headers(editor))
    data = response.get_json()

    assert response.status_code == 200
    assert data["data"]["tenant_id"] == 1
    assert data["data"]["role"] == "editor"
    assert data["data"]["permissions"] == {"can_read": True, "can_write": True, "can_admin": False}


def test_me_uses_tenant_level_role_override(client):
    from backend.repositories import users_repo

    admin = login_as(client, "admin_me_viewer", role="admin")
    users_repo.create_tenant("me-role-scope", "Me Role Scope")
    tenant = users_repo.get_tenant_by_code("me-role-scope")
    user = users_repo.get_user_by_username("admin_me_viewer")
    users_repo.bind_user_tenant(user["id"], tenant["id"], "viewer")

    response = admin.get("/api/v1/me", headers=tenant_headers(admin, tenant_id=tenant["id"]))
    data = response.get_json()

    assert response.status_code == 200
    assert data["data"]["tenant_id"] == tenant["id"]
    assert data["data"]["role"] == "viewer"
    assert data["data"]["permissions"]["can_write"] is False
    assert data["data"]["permissions"]["can_admin"] is False



def test_create_scan_returns_accepted_task_for_editor(client):
    authed = login_as(client, "editor_scan")

    response = authed.post(
        "/api/v1/scans",
        json={"strategy_code": "2560", "params": {"trade_date": "2026-05-02"}},
        headers=tenant_headers(authed, include_csrf=True),
    )
    data = response.get_json()

    assert response.status_code == 202
    assert data["data"]["strategy_code"] == "2560"
    assert data["data"]["tenant_id"] == 1
    assert data["data"]["market_data"]["healthy"] is True
    assert data["data"]["market_data"]["actual_provider"] != "mock"
    assert data["data"]["market_data"]["data_quality"] in {"primary", "fallback", "unknown"}
    assert data["data"]["market_data"]["fallback_used"] is False
    assert data["data"]["explanation"]["score"] >= 0
    assert data["data"]["explanation"]["schema_version"] == "scan-task-explanation/v2"
    assert "indicator_groups" in data["data"]["explanation"]
    assert "action_suggestion" in data["data"]["explanation"]
    assert "reasons" in data["data"]["explanation"]


def test_task_center_paginates_and_exposes_failure_summary(client):
    from backend.infrastructure.tasks.queue import save_task

    authed = login_as(client, "editor_task_center")
    for index in range(12):
        save_task(
            {
                "id": f"task-center-{index}",
                "name": "scan.strategy",
                "tenant_id": 1,
                "status": "failed" if index == 0 else "completed",
                "payload": {},
                "idempotency_key": f"task-center-{index}",
                "retry_count": 0,
                "max_retries": 0,
                "failure_category": "validation" if index == 0 else None,
                "heartbeat_at": "2026-05-04T09:00:00",
                "duration_seconds": 1.5,
                "events": [{"status": "failed" if index == 0 else "completed", "message": "done", "at": "2026-05-04T09:00:00"}],
                "created_at": f"2026-05-04T09:00:{index:02d}",
                "started_at": "2026-05-04T09:00:00",
                "finished_at": "2026-05-04T09:00:01",
                "result": {"matched_count": index},
                "error": "bad input" if index == 0 else None,
            }
        )

    response = authed.get(
        "/api/v1/tasks?page=1&page_size=5&status=failed&sort=created_at&order=asc",
        headers=tenant_headers(authed),
    )
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["page_size"] == 5
    assert data["sort"] == {"field": "created_at", "order": "asc"}
    assert data["filters"]["normalized_status"] == "failed"
    assert data["items"][0]["failure_category"] == "validation"
    assert data["items"][0]["lifecycle_status"] == "failed"
    assert data["items"][0]["error_summary"] == "bad input"
    assert data["items"][0]["events"]


def test_task_center_accepts_lifecycle_status_aliases_and_sorting(client):
    from backend.infrastructure.tasks.queue import save_task

    authed = login_as(client, "editor_task_aliases")
    for task_id, status, created_at, duration in [
        ("task-alias-old", "completed", "2026-05-04T09:00:00", 1.0),
        ("task-alias-new", "completed", "2026-05-04T10:00:00", 2.0),
        ("task-alias-cancelled", "cancelled", "2026-05-04T11:00:00", 3.0),
    ]:
        save_task(
            {
                "id": task_id,
                "name": "alias.strategy",
                "tenant_id": 1,
                "status": status,
                "payload": {},
                "idempotency_key": task_id,
                "retry_count": 0,
                "max_retries": 0,
                "failure_category": "cancelled" if status == "cancelled" else None,
                "heartbeat_at": created_at,
                "duration_seconds": duration,
                "events": [{"status": status, "message": "done", "at": created_at}],
                "created_at": created_at,
                "started_at": created_at,
                "finished_at": created_at,
                "result": {"matched_count": 1},
                "error": None,
            }
        )

    succeeded = authed.get(
        "/api/v1/tasks?page=1&page_size=10&name=alias.strategy&status=succeeded&sort=duration_seconds&order=desc",
        headers=tenant_headers(authed),
    ).get_json()["data"]
    canceled = authed.get("/api/v1/tasks?name=alias.strategy&status=canceled", headers=tenant_headers(authed)).get_json()["data"]

    assert [item["id"] for item in succeeded["items"][:2]] == ["task-alias-new", "task-alias-old"]
    assert {item["lifecycle_status"] for item in succeeded["items"]} == {"succeeded"}
    assert canceled["items"][0]["id"] == "task-alias-cancelled"
    assert canceled["items"][0]["lifecycle_status"] == "canceled"


def test_task_center_cancels_pending_task_and_marks_stale_task(client):
    from backend.infrastructure.tasks.queue import save_task

    authed = login_as(client, "editor_task_lifecycle")
    save_task(
        {
            "id": "task-cancel-me",
            "name": "market.sync",
            "tenant_id": 1,
            "status": "pending",
            "payload": {},
            "idempotency_key": "task-cancel-me",
            "retry_count": 0,
            "max_retries": 0,
            "failure_category": None,
            "heartbeat_at": None,
            "duration_seconds": None,
            "events": [{"status": "queued", "message": "task accepted", "at": "2026-05-04T09:00:00"}],
            "created_at": "2026-05-04T09:00:00",
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
        }
    )
    save_task(
        {
            "id": "task-stale-me",
            "name": "scan.strategy",
            "tenant_id": 1,
            "status": "running",
            "payload": {},
            "idempotency_key": "task-stale-me",
            "retry_count": 0,
            "max_retries": 0,
            "failure_category": None,
            "heartbeat_at": "2026-05-04T00:00:00",
            "duration_seconds": None,
            "events": [{"status": "running", "message": "worker started", "at": "2026-05-04T00:00:00"}],
            "created_at": "2026-05-04T00:00:00",
            "started_at": "2026-05-04T00:00:00",
            "finished_at": None,
            "result": None,
            "error": None,
        }
    )

    cancel_response = authed.post(
        "/api/v1/tasks/task-cancel-me/cancel",
        json={},
        headers=tenant_headers(authed, include_csrf=True),
    )
    cancelled = cancel_response.get_json()["data"]
    stale_response = authed.get("/api/v1/tasks?page=1&page_size=10&status=stale", headers=tenant_headers(authed))
    stale_items = stale_response.get_json()["data"]["items"]

    assert cancel_response.status_code == 200
    assert cancelled["status"] == "cancelled"
    assert cancelled["failure_category"] == "cancelled"
    assert cancelled["finished_at"]
    assert stale_response.status_code == 200
    assert any(item["id"] == "task-stale-me" and item["failure_category"] == "stale" for item in stale_items)


def test_readiness_includes_task_health_summary(client):
    from backend.infrastructure.tasks.queue import save_task

    save_task(
        {
            "id": "task-readiness-stale",
            "name": "scan.strategy",
            "tenant_id": 1,
            "status": "running",
            "payload": {},
            "idempotency_key": "task-readiness-stale",
            "retry_count": 0,
            "max_retries": 0,
            "failure_category": None,
            "heartbeat_at": "2026-05-04T00:00:00",
            "duration_seconds": None,
            "events": [{"status": "running", "message": "worker started", "at": "2026-05-04T00:00:00"}],
            "created_at": "2026-05-04T00:00:00",
            "started_at": "2026-05-04T00:00:00",
            "finished_at": None,
            "result": None,
            "error": None,
        }
    )

    response = client.get("/api/v1/readiness")
    data = response.get_json()["data"]

    assert response.status_code in {200, 503}
    assert data["checks"]["tasks"] is True
    assert data["tasks"]["stale"] >= 1
    assert data["detail"] == "internal readiness details require admin access"
    assert "database" not in data

    authed = login_as(client, "admin_internal_readiness", role="admin")
    internal = authed.get("/api/v1/monitoring/readiness", headers=tenant_headers(authed))
    internal_data = internal.get_json()["data"]

    assert internal.status_code == 200
    assert internal_data["tasks"]["by_failure_category"]["stale"] >= 1
    assert "database" in internal_data
    assert "repository_backends" in internal_data


def test_monitoring_uses_sqlite_health_for_local_sqlite_repositories(client):
    authed = login_as(client, "admin_monitoring_sqlite", role="admin")

    response = authed.get("/api/v1/monitoring/overview", headers=tenant_headers(authed))
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["database"]["ok"] is True
    assert data["database"]["backend"] == "sqlite"
    assert set(data["database"]["repository_backends"].values()) == {"sqlite"}
    assert data["signal_review"]["schema_version"] == "signal-review-health/v1"
    assert data["signal_review"]["complete_rate"] == 1



def test_scan_results_expose_market_data_quality_on_items(client):
    authed = login_as(client, "editor_scan_quality")

    create_response = authed.post(
        "/api/v1/scans",
        json={"strategy_code": "2560", "params": {}},
        headers=tenant_headers(authed, include_csrf=True),
    )
    scan_id = create_response.get_json()["data"]["id"]

    from backend.infrastructure.tasks.queue import update_task

    update_task(
        scan_id,
        {
            "status": "completed",
            "result": {
                "market_data": {
                    "provider": "akshare",
                    "primary_provider": "mootdx",
                    "actual_provider": "akshare",
                    "provider_chain": ["mootdx", "akshare"],
                    "fallback_used": True,
                    "data_quality": "fallback",
                    "errors": [],
                    "healthy": True,
                    "sample_symbols": [
                        {
                            "symbol": "000001",
                            "name": "平安银行",
                            "exchange": "SZ",
                            "market": "A",
                            "market_data_source": "akshare",
                            "data_quality": "fallback",
                            "fallback_used": True,
                        }
                    ],
                }
            },
        },
    )

    response = authed.get(f"/api/v1/scans/{scan_id}/results", headers=tenant_headers(authed))
    data = response.get_json()

    assert response.status_code == 200
    assert data["data"]["market_data"]["actual_provider"] == "akshare"
    assert data["data"]["market_data"]["data_quality"] == "fallback"
    assert data["data"]["items"][0]["market_data_source"] == "akshare"
    assert data["data"]["items"][0]["data_quality"] == "fallback"
    assert data["data"]["items"][0]["explanation"]["schema_version"] == "scan-explanation/v2"
    assert data["data"]["items"][0]["explanation"]["risk_level"] == "medium"
    assert data["data"]["items"][0]["explanation"]["quality_gate"]["quality_reason"] == "degraded_market_data"


def test_scan_results_use_registered_strategy_before_market_sample(client, monkeypatch):
    from backend.application import scan_api_service
    from backend.repositories import scan_repo

    class FakeStrategy:
        code = "2560"

        def scan(self, target_date=None):
            assert target_date == "2026-05-04"
            return [
                {
                    "code": "000888",
                    "name": "Strategy Pick",
                    "pick_price": 12.3,
                    "signal": "策略信号",
                    "reason_tag": "策略信号",
                    "risk_score": 18,
                    "total_score": 91,
                }
            ]

    monkeypatch.setattr(scan_api_service.registry, "get", lambda code: FakeStrategy() if code == "2560" else None)
    authed = login_as(client, "editor_scan_registry")

    create_response = authed.post(
        "/api/v1/scans",
        json={"strategy_code": "2560", "params": {"trade_date": "2026-05-04"}},
        headers=tenant_headers(authed, include_csrf=True),
    )
    scan_id = create_response.get_json()["data"]["id"]
    response = authed.get(f"/api/v1/scans/{scan_id}/results", headers=tenant_headers(authed))
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["strategy_runner"] == "registry"
    assert data["items"][0]["symbol"] == "000888"
    assert data["items"][0]["explanation"]["strategy_code"] == "2560"
    persisted = scan_repo.get_scan_bundle(1, scan_id)
    assert persisted["task"]["task_no"] == scan_id
    assert persisted["items"][0]["signals"]["symbol"] == "000888"

    monkeypatch.setattr(scan_api_service, "get_task", lambda task_id: None)
    persisted_response = authed.get(f"/api/v1/scans/{scan_id}/results", headers=tenant_headers(authed))
    persisted_data = persisted_response.get_json()["data"]

    assert persisted_response.status_code == 200
    assert persisted_data["persistent"] is True
    assert persisted_data["strategy_runner"] == "registry"
    assert persisted_data["items"][0]["symbol"] == "000888"


def test_scan_market_sample_carries_security_type_and_bar_interval(monkeypatch):
    from backend.application.scan_api_service import ScanApiService
    from backend.infrastructure.market_data.provider import HealthCheckResult, StockInfo

    class FakeProvider:
        name = "fake"

        def get_stock_list(self):
            return [
                StockInfo(symbol="000001", name="Ping An", exchange="SZ", security_type="stock"),
                StockInfo(symbol="123001", name="Convertible", exchange="SZ", security_type="convertible_bond"),
                StockInfo(symbol="510300", name="ETF", exchange="SH", security_type="etf"),
            ]

        def health_check(self):
            return HealthCheckResult(provider="fake", ok=True)

    from backend.application import scan_api_service

    monkeypatch.setattr(scan_api_service.registry, "get", lambda code: None)
    result = ScanApiService(FakeProvider())._run_scan(
        1,
        "unknown",
        {"security_type": "convertible_bond", "bar_interval": "30m", "adjust": "qfq", "sample_size": 5},
    )

    assert result["params"]["security_type"] == "convertible_bond"
    assert result["params"]["bar_interval"] == "30m"
    assert result["params"]["adjust"] == "none"
    assert result["market_data"]["sample_symbols"][0]["symbol"] == "123001"
    assert result["market_data"]["sample_symbols"][0]["security_type"] == "convertible_bond"
    assert result["market_data"]["sample_symbols"][0]["bar_interval"] == "30m"
    assert result["market_data"]["sample_symbols"][0]["strategy_runner"] == "market_sample"
    assert result["market_data"]["sample_symbols"][0]["executable_signal"] is False
    assert result["market_data"]["sample_symbols"][0]["quality_gate"]["status"] == "allowed"


def test_scan_can_disable_market_sample_fallback(monkeypatch):
    from backend.application import scan_api_service
    from backend.application.scan_api_service import ScanApiService
    from backend.infrastructure.market_data.provider import HealthCheckResult

    class EmptyStrategy:
        def scan(self, target_date=None):
            return []

    class FakeProvider:
        name = "fake"

        def get_stock_list(self):
            pytest.fail("market sample fallback should be disabled")

        def health_check(self):
            return HealthCheckResult(provider="fake", ok=True)

    monkeypatch.setattr(scan_api_service.registry, "get", lambda code: EmptyStrategy())

    result = ScanApiService(FakeProvider())._run_scan(
        1,
        "2560",
        {"disable_market_sample_fallback": True, "sample_size": 5},
    )

    assert result["strategy_runner"] == "registry"
    assert result["market_data"]["sample_symbols"] == []
    assert result["params"]["disable_market_sample_fallback"] is True


def test_scan_accepts_first_limit_up_alias(client, monkeypatch):
    from backend.application import scan_api_service

    seen = {}

    class FakeStrategy:
        code = "FIRST_LIMIT_UP"

        def scan(self, target_date=None):
            return []

    def fake_get(code):
        seen["code"] = code
        return FakeStrategy()

    monkeypatch.setattr(scan_api_service.registry, "get", fake_get)
    authed = login_as(client, "editor_scan_alias")

    response = authed.post(
        "/api/v1/scans",
        json={"strategy_code": "first_limit_up", "params": {}},
        headers=tenant_headers(authed, include_csrf=True),
    )
    payload = response.get_json()["data"]

    assert response.status_code == 202
    assert payload["strategy_code"] == "first_limit_up"
    assert seen["code"] == "FIRST_LIMIT_UP"


def test_market_discovery_returns_breadth_and_data_contract(client):
    authed = login_as(client, "editor_market_discovery")

    response = authed.get("/api/v1/market-discovery?sample_size=3&lookback_days=20", headers=tenant_headers(authed))
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["breadth"]["sampled"] <= 3
    assert "advance_ratio" in data["breadth"]
    assert data["coverage"]["requested_sample_size"] == 3
    assert data["coverage"]["successful"] == data["breadth"]["sampled"]
    assert "success_rate" in data["coverage"]
    assert data["data_contract"]["data_quality"] in {"primary", "fallback", "unknown"}
    assert data["data_quality_summary"]["grade"] in {"primary", "fallback", "unknown"}
    assert isinstance(data["candidate_groups"], list)
    assert isinstance(data["top_movers"], list)


def test_market_discovery_returns_empty_contract_when_stock_list_provider_fails(client, monkeypatch):
    from backend.api_v1.routers import market as market_router

    class FailingStockListProvider(TestMarketProvider):
        name = "broken"

        def get_stock_list(self):
            raise RuntimeError("stock list unavailable")

    monkeypatch.setattr(market_router.service, "market_data_provider", FailingStockListProvider())
    authed = login_as(client, "editor_market_discovery_provider_error")

    response = authed.get("/api/v1/market-discovery?sample_size=3&lookback_days=20", headers=tenant_headers(authed))
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["breadth"]["sampled"] == 0
    assert data["coverage"]["successful"] == 0
    assert data["data_quality_summary"]["research_ready"] is False
    assert "provider_unhealthy" in data["data_quality_summary"]["warnings"]
    assert any("stock list unavailable" in item for item in data["data_contract"]["provider_errors"])


def test_settings_saved_views_and_alerts_are_persisted(client):
    authed = login_as(client, "editor_settings")
    write_headers = tenant_headers(authed, include_csrf=True)
    read_headers = tenant_headers(authed)

    view_response = authed.post(
        "/api/v1/settings/saved-views",
        json={
            "name": "High quality scans",
            "page": "scans",
            "filters": {"risk_level": "low", "data_quality": "primary"},
            "sort": {"field": "score", "order": "desc"},
            "columns": ["symbol", "score"],
        },
        headers=write_headers,
    )
    view = view_response.get_json()["data"]

    assert view_response.status_code == 201
    assert view["id"]
    assert view["filters"]["data_quality"] == "primary"

    views_response = authed.get("/api/v1/settings/saved-views", headers=read_headers)
    views = views_response.get_json()["data"]
    assert views_response.status_code == 200
    assert views["items"][0]["id"] == view["id"]

    alert_response = authed.post(
        "/api/v1/settings/alerts",
        json={
            "name": "Ping An drawdown",
            "target": "000001",
            "rule": {"field": "drawdown_pct", "operator": "<=", "value": -0.05},
            "channels": ["in_app"],
        },
        headers=write_headers,
    )
    alert = alert_response.get_json()["data"]

    assert alert_response.status_code == 201
    assert alert["enabled"] is True
    assert alert["rule"]["field"] == "drawdown_pct"

    alerts_response = authed.get("/api/v1/settings/alerts", headers=read_headers)
    alerts = alerts_response.get_json()["data"]
    assert alerts_response.status_code == 200
    assert alerts["items"][0]["id"] == alert["id"]

    delete_response = authed.delete(f"/api/v1/settings/saved-views/{view['id']}", headers=write_headers)
    assert delete_response.status_code == 200


def test_batch_pick_review_updates_selected_items_and_audits(client):
    from backend.application.audit_log_service import audit_log_service

    authed = login_as(client, "editor_pick_batch")
    headers = tenant_headers(authed, include_csrf=True)
    first = authed.post(
        "/api/v1/picks",
        json={"symbol": "000101", "stock_name": "Batch One", "trade_date": "2026-05-04", "source": "manual"},
        headers=headers,
    ).get_json()["data"]
    second = authed.post(
        "/api/v1/picks",
        json={"symbol": "000102", "stock_name": "Batch Two", "trade_date": "2026-05-04", "source": "manual"},
        headers=headers,
    ).get_json()["data"]

    response = authed.patch(
        "/api/v1/picks/batch/review",
        json={"ids": [first["id"], second["id"]], "status": "watching", "risk_level": "medium", "watch_flag": True},
        headers=headers,
    )
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["updated"] == 2
    assert {item["status"] for item in data["items"]} == {"watching"}
    assert all(item["watch_flag"] for item in data["items"])
    logs = audit_log_service.list_logs(tenant_id=1, action="pick.review.batch_update")
    assert logs["items"]
    assert logs["items"][0]["detail"]["updated"] == 2



def test_create_scan_rejects_viewer_role(client):
    viewer = login_as(client, "viewer_scan", role="viewer")

    response = viewer.post(
        "/api/v1/scans",
        json={"strategy_code": "2560", "params": {}},
        headers=tenant_headers(viewer, include_csrf=True),
    )
    data = response.get_json()

    assert response.status_code == 403
    assert data["code"] == 403



def test_picks_list_returns_empty_page_for_authenticated_user(client):
    authed = login_as(client, "editor_picks")

    response = authed.get("/api/v1/picks", headers={"X-Tenant-ID": "1"})
    data = response.get_json()

    assert response.status_code == 200
    assert data["data"]["items"] == []
    assert data["data"]["tenant_id"] == 1


def test_picks_list_supports_date_and_source_filters(client):
    authed = login_as(client, "editor_picks_filters")

    for payload in [
        {"symbol": "000001", "stock_name": "Manual Old", "trade_date": "2026-05-01", "source": "manual"},
        {"symbol": "000002", "stock_name": "Scan New", "trade_date": "2026-05-03", "source": "scan"},
        {"symbol": "000003", "stock_name": "Manual New", "trade_date": "2026-05-04", "source": "manual"},
    ]:
        response = authed.post(
            "/api/v1/picks",
            json=payload,
            headers=tenant_headers(authed, include_csrf=True),
        )
        assert response.status_code == 201

    response = authed.get(
        "/api/v1/picks?source=manual&from_date=2026-05-02&to_date=2026-05-04",
        headers=tenant_headers(authed),
    )
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["total"] == 1
    assert data["items"][0]["symbol"] == "000003"

    bad_response = authed.get("/api/v1/picks?from_date=2026/05/02", headers=tenant_headers(authed))
    assert bad_response.status_code == 400


def test_picks_list_and_stock_context_support_symbol_drilldown(client):
    authed = login_as(client, "editor_symbol_drilldown")
    headers = tenant_headers(authed, include_csrf=True)
    created = authed.post(
        "/api/v1/picks",
        json={
            "symbol": "000777",
            "stock_name": "Context Stock",
            "trade_date": "2026-05-04",
            "source": "manual",
            "strategy_code": "2560",
            "data_quality": "primary",
            "market_data_source": "akshare",
        },
        headers=headers,
    )
    assert created.status_code == 201

    list_response = authed.get("/api/v1/picks?symbol=000777", headers=tenant_headers(authed))
    listed = list_response.get_json()["data"]
    assert list_response.status_code == 200
    assert listed["total"] == 1
    assert listed["items"][0]["symbol"] == "000777"

    context_response = authed.get("/api/v1/stocks/000777/context", headers=tenant_headers(authed))
    context = context_response.get_json()["data"]
    assert context_response.status_code == 200
    assert context["in_pool"] is True
    assert context["review_markers"]["has_pick"] is True
    assert context["history"][0]["market_data_source"] == "akshare"



def test_viewer_can_read_but_cannot_write_picks(client):
    viewer = login_as(client, "viewer_picks", role="viewer")

    read_response = viewer.get("/api/v1/picks", headers={"X-Tenant-ID": "1"})
    assert read_response.status_code == 200

    write_response = viewer.post(
        "/api/v1/picks",
        json={"symbol": "000001", "stock_name": "viewer blocked", "source": "manual"},
        headers=tenant_headers(viewer, include_csrf=True),
    )
    data = write_response.get_json()

    assert write_response.status_code == 403
    assert data["code"] == 403



def test_pick_create_and_review_update_write_audit_logs(client):
    from backend.application.audit_log_service import audit_log_service

    authed = login_as(client, "editor_pick_audit")

    create_response = authed.post(
        "/api/v1/picks",
        json={"symbol": "000001", "stock_name": "Ping An", "trade_date": "2026-05-03", "source": "manual"},
        headers=tenant_headers(authed, include_csrf=True),
    )
    created = create_response.get_json()["data"]

    assert create_response.status_code == 201
    create_logs = audit_log_service.list_logs(tenant_id=1, action="pick.create")
    assert create_logs["items"]
    assert create_logs["items"][0]["resource_id"] == str(created["id"])
    assert create_logs["items"][0]["detail"]["symbol"] == "000001"

    review_response = authed.patch(
        f"/api/v1/picks/{created['id']}/review",
        json={"status": "verified", "deal_status": "filled", "return_pct": 3.5, "review_comment": "ok"},
        headers=tenant_headers(authed, include_csrf=True),
    )
    reviewed = review_response.get_json()["data"]

    assert review_response.status_code == 200
    assert reviewed["status"] == "verified"
    review_logs = audit_log_service.list_logs(tenant_id=1, action="pick.review.update")
    assert review_logs["items"]
    assert review_logs["items"][0]["resource_id"] == str(created["id"])
    assert review_logs["items"][0]["detail"]["deal_status"] == "filled"



def test_create_report_returns_report_payload_for_editor(client):
    authed = login_as(client, "editor_report")

    response = authed.post(
        "/api/v1/reports",
        json={"symbol": "000001", "title": "平安银行研究", "content": "test"},
        headers=tenant_headers(authed, include_csrf=True),
    )
    data = response.get_json()

    assert response.status_code == 201
    assert data["data"]["tenant_id"] == 1
    assert data["data"]["symbol"] == "000001"


def test_report_create_list_and_detail_are_persisted(client):
    authed = login_as(client, "editor_report_persisted")
    headers = tenant_headers(authed)

    created_response = authed.post(
        "/api/v1/reports",
        json={
            "symbol": "000002",
            "title": "Persisted report",
            "content": "persistent content",
            "analysis_date": "2026-05-04",
            "total_score": 88,
        },
        headers=tenant_headers(authed, include_csrf=True),
    )
    created = created_response.get_json()["data"]

    assert created_response.status_code == 201
    assert created["id"]
    assert created["content"] == "persistent content"

    listed_response = authed.get("/api/v1/reports?symbol=000002", headers=headers)
    listed = listed_response.get_json()["data"]
    assert listed_response.status_code == 200
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == created["id"]
    assert listed["items"][0]["content"] == "persistent content"

    detail_response = authed.get(f"/api/v1/reports/{created['id']}", headers=headers)
    detail = detail_response.get_json()["data"]
    assert detail_response.status_code == 200
    assert detail["id"] == created["id"]
    assert detail["symbol"] == "000002"
    assert detail["content"] == "persistent content"


def test_report_summary_export_supports_csv_and_json(client):
    import json

    authed = login_as(client, "editor_report_export")
    headers = tenant_headers(authed)

    csv_response = authed.get("/api/v1/reports/summary/export?period=week&format=csv", headers=headers)
    assert csv_response.status_code == 200
    assert "text/csv" in csv_response.headers["Content-Type"]
    assert "report-summary-week.csv" in csv_response.headers["Content-Disposition"]
    assert "section,metric,value" in csv_response.get_data(as_text=True)

    json_response = authed.get("/api/v1/reports/summary/export?period=month&format=json", headers=headers)
    payload = json.loads(json_response.get_data(as_text=True))
    assert json_response.status_code == 200
    assert "application/json" in json_response.headers["Content-Type"]
    assert "report-summary-month.json" in json_response.headers["Content-Disposition"]
    assert payload["period"] == "month"
    assert "summary" in payload


def test_report_summary_distinguishes_market_data_quality(client):
    authed = login_as(client, "editor_report_quality")

    trade_date = date.today().isoformat()
    for payload in [
        {"symbol": "000001", "stock_name": "Primary", "source": "manual", "data_quality": "primary", "market_data_source": "akshare"},
        {"symbol": "000002", "stock_name": "Fallback", "source": "scan", "data_quality": "primary", "market_data_source": "akshare", "fallback_used": True},
        {"symbol": "000003", "stock_name": "Fallback 2", "source": "scan", "data_quality": "primary", "market_data_source": "akshare", "fallback_used": True},
    ]:
        response = authed.post(
            "/api/v1/picks",
            json={**payload, "trade_date": trade_date, "strategy_code": "2560"},
            headers=tenant_headers(authed, include_csrf=True),
        )
        assert response.status_code == 201

    response = authed.get("/api/v1/reports/summary?period=week", headers=tenant_headers(authed))
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["summary"]["data_quality"]["primary"] == 1
    assert data["summary"]["data_quality"]["fallback"] == 2
    assert data["summary"]["data_quality"]["mock"] == 0
    assert data["groups"][0]["data_quality"]["primary"] == 1
    assert data["groups"][0]["data_quality"]["fallback"] == 2
    assert data["drilldowns"]["picks"]["page"] == "picks"
    assert data["groups"][0]["drilldowns"]["picks"]["filters"]["strategy_code"] == "2560"
    assert data["groups"][0]["drilldowns"]["backtests"]["page"] == "strategies"
    assert data["groups"][0]["data_quality"]["mock"] == 0
    assert data["attribution"]["schema_version"] == "report-attribution/v1"
    assert data["attribution"]["dimensions"]["strategy"][0]["key"] == "2560"
    assert data["attribution"]["dimensions"]["strategy"][0]["total"] == 3
    assert data["feedback"]["schema_version"] == "strategy-feedback/v1"
    assert any(item["type"] == "data_quality" and item["strategy"] == "2560" for item in data["feedback"]["items"])
    quality_keys = {item["key"] for item in data["attribution"]["dimensions"]["data_quality"]}
    assert {"primary", "fallback"} <= quality_keys
    assert data["attribution"]["dimensions"]["source"][0]["drilldown"]["page"] == "picks"


def test_report_summary_export_rejects_unknown_format(client):
    authed = login_as(client, "editor_report_export_bad")

    response = authed.get("/api/v1/reports/summary/export?format=xlsx", headers=tenant_headers(authed))
    data = response.get_json()

    assert response.status_code == 400
    assert data["message"] == "unsupported report export format"



def test_market_sync_requires_admin_role(client):
    editor = login_as(client, "editor_sync", role="editor")
    forbidden = editor.post(
        "/api/v1/market-data/sync",
        json={"symbols": ["000001"]},
        headers=tenant_headers(editor, include_csrf=True),
    )
    forbidden_data = forbidden.get_json()

    assert forbidden.status_code == 403
    assert forbidden_data["code"] == 403

    admin = client.application.test_client()
    login_as(admin, "admin_sync", role="admin")
    allowed = admin.post(
        "/api/v1/market-data/sync",
        json={"symbols": ["000001"]},
        headers=tenant_headers(admin, include_csrf=True),
    )
    allowed_data = allowed.get_json()

    assert allowed.status_code == 202
    assert allowed_data["data"]["tenant_id"] == 1
    assert allowed_data["data"]["name"] == "market.sync"
    task_id = allowed_data["data"]["id"]
    from backend.infrastructure.tasks.queue import get_task
    import time

    for _ in range(60):
        task = get_task(task_id) or {}
        if task.get("status") in {"completed", "failed", "cancelled", "stale"}:
            break
        time.sleep(0.05)


def test_market_sync_persists_local_bars_and_exposes_coverage(client):
    from backend.application.sync_api_service import SyncApiService

    result = SyncApiService(TestMarketProvider())._sync_market_data(["000001"], "2026-05-01", "2026-05-04", "qfq")

    assert result["synced_symbols"] == 1
    assert result["persisted_bars"] >= 1
    assert result["symbols"][0]["last_trade_date"] == "2026-05-04"

    admin = login_as(client, "admin_market_coverage", role="admin")
    response = admin.get("/api/v1/market-data/coverage?keyword=000001", headers=tenant_headers(admin))
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["summary"]["synced_symbols"] == 1
    assert data["summary"]["last_trade_date"] == "2026-05-04"
    assert data["items"][0]["symbol"] == "000001"
    assert data["items"][0]["synced"] is True
    assert data["items"][0]["last_trade_date"] == "2026-05-04"
    assert data["items"][0]["last_trade_time"].startswith("2026-05-04T")
    assert data["items"][0]["adjusts"] == ["qfq"]
    assert data["items"][0]["intervals"] == ["1d"]

    state_response = admin.get("/api/v1/market-data/sync/state?keyword=000001&interval=1d", headers=tenant_headers(admin))
    state_data = state_response.get_json()["data"]

    assert state_response.status_code == 200
    assert state_data["summary"]["success_count"] == 1
    assert state_data["items"][0]["status"] == "success"
    assert state_data["items"][0]["adjust"] == "qfq"
    assert state_data["items"][0]["interval"] == "1d"
    assert state_data["items"][0]["coverage_end_date"] == "2026-05-04"


def test_market_sync_task_events_show_symbol_level_live_log(client, monkeypatch):
    from backend.api_v1.routers import sync as sync_router
    from backend.infrastructure.market_data.fallback_provider import FallbackMarketDataProvider
    from backend.infrastructure.tasks.queue import get_task
    from backend.repositories import market_data_repo, paper_trading_repo

    class ChineseNameProvider(TestMarketProvider):
        def get_stock_list(self):
            return [StockInfo("000001", "平安银行", "SZ")]

    monkeypatch.setattr(sync_router.service, "market_data_provider", FallbackMarketDataProvider([ChineseNameProvider()]))
    market_data_repo.upsert_stocks([{"symbol": "000001", "name": "000001", "exchange": "SZ", "security_type": "stock"}])

    admin = login_as(client, "admin_market_sync_log", role="admin")
    response = admin.post(
        "/api/v1/market-data/sync",
        json={"symbols": ["000001"], "start_date": "2026-05-01", "end_date": "2026-05-04", "adjust": "qfq"},
        headers=tenant_headers(admin, include_csrf=True),
    )
    task_id = response.get_json()["data"]["id"]
    task = {}
    import time

    for _ in range(60):
        task = get_task(task_id) or {}
        if any("同步成功" in (event.get("message") or "") for event in task.get("events") or []):
            break
        time.sleep(0.05)
    messages = [event.get("message", "") for event in task.get("events") or []]

    assert response.status_code == 202
    assert any("数据源 akshare" in message for message in messages), messages
    assert any("000001 平安银行 开始同步" in message for message in messages), messages
    assert any("000001 平安银行 同步成功" in message and "本次获取" in message for message in messages), messages
    assert any("行情同步完成" in message and "本次写入/更新" in message for message in messages), messages


def test_market_sync_keeps_adjust_variants_separate(client):
    from backend.application.sync_api_service import SyncApiService
    from backend.repositories import market_data_repo, paper_trading_repo

    service = SyncApiService(TestMarketProvider())
    service._sync_market_data(["000001"], "2026-05-01", "2026-05-04", "qfq")
    service._sync_market_data(["000001"], "2026-05-01", "2026-05-04", "hfq")

    qfq_bars = market_data_repo.get_daily_bars("000001", "2026-05-01", "2026-05-04", adjust="qfq")
    hfq_bars = market_data_repo.get_daily_bars("000001", "2026-05-01", "2026-05-04", adjust="hfq")
    coverage = market_data_repo.list_coverage(keyword="000001")

    assert qfq_bars
    assert hfq_bars
    assert {bar["adjust"] for bar in qfq_bars} == {"qfq"}
    assert {bar["adjust"] for bar in hfq_bars} == {"hfq"}
    assert {"qfq", "hfq"}.issubset(set(coverage["items"][0]["adjusts"]))


def test_market_sync_passes_none_adjust_to_provider_without_empty_string(client):
    from backend.application.sync_api_service import SyncApiService

    class RecordingProvider(TestMarketProvider):
        def __init__(self):
            self.adjusts = []

        def get_daily_bars(self, symbol, start_date, end_date, adjust="qfq", interval="1d"):
            self.adjusts.append(adjust)
            return super().get_daily_bars(symbol, start_date, end_date, adjust=adjust, interval=interval)

    provider = RecordingProvider()
    SyncApiService(provider)._sync_market_data(["000001"], "2026-05-01", "2026-05-04", "none")

    assert provider.adjusts == ["none"]


def test_market_snapshot_sync_persists_and_exposes_latest_quotes(client):
    from backend.application.sync_api_service import SyncApiService

    result = SyncApiService(TestMarketProvider())._sync_quote_snapshots(["000001", "600519"])

    assert result["snapshot_count"] == 2
    assert result["persisted_snapshots"] == 2

    admin = login_as(client, "admin_market_snapshots", role="admin")
    response = admin.get("/api/v1/market-data/snapshots?keyword=000001", headers=tenant_headers(admin))
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["summary"]["snapshot_count"] == 2
    assert data["items"][0]["symbol"] == "000001"
    assert data["items"][0]["last_price"] is not None


def test_market_sync_incremental_starts_from_local_latest_bar(client):
    from datetime import date, timedelta
    from decimal import Decimal

    from backend.application.sync_api_service import SyncApiService
    from backend.infrastructure.market_data.provider import DailyBar, HealthCheckResult, QuoteSnapshot, StockInfo
    from backend.repositories import market_data_repo

    class RecordingProvider:
        name = "recording"

        def __init__(self):
            self.calls = []

        def get_stock_list(self):
            return [StockInfo("000001", "Ping An", "SZ")]

        def get_daily_bars(self, symbol, start_date, end_date, adjust="qfq", interval="1d"):
            self.calls.append((symbol, start_date, end_date, adjust, interval))
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
            current = start
            bars = []
            while current <= end:
                if current.weekday() < 5:
                    bars.append(DailyBar(symbol, current, Decimal("10"), Decimal("11"), Decimal("9"), Decimal("10.5"), 100, Decimal("1050"), source=self.name))
                current += timedelta(days=1)
            return bars

        def get_quote_snapshots(self, symbols):
            return [QuoteSnapshot(symbol=symbol, trade_time="2026-05-08T09:30:00", last_price=Decimal("10"), open=Decimal("10"), high=Decimal("10"), low=Decimal("10"), source=self.name) for symbol in symbols]

        def get_trading_dates(self, start_date, end_date):
            return []

        def health_check(self):
            return HealthCheckResult(provider=self.name, ok=True)

    market_data_repo.upsert_daily_bars(
        [DailyBar("000001", date(2026, 5, 4), Decimal("10"), Decimal("11"), Decimal("9"), Decimal("10.5"), 100, Decimal("1050"), source="recording")],
        adjust="qfq",
    )
    provider = RecordingProvider()
    result = SyncApiService(provider)._sync_market_data(
        ["000001"],
        "",
        "2026-05-08",
        "qfq",
        tenant_id=1,
        incremental=True,
        bootstrap_days=180,
        correction_days=0,
    )
    states = market_data_repo.list_sync_states(1, keyword="000001")

    assert provider.calls[0][1] == "2026-05-05"
    assert result["incremental"] is True
    assert result["symbols"][0]["window"]["latest_local_trade_date"] == "2026-05-04"
    assert states["items"][0]["last_success_trade_date"] == "2026-05-08"


def test_market_indicator_precompute_and_qfq_repair_tasks(client, monkeypatch):
    from datetime import date, timedelta
    from decimal import Decimal

    from backend.infrastructure.cache.redis_client import get_json
    from backend.infrastructure.market_data.provider import DailyBar, StockInfo
    from backend.infrastructure.tasks.queue import get_task
    from backend.repositories import market_data_repo
    from backend.application import sync_api_service
    from backend.api_v1.routers import sync as sync_router

    monkeypatch.setattr(sync_api_service, "create_fallback_market_data_provider", lambda: TestMarketProvider())
    monkeypatch.setattr(sync_router.service, "market_data_provider", TestMarketProvider())

    market_data_repo.upsert_stocks([StockInfo("000001", "Ping An", "SZ")])
    end = date.today()
    start = end - timedelta(days=95)
    bars = []
    current = start
    index = 0
    while current <= end:
        if current.weekday() < 5:
            close = Decimal("10") + Decimal(index) / Decimal("100")
            bars.append(DailyBar("000001", current, close, close + Decimal("0.1"), close - Decimal("0.1"), close, 1000 + index, close * Decimal("1000"), source="unit"))
            index += 1
        current += timedelta(days=1)
    market_data_repo.upsert_daily_bars(bars, adjust="qfq")

    admin = login_as(client, "admin_indicator_precompute", role="admin")
    precompute_response = admin.post(
        "/api/v1/market-data/indicators/precompute",
        json={"symbols": ["000001"], "adjust": "qfq", "interval": "1d", "lookback_days": 180},
        headers=tenant_headers(admin, include_csrf=True),
    )
    precompute_task = get_task(precompute_response.get_json()["data"]["id"])

    assert precompute_response.status_code == 202
    assert precompute_task["status"] == "completed"
    assert precompute_task["result"]["schema_version"] == "indicator-precompute/2560/v1"
    assert precompute_task["result"]["cached_symbols"] == 1
    cache_index = get_json(precompute_task["result"]["cache_index_key"])
    cache_item = get_json(precompute_task["result"]["items"][0]["cache_key"])
    assert cache_index["symbols"] == ["000001"]
    assert cache_item["ready"] is True
    assert cache_item["ma25"] > 0
    assert cache_item["ma60"] > 0

    repair_response = admin.post(
        "/api/v1/market-data/qfq/repair",
        json={"symbols": ["000001"], "max_symbols": 1, "correction_days": 3},
        headers=tenant_headers(admin, include_csrf=True),
    )
    repair_task = get_task(repair_response.get_json()["data"]["id"])

    assert repair_response.status_code == 202
    assert repair_task["name"] == "market.qfq.repair"
    assert repair_task["status"] == "completed"
    assert repair_task["result"]["adjust"] == "qfq"


def test_paper_trading_service_creates_order_fill_and_position(client):
    from datetime import datetime
    from decimal import Decimal

    from backend.application.paper_trading_service import PaperTradingService
    from backend.infrastructure.market_data.provider import QuoteSnapshot
    from backend.repositories import market_data_repo, paper_trading_repo

    market_data_repo.upsert_quote_snapshots(
        [
            QuoteSnapshot(
                symbol="000001",
                trade_time=datetime(2026, 5, 5, 9, 30),
                last_price=Decimal("10"),
                open=Decimal("10"),
                high=Decimal("10.5"),
                low=Decimal("9.8"),
                source="unit",
            )
        ]
    )
    result = PaperTradingService().apply_strategy_scan(
        1,
        {"id": 1, "code": "2560"},
        {
            "market_data": {
                "sample_symbols": [
                    {
                        "symbol": "000001",
                        "trade_date": "2026-05-05",
                        "signal": "缩量回踩",
                        "signal_type": "BUY",
                        "signal_subtype": "volume_lock_shrink",
                        "volume_phase": "lock_shrink",
                        "score": 88,
                        "total_score": 88,
                        "ma60": 9.8,
                    },
                    {
                        "symbol": "000002",
                        "trade_date": "2026-05-05",
                        "signal": "低分观察",
                        "signal_subtype": "volume_impulse",
                        "score": 60,
                    },
                ]
            }
        },
        {"cash_per_trade": 10000, "max_paper_positions": 3, "min_signal_score": 80},
    )

    assert result["enabled"] is True
    assert result["orders"][0]["side"] == "BUY"
    assert result["skipped"][0]["reason"] == "score_below_threshold"
    assert result["summary"]["active_positions"] == 1

    authed = login_as(client, "editor_paper_trading")
    positions = authed.get("/api/v1/trading/paper/positions", headers=tenant_headers(authed)).get_json()["data"]
    orders = authed.get("/api/v1/trading/paper/orders", headers=tenant_headers(authed)).get_json()["data"]
    signals = authed.get("/api/v1/trading/signals", headers=tenant_headers(authed)).get_json()["data"]
    links = authed.get("/api/v1/trading/signal-review-links", headers=tenant_headers(authed)).get_json()["data"]

    assert positions["items"][0]["symbol"] == "000001"
    assert positions["items"][0]["quantity"] > 0
    assert orders["items"][0]["symbol"] == "000001"
    assert signals["items"][0]["symbol"] == "000001"
    assert signals["items"][0]["score"] == 88
    assert signals["items"][0]["payload"]["signal_subtype"] == "volume_lock_shrink"
    assert signals["items"][0]["payload"]["volume_phase"] == "lock_shrink"
    assert signals["items"][0]["payload"]["ma60"] == 9.8
    link = paper_trading_repo.get_signal_review_link(1, signals["items"][0]["source_hash"])
    assert link["trade_signal_id"] == signals["items"][0]["id"]
    assert link["pick_id"]
    assert link["buy_order_id"] == orders["items"][0]["id"]
    assert links["items"][0]["source_signal_hash"] == signals["items"][0]["source_hash"]
    assert links["items"][0]["pick_id"] == link["pick_id"]
    assert links["health"]["schema_version"] == "signal-review-health/v1"
    assert links["health"]["status"] == "ok"
    assert links["health"]["complete_rate"] == 1

    market_data_repo.upsert_quote_snapshots(
        [
            QuoteSnapshot(
                symbol="000001",
                trade_time=datetime(2026, 5, 11, 10, 30),
                last_price=Decimal("12.50"),
                open=Decimal("12"),
                high=Decimal("12.8"),
                low=Decimal("11.9"),
                source="unit",
            )
        ]
    )
    mark_response = authed.post(
        "/api/v1/trading/paper/mark-to-market",
        json={},
        headers=tenant_headers(authed, include_csrf=True),
    )
    mark_payload = mark_response.get_json()["data"]
    assert mark_response.status_code == 200
    assert mark_payload["schema_version"] == "paper-mark-to-market/v1"
    assert mark_payload["updated"] == 1
    assert mark_payload["items"][0]["position"]["market_price"] == 12.5

    admin = login_as(client, "admin_paper_reset", role="admin")
    reset_response = admin.post(
        f"/api/v1/trading/paper/accounts/{positions['items'][0]['account_id']}/reset",
        json={},
        headers=tenant_headers(admin, include_csrf=True),
    )
    reset_signals = paper_trading_repo.list_trade_signals(1, limit=1)
    reset_links = paper_trading_repo.list_signal_review_links(1, limit=10)
    assert reset_response.status_code == 200
    assert reset_signals[0]["status"] == "reset"
    assert reset_links == []


def test_paper_position_monitor_endpoint_runs_closed_loop(client, monkeypatch):
    from backend.api_v1.routers import trading as trading_router

    calls = []

    class FakeSyncApiService:
        def monitor_paper_positions(self, tenant_id, payload):
            calls.append((tenant_id, payload))
            return {
                "schema_version": "paper-position-monitor/v1",
                "status": "completed",
                "tenant_id": tenant_id,
                "account_id": payload.get("account_id"),
                "position_count": 1,
                "symbol_count": 1,
                "snapshot_sync": {"snapshot_count": 1, "persisted_snapshots": 1, "source": "unit"},
                "accounts": [{"account_id": payload.get("account_id"), "mark_to_market": {"updated": 1}, "exits": {"orders": 1}}],
                "exit_summary": {"orders": 1, "skipped": 0, "blocked": 0},
                "updated_at": "2026-05-12T10:00:00",
            }

    monkeypatch.setattr(trading_router, "SyncApiService", FakeSyncApiService)

    authed = login_as(client, "editor_paper_monitor")
    response = authed.post(
        "/api/v1/trading/paper/monitor-positions",
        json={"sync_snapshots": True, "evaluate_exits": True},
        headers=tenant_headers(authed, include_csrf=True),
    )
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["schema_version"] == "paper-position-monitor/v1"
    assert data["status"] == "completed"
    assert data["snapshot_sync"]["persisted_snapshots"] == 1
    assert data["exit_summary"]["orders"] == 1
    assert calls[0][0] == 1
    assert calls[0][1]["account_id"]
    assert calls[0][1]["sync_snapshots"] is True
    assert calls[0][1]["evaluate_exits"] is True


def test_paper_complete_loop_endpoint_runs_strategy_buy_and_position_monitor(client, monkeypatch):
    from backend.api_v1.routers import trading as trading_router

    strategy_calls = []
    monitor_calls = []

    class FakeStrategyApiService:
        def run_deployed_strategy(self, tenant_id, strategy_id, params):
            strategy_calls.append((tenant_id, strategy_id, params))
            return {
                "production_status": "completed",
                "scan": {"matched_count": 2},
                "paper_trading": {
                    "orders": [{"id": 1}, {"id": 2}],
                    "skipped": [{"symbol": "000002", "reason": "position_exists"}],
                    "blocked": [],
                    "exits": {"orders": [{"id": 9}]},
                },
                "warnings": [],
            }

    class FakeSyncApiService:
        def monitor_paper_positions(self, tenant_id, payload):
            monitor_calls.append((tenant_id, payload))
            return {
                "schema_version": "paper-position-monitor/v1",
                "status": "completed",
                "tenant_id": tenant_id,
                "account_id": payload.get("account_id"),
                "position_count": 2,
                "symbol_count": 2,
                "snapshot_sync": {"snapshot_count": 2, "persisted_snapshots": 2, "source": "unit"},
                "accounts": [{"account_id": payload.get("account_id"), "mark_to_market": {"updated": 2}, "exits": {"orders": 1}}],
                "exit_summary": {"orders": 1, "skipped": 0, "blocked": 0},
                "updated_at": "2026-05-12T10:00:00",
            }

    monkeypatch.setattr(trading_router, "StrategyApiService", FakeStrategyApiService)
    monkeypatch.setattr(trading_router, "SyncApiService", FakeSyncApiService)
    monkeypatch.setattr(
        trading_router.strategy_repo,
        "list_strategies",
        lambda active_only=True: [
            {"id": 11, "code": "2560", "name": "2560", "enabled": True, "lifecycle_status": "deployed", "is_active": 1},
            {"id": 12, "code": "DISABLED", "name": "disabled", "enabled": False, "lifecycle_status": "deployed", "is_active": 1},
        ],
    )

    authed = login_as(client, "editor_paper_complete_loop")
    response = authed.post(
        "/api/v1/trading/paper/complete-loop",
        json={"sync_snapshots": True, "evaluate_exits": True},
        headers=tenant_headers(authed, include_csrf=True),
    )
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["schema_version"] == "paper-complete-loop/v1"
    assert data["status"] == "completed"
    assert data["strategy_summary"]["executed"] == 1
    assert data["strategy_summary"]["buy_orders"] == 2
    assert data["strategy_summary"]["pre_buy_exit_orders"] == 1
    assert data["position_monitor"]["exit_summary"]["orders"] == 1
    assert strategy_calls[0][0] == 1
    assert strategy_calls[0][1] == 11
    assert strategy_calls[0][2]["paper_trade"] is True
    assert strategy_calls[0][2]["paper_account_id"]
    assert monitor_calls[0][1]["sync_snapshots"] is True
    assert monitor_calls[0][1]["evaluate_exits"] is True


def test_paper_signal_api_creates_closed_loop_from_scan_candidate(client):
    from datetime import datetime
    from decimal import Decimal

    from backend.infrastructure.market_data.provider import QuoteSnapshot
    from backend.repositories import market_data_repo, paper_trading_repo

    market_data_repo.upsert_quote_snapshots(
        [
            QuoteSnapshot(
                symbol="000003",
                trade_time=datetime(2026, 5, 5, 9, 35),
                last_price=Decimal("8"),
                open=Decimal("8"),
                high=Decimal("8.2"),
                low=Decimal("7.9"),
                source="unit",
            )
        ]
    )
    authed = login_as(client, "editor_paper_signal_api")
    response = authed.post(
        "/api/v1/trading/paper/apply-signal",
        json={
            "strategy_code": "2560",
            "candidate": {
                "symbol": "000003",
                "stock_name": "测试股份",
                "trade_date": "2026-05-05",
                "signal": "缩量回踩",
                "signal_type": "BUY",
                "signal_subtype": "volume_lock_shrink",
                "score": 86,
                "total_score": 86,
                "security_type": "stock",
                "bar_interval": "1d",
            },
            "params": {"cash_per_trade": 8000, "min_signal_score": 0},
            "source_context": {"scan_id": "scan-api-test", "scan_result_index": 0, "scan_params": {"strategy_code": "2560"}},
        },
        headers=tenant_headers(authed, include_csrf=True),
    )
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["orders"][0]["symbol"] == "000003"
    assert data["orders"][0]["side"] == "BUY"
    signals = authed.get("/api/v1/trading/signals", headers=tenant_headers(authed)).get_json()["data"]["items"]
    signal = next(item for item in signals if item["symbol"] == "000003")
    assert signal["payload"]["source_context"]["scan_id"] == "scan-api-test"
    link = paper_trading_repo.get_signal_review_link(1, signal["source_hash"])
    assert link["trade_signal_id"] == signal["id"]
    assert link["pick_id"]
    assert link["buy_order_id"] == data["orders"][0]["id"]
    assert link["metadata"]["source_context"]["scan_id"] == "scan-api-test"


def test_paper_signal_api_blocks_mock_market_data_when_quality_gate_enabled(client):
    authed = login_as(client, "editor_paper_signal_quality")
    response = authed.post(
        "/api/v1/trading/paper/apply-signal",
        json={
            "strategy_code": "2560",
            "candidate": {
                "symbol": "000004",
                "stock_name": "Mock 股份",
                "trade_date": "2026-05-05",
                "signal": "缩量回踩",
                "signal_type": "BUY",
                "signal_subtype": "volume_lock_shrink",
                "score": 90,
                "total_score": 90,
                "data_quality": "mock",
                "market_data_source": "mock",
            },
            "params": {"cash_per_trade": 8000, "min_signal_score": 0, "enforce_market_data_quality_gate": True},
        },
        headers=tenant_headers(authed, include_csrf=True),
    )
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["orders"] == []
    assert data["blocked"][0]["reason"] == "mock_market_data"


def test_paper_signal_api_blocks_non_executable_scan_sample(client):
    authed = login_as(client, "editor_paper_signal_non_exec")
    response = authed.post(
        "/api/v1/trading/paper/apply-signal",
        json={
            "strategy_code": "2560",
            "candidate": {
                "symbol": "000005",
                "stock_name": "样本股份",
                "trade_date": "2026-05-05",
                "signal": "行情样本",
                "signal_type": "WATCH",
                "strategy_runner": "market_sample",
                "executable_signal": False,
                "score": 90,
                "total_score": 90,
                "data_quality": "primary",
                "market_data_source": "unit",
            },
            "params": {"cash_per_trade": 8000, "min_signal_score": 0},
        },
        headers=tenant_headers(authed, include_csrf=True),
    )
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["orders"] == []
    assert data["blocked"][0]["reason"] == "market_sample_not_executable"


def test_paper_trading_persists_convertible_bond_interval_and_lot_size(client):
    from datetime import datetime
    from decimal import Decimal

    from backend.application.paper_trading_service import PaperTradingService
    from backend.infrastructure.market_data.provider import QuoteSnapshot
    from backend.repositories import market_data_repo

    market_data_repo.upsert_quote_snapshots(
        [
            QuoteSnapshot(
                symbol="123001",
                trade_time=datetime(2026, 5, 5, 10, 30),
                last_price=Decimal("100"),
                open=Decimal("99"),
                high=Decimal("101"),
                low=Decimal("98"),
                source="unit",
            )
        ]
    )
    result = PaperTradingService().apply_strategy_scan(
        1,
        {"id": 2, "code": "bond_t0", "target_security_type": "convertible_bond", "bar_interval": "15m"},
        {
            "market_data": {
                "sample_symbols": [
                    {
                        "symbol": "123001",
                        "trade_date": "2026-05-05",
                        "signal": "intraday bond match",
                        "security_type": "convertible_bond",
                        "bar_interval": "15m",
                    }
                ]
            }
        },
        {"cash_per_trade": 1000, "max_paper_positions": 3},
    )

    assert result["enabled"] is True
    assert result["orders"][0]["quantity"] == 10
    assert result["orders"][0]["security_type"] == "convertible_bond"
    assert result["orders"][0]["bar_interval"] == "15m"
    assert result["summary"]["active_positions"] == 1

    authed = login_as(client, "editor_paper_trading_bond")
    positions = authed.get("/api/v1/trading/paper/positions", headers=tenant_headers(authed)).get_json()["data"]
    signals = authed.get("/api/v1/trading/signals", headers=tenant_headers(authed)).get_json()["data"]

    assert positions["items"][0]["security_type"] == "convertible_bond"
    assert positions["items"][0]["bar_interval"] == "15m"
    assert signals["items"][0]["security_type"] == "convertible_bond"
    assert signals["items"][0]["bar_interval"] == "15m"


def test_paper_trading_generates_technical_exit_from_local_ma60(client, monkeypatch):
    from datetime import date, datetime, timedelta
    from decimal import Decimal

    from backend.application import paper_trading_service
    from backend.application.paper_trading_service import PaperTradingService
    from backend.infrastructure.market_data.provider import DailyBar, QuoteSnapshot
    from backend.repositories import market_data_repo, paper_trading_repo

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 5, 5)

    monkeypatch.setattr(paper_trading_service, "date", FixedDate)
    service = PaperTradingService()
    trade_time = datetime(2026, 5, 5, 10, 0)
    market_data_repo.upsert_quote_snapshots(
        [
            QuoteSnapshot(
                symbol="000001",
                trade_time=trade_time,
                last_price=Decimal("10"),
                open=Decimal("10"),
                high=Decimal("10.2"),
                low=Decimal("9.8"),
                source="unit",
            )
        ]
    )
    buy_result = service.apply_strategy_scan(
        1,
        {"id": 3, "code": "2560"},
        {
            "market_data": {
                "sample_symbols": [
                    {"symbol": "000001", "trade_date": "2026-05-05", "signal": "缩量回踩", "score": 88, "total_score": 88}
                ]
            }
        },
        {"cash_per_trade": 10000, "max_paper_positions": 3, "allow_t0": True},
    )
    account_id = buy_result["account"]["id"]
    start = date(2026, 2, 5)
    bars = []
    for index in range(90):
        trade_date = start + timedelta(days=index)
        close = Decimal("10.00")
        if index == 89:
            close = Decimal("9.50")
        bars.append(
            DailyBar(
                symbol="000001",
                trade_date=trade_date,
                open=close,
                high=close + Decimal("0.10"),
                low=close - Decimal("0.10"),
                close=close,
                volume=1000,
                amount=close * Decimal("1000"),
                source="unit",
            )
        )
    market_data_repo.upsert_daily_bars(bars, adjust="qfq")
    market_data_repo.upsert_quote_snapshots(
        [
            QuoteSnapshot(
                symbol="000001",
                trade_time=trade_time,
                last_price=Decimal("9.5"),
                open=Decimal("9.5"),
                high=Decimal("9.6"),
                low=Decimal("9.4"),
                source="unit",
            )
        ]
    )

    exit_result = service.apply_strategy_scan(
        1,
        {"id": 3, "code": "2560"},
        {"market_data": {"sample_symbols": []}},
        {"paper_account_id": account_id, "allow_t0": True, "technical_exit_enabled": True},
    )

    assert exit_result["exits"]["orders"][0]["side"] == "SELL"
    assert exit_result["exits"]["orders"][0]["reason"] == "ma60_breakdown"
    assert exit_result["summary"]["active_positions"] == 0
    signals = paper_trading_repo.list_trade_signals(1, limit=1)
    link = paper_trading_repo.get_signal_review_link(1, signals[0]["source_hash"])
    assert signals[0]["status"] == "closed"
    assert link["status"] == "closed"
    assert link["sell_order_id"] == exit_result["exits"]["orders"][0]["id"]


def test_strategy_production_run_blocks_without_realtime_snapshot(client):
    authed = login_as(client, "editor_production_gate")
    strategies_response = authed.get("/api/v1/strategies", headers=tenant_headers(authed))
    strategy = next(item for item in strategies_response.get_json()["data"]["items"] if item["code"] == "2560")

    response = authed.post(
        f"/api/v1/strategies/{strategy['id']}/production-run",
        json={"params": {"sample_size": 5}},
        headers=tenant_headers(authed, include_csrf=True),
    )
    data = response.get_json()["data"]

    assert response.status_code == 202
    assert data["production_contract"]["data_policy"] == "local_snapshot_and_history_first"
    assert data["production_contract"]["local_only_required"] is True
    assert data["production_contract"]["security_type"] == "stock"
    assert data["production_contract"]["bar_interval"] == "1d"
    assert data["production_contract"]["adjust"] == "qfq"
    assert data["production_contract"]["local_coverage"]["security_type"] == "stock"
    assert data["params"]["local_only"] is True

    from backend.infrastructure.tasks.queue import get_task

    task = get_task(data["task"]["id"])
    assert task["status"] == "completed"
    assert task["result"]["production_status"] == "blocked_no_snapshot"
    assert task["result"]["production_contract"]["local_only_required"] is True
    assert task["result"]["scan_params"]["local_only"] is True
    assert task["result"]["scan_params"]["local_coverage"]["security_type"] == "stock"
    assert task["result"]["warnings"]


def test_market_sync_all_uses_plan_and_child_batches(client, monkeypatch):
    from backend.api_v1.routers import sync as sync_router

    monkeypatch.setattr(sync_router.service, "market_data_provider", TestMarketProvider())

    admin = login_as(client, "admin_market_sync_plan", role="admin")
    response = admin.post(
        "/api/v1/market-data/sync",
        json={
            "symbols": ["all"],
            "start_date": "2026-05-01",
            "end_date": "2026-05-04",
            "adjust": "qfq",
            "batch_size": 2,
        },
        headers=tenant_headers(admin, include_csrf=True),
    )
    data = response.get_json()["data"]

    assert response.status_code == 202
    assert data["name"] == "market.sync.plan"

    from backend.infrastructure.tasks.queue import get_task

    task = get_task(data["id"])
    assert task["status"] == "completed"
    assert task["result"]["batch_count"] == 3
    assert len(task["result"]["child_tasks"]) == 3


def test_strategy_production_run_blocks_without_local_history(client):
    from backend.application.sync_api_service import SyncApiService

    SyncApiService(TestMarketProvider())._sync_quote_snapshots(["000001"])
    authed = login_as(client, "editor_production_history_gate")
    strategies_response = authed.get("/api/v1/strategies", headers=tenant_headers(authed))
    strategy = next(item for item in strategies_response.get_json()["data"]["items"] if item["code"] == "2560")

    response = authed.post(
        f"/api/v1/strategies/{strategy['id']}/production-run",
        json={"params": {"sample_size": 5}},
        headers=tenant_headers(authed, include_csrf=True),
    )
    data = response.get_json()["data"]

    from backend.infrastructure.tasks.queue import get_task

    task = get_task(data["task"]["id"])
    assert task["status"] == "completed"
    assert task["result"]["production_status"] == "blocked_no_history"
    assert task["result"]["local_coverage"]["synced_symbols"] == 0
    assert task["result"]["local_coverage"]["security_type"] == "stock"
    assert task["result"]["local_coverage"]["adjust"] == "qfq"
    assert task["result"]["scan_params"]["bar_interval"] == "1d"
    assert task["result"]["scan_params"]["adjust"] == "qfq"
    assert task["result"]["scan_params"]["local_only"] is True


def test_strategy_production_run_carries_local_contract_into_scan_params(client, monkeypatch):
    from datetime import date, datetime
    from decimal import Decimal

    from backend.application import strategy_api_service
    from backend.infrastructure.market_data.provider import DailyBar, QuoteSnapshot
    from backend.repositories import market_data_repo

    class EmptyStrategy:
        def scan(self, target_date=None):
            return []

    monkeypatch.setattr(strategy_api_service.registry, "get", lambda code: EmptyStrategy())
    market_data_repo.upsert_quote_snapshots(
        [
            QuoteSnapshot(
                "000001",
                datetime(2026, 5, 5, 9, 30, 0),
                Decimal("10"),
                Decimal("10"),
                Decimal("10.5"),
                Decimal("9.8"),
                source="unit",
            )
        ]
    )
    market_data_repo.upsert_daily_bars(
        [
            DailyBar(
                "000001",
                date(2026, 5, 4),
                Decimal("10"),
                Decimal("10.5"),
                Decimal("9.8"),
                Decimal("10.2"),
                1000,
                Decimal("10200"),
                source="unit",
            )
        ],
        adjust="qfq",
    )
    authed = login_as(client, "editor_production_scan_contract")
    strategies_response = authed.get("/api/v1/strategies", headers=tenant_headers(authed))
    strategy = next(item for item in strategies_response.get_json()["data"]["items"] if item["code"] == "2560")

    response = authed.post(
        f"/api/v1/strategies/{strategy['id']}/production-run",
        json={"params": {"sample_size": 5, "bar_interval": "1d", "adjust": "qfq", "paper_trade": False}},
        headers=tenant_headers(authed, include_csrf=True),
    )
    data = response.get_json()["data"]

    from backend.infrastructure.tasks.queue import get_task

    task = get_task(data["task"]["id"])
    result = task["result"]

    assert response.status_code == 202
    assert data["params"]["local_only"] is True
    assert data["production_contract"]["local_coverage"]["coverage_ratio"] == 1
    assert result["production_status"] == "completed"
    assert result["scan_params"]["security_type"] == "stock"
    assert result["scan_params"]["bar_interval"] == "1d"
    assert result["scan_params"]["adjust"] == "qfq"
    assert result["scan_params"]["local_only"] is True
    assert result["scan_params"]["disable_market_sample_fallback"] is True
    assert result["scan_params"]["local_coverage"]["coverage_ratio"] == 1
    assert result["scan"]["params"]["local_only"] is True
    assert result["scan"]["params"]["local_coverage"]["security_type"] == "stock"
    assert result["scan"]["market_data"]["sample_symbols"] == []



def test_user_id_header_must_match_authenticated_user(client):
    authed = login_as(client, "editor_uid")

    response = authed.get(
        "/api/v1/strategies",
        headers=tenant_headers(authed, extra={"X-User-ID": "999"}),
    )
    data = response.get_json()

    assert response.status_code == 401
    assert data["code"] == 401



def test_logout_revokes_api_access(client):
    authed = login_as(client, "editor_logout")
    assert get_auth_token(authed)

    logout_response = authed.get("/logout", follow_redirects=True)
    assert logout_response.status_code == 200

    response = authed.get("/api/v1/strategies", headers={"X-Tenant-ID": "1"})
    data = response.get_json()

    assert response.status_code == 401
    assert data["code"] == 401
    assert get_auth_token(authed) is None



def test_inactive_user_session_is_rejected_and_deleted(client):
    from backend.repositories import sessions_repo, users_repo

    authed = login_as(client, "editor_inactive")
    token = get_auth_token(authed)
    assert token

    user = users_repo.get_user_by_username("editor_inactive")
    users_repo.set_user_active(user["id"], False)

    response = authed.get("/api/v1/strategies", headers={"X-Tenant-ID": "1"})
    data = response.get_json()

    assert response.status_code == 401
    assert data["code"] == 401
    assert sessions_repo.get_session(token) is None



def test_expired_session_is_rejected_and_deleted(client):
    from backend.repositories import sessions_repo, users_repo

    authed = login_as(client, "editor_expired")
    token = get_auth_token(authed)
    assert token

    user = users_repo.get_user_by_username("editor_expired")
    sessions_repo.create_session("expired-token", user["id"], "2000-01-01 00:00:00")
    sessions_repo.delete_session(token)
    with authed.session_transaction() as current_session:
        current_session["auth_token"] = "expired-token"

    response = authed.get("/api/v1/strategies", headers={"X-Tenant-ID": "1"})
    data = response.get_json()

    assert response.status_code == 401
    assert data["code"] == 401
    assert sessions_repo.get_session("expired-token") is None



def test_tampered_session_token_is_rejected_and_removed_from_flask_session(client):
    authed = login_as(client, "editor_tampered")
    assert get_auth_token(authed)

    with authed.session_transaction() as current_session:
        current_session["auth_token"] = "missing-session-token"

    response = authed.get("/api/v1/strategies", headers={"X-Tenant-ID": "1"})
    data = response.get_json()

    assert response.status_code == 401
    assert data["code"] == 401
    assert get_auth_token(authed) is None



def test_viewer_can_read_but_cannot_write_reports(client):
    viewer = login_as(client, "viewer_reports", role="viewer")

    read_response = viewer.get("/api/v1/reports", headers={"X-Tenant-ID": "1"})
    read_data = read_response.get_json()
    assert read_response.status_code == 200
    assert read_data["code"] == 0

    write_response = viewer.post(
        "/api/v1/reports",
        json={"symbol": "000001", "title": "viewer blocked", "content": "nope"},
        headers=tenant_headers(viewer, include_csrf=True),
    )
    write_data = write_response.get_json()

    assert write_response.status_code == 403
    assert write_data["code"] == 403



def test_user_cannot_access_unbound_tenant(client):
    authed = login_as(client, "editor_unbound_tenant")

    response = authed.get("/api/v1/strategies", headers={"X-Tenant-ID": "2"})
    data = response.get_json()

    assert response.status_code == 403
    assert data["code"] == 403



def test_disabled_tenant_is_rejected(client):
    from backend.repositories import users_repo

    authed = login_as(client, "editor_disabled_tenant")
    users_repo.create_tenant("disabled", "停用租户", status="disabled")
    tenant = users_repo.get_tenant_by_code("disabled")
    user = users_repo.get_user_by_username("editor_disabled_tenant")
    users_repo.bind_user_tenant(user["id"], tenant["id"], "editor")

    response = authed.get("/api/v1/strategies", headers={"X-Tenant-ID": str(tenant["id"])})
    data = response.get_json()

    assert response.status_code == 403
    assert data["code"] == 403



def test_tenant_level_role_overrides_global_role(client):
    from backend.repositories import users_repo

    authed = login_as(client, "admin_viewer_in_tenant", role="admin")
    users_repo.create_tenant("role-scope", "角色租户")
    tenant = users_repo.get_tenant_by_code("role-scope")
    user = users_repo.get_user_by_username("admin_viewer_in_tenant")
    users_repo.bind_user_tenant(user["id"], tenant["id"], "viewer")

    response = authed.post(
        "/api/v1/scans",
        json={"strategy_code": "2560", "params": {}},
        headers=tenant_headers(authed, tenant_id=tenant["id"], include_csrf=True),
    )
    data = response.get_json()

    assert response.status_code == 403
    assert data["code"] == 403


def test_strategy_backtest_api_returns_structured_summary_and_audit(client, monkeypatch):
    from backend.application import backtest_api_service
    from backend.application.backtest_api_service import BacktestApiService
    from backend.application.audit_log_service import audit_log_service

    def fake_run_backtest(strategy_code, start_date, end_date, *, holding_days=5, max_positions_per_day=3):
        return {
            "success": True,
            "results": {
                "total_trades": 4,
                "win_rate": 0.75,
                "total_return": 0.12,
                "max_drawdown": 0.05,
                "sharpe_ratio": 1.4,
                "profit_factor": 2.2,
                "trades": [
                    {
                        "code": "000001",
                        "name": "平安银行",
                        "signal": "站上25日均线",
                        "entry_date": "2026-01-02",
                        "exit_date": "2026-01-07",
                        "holding_days": holding_days,
                        "entry_price": 10,
                        "exit_price": 10.3,
                        "return_pct": 0.03,
                    }
                ],
            },
            "meta": {
                "strategy_code": strategy_code,
                "strategy_name": "2560战法",
                "start_date": start_date,
                "end_date": end_date,
                "holding_days": holding_days,
                "max_positions_per_day": max_positions_per_day,
                "trade_days": 20,
            },
        }

    monkeypatch.setattr(backtest_api_service, "run_backtest", fake_run_backtest)
    authed = login_as(client, "editor_backtest")

    response = authed.post(
        "/api/v1/strategies/2560/backtest",
        json={
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "holding_days": 7,
            "max_positions_per_day": 2,
            "trade_limit": 10,
            "benchmark_code": "000300",
            "benchmark_return_pct": 0.03,
            "api_key": "secret-value",
        },
        headers=tenant_headers(authed, include_csrf=True),
    )
    data = response.get_json()

    assert response.status_code == 202
    assert data["data"]["summary"]["total_trades"] == 4
    assert data["data"]["summary"]["risk_level"] == "low"
    assert data["data"]["summary"]["benchmark"]["code"] == "000300"
    assert data["data"]["summary"]["benchmark"]["total_return"] == 0.03
    assert data["data"]["summary"]["benchmark"]["excess_return"] == 0.09
    assert data["data"]["summary"]["benchmark"]["curve"]
    assert data["data"]["summary"]["data_contract"]["benchmark_source"] == "synthetic"
    assert data["data"]["summary"]["data_contract"]["adjust"] == "qfq"
    assert data["data"]["summary"]["data_contract"]["mock_or_fallback"] is True
    assert data["data"]["summary"]["data_contract"]["quality_gate"]["quality_reason"] == "degraded_market_data"
    assert data["data"]["summary"]["portfolio_curve"][0]["excess_return_pct"] == 0
    assert data["data"]["summary"]["risk_attribution"]["schema_version"] == "risk-attribution/v1"
    assert data["data"]["summary"]["experiment"]["params"]["benchmark_code"] == "000300"
    assert data["data"]["summary"]["trade_page"]["items"][0]["holding_days"] == 7
    assert data["data"]["summary"]["return_distribution"]["win_count"] == 1
    assert data["data"]["meta"]["request_options"]["max_positions_per_day"] == 2
    assert data["data"]["explanation"]["schema_version"] == "backtest-explanation/v2"
    assert data["data"]["explanation"]["confidence"] > 0
    assert data["data"]["explanation"]["indicators"]["win_rate"] == 0.75
    assert data["data"]["explanation"]["indicators"]["excess_return"] == 0.09
    assert data["data"]["explanation"]["indicator_groups"]["risk"]["risk_level"] == "low"
    assert "action_suggestion" in data["data"]["explanation"]
    logs = audit_log_service.list_logs(tenant_id=1, action="strategy.backtest.create")
    assert logs["items"]
    assert logs["items"][0]["detail"]["params"]["api_key"] == "***REDACTED***"
    assert logs["items"][0]["integrity_hash"]


def test_strategy_backtest_uses_synthetic_benchmark_when_local_missing(client, monkeypatch):
    from backend.application import backtest_api_service

    def fake_run_backtest(strategy_code, start_date, end_date, *, holding_days=5, max_positions_per_day=3):
        assert os.environ.get("MARKET_DATA_LOCAL_ONLY") == "1"
        return {
            "success": True,
            "results": {
                "total_trades": 1,
                "win_rate": 1.0,
                "total_return": 0.1,
                "max_drawdown": 0.0,
                "trades": [{"code": "000001", "entry_price": 10, "exit_price": 11, "return_pct": 0.1}],
            },
            "meta": {"strategy_code": strategy_code, "start_date": start_date, "end_date": end_date},
        }

    monkeypatch.setattr(backtest_api_service, "run_backtest", fake_run_backtest)
    authed = login_as(client, "editor_real_benchmark")

    response = authed.post(
        "/api/v1/strategies/2560/backtest",
        json={"start_date": "2026-01-01", "end_date": "2026-01-31", "benchmark_code": "000300"},
        headers=tenant_headers(authed, include_csrf=True),
    )
    benchmark = response.get_json()["data"]["summary"]["benchmark"]
    data_contract = response.get_json()["data"]["summary"]["data_contract"]

    assert response.status_code == 202
    assert benchmark["source"] == "synthetic"
    assert benchmark["data_quality"] == "derived"
    assert benchmark["fallback_used"] is True
    assert benchmark["message"] == "local benchmark data unavailable; external provider disabled for backtest"
    assert data_contract["benchmark_source"] == "synthetic"
    assert data_contract["backtest_data_policy"] == "local_only_no_external_provider"
    assert data_contract["external_provider_disabled"] is True
    assert data_contract["mock_or_fallback"] is True
    assert data_contract["quality_gate"]["quality_reason"] == "degraded_market_data"
    assert benchmark["total_return"] == 0.0
    assert benchmark["curve"][-1]["return_pct"] == 0.0


def test_strategy_backtest_uses_local_data_center_before_external_provider(client, monkeypatch):
    from datetime import date
    from decimal import Decimal

    from backend.application import backtest_api_service
    from backend.infrastructure.market_data.provider import DailyBar
    from backend.repositories import market_data_repo

    def fake_run_backtest(strategy_code, start_date, end_date, *, holding_days=5, max_positions_per_day=3):
        return {
            "success": True,
            "results": {
                "total_trades": 1,
                "win_rate": 1,
                "total_return": 0.01,
                "trades": [{"code": "000001", "entry_price": 10, "exit_price": 11, "return_pct": 0.1}],
            },
            "meta": {"strategy_code": strategy_code, "strategy_name": "2560", "start_date": start_date, "end_date": end_date},
        }

    market_data_repo.upsert_daily_bars(
        [
            DailyBar("000300", date(2026, 1, 1), Decimal("10"), Decimal("10"), Decimal("10"), Decimal("10"), 100, Decimal("1000"), source="mootdx"),
            DailyBar("000300", date(2026, 1, 31), Decimal("11"), Decimal("11"), Decimal("11"), Decimal("11"), 100, Decimal("1100"), source="mootdx"),
        ],
        adjust="qfq",
    )
    monkeypatch.setattr(backtest_api_service, "run_backtest", fake_run_backtest)
    authed = login_as(client, "editor_local_benchmark")

    response = authed.post(
        "/api/v1/strategies/2560/backtest",
        json={"start_date": "2026-01-01", "end_date": "2026-01-31", "benchmark_code": "000300"},
        headers=tenant_headers(authed, include_csrf=True),
    )
    benchmark = response.get_json()["data"]["summary"]["benchmark"]

    assert response.status_code == 202
    assert benchmark["source"] == "local:mootdx"
    assert benchmark["message"] == "benchmark curve built from local data center"
    assert benchmark["fallback_used"] is False


def test_strategy_backtest_rejects_invalid_date(client):
    authed = login_as(client, "editor_backtest_bad_date")

    response = authed.post(
        "/api/v1/strategies/2560/backtest",
        json={"start_date": "2026/01/01", "end_date": "2026-01-31"},
        headers=tenant_headers(authed, include_csrf=True),
    )

    assert response.status_code == 400



def test_strategy_backtest_rejects_invalid_position_options(client):
    authed = login_as(client, "editor_backtest_bad_options")

    response = authed.post(
        "/api/v1/strategies/2560/backtest",
        json={"start_date": "2026-01-01", "end_date": "2026-01-31", "holding_days": 0},
        headers=tenant_headers(authed, include_csrf=True),
    )

    assert response.status_code == 400
    assert "holding_days" in response.get_json()["message"]


def test_strategy_backtest_returns_parameter_comparison(client, monkeypatch):
    from backend.application import backtest_api_service

    def fake_run_backtest(strategy_code, start_date, end_date, *, holding_days=5, max_positions_per_day=3):
        trade_return = holding_days / 100
        return {
            "success": True,
            "results": {
                "total_trades": max_positions_per_day,
                "win_rate": 1.0,
                "total_return": trade_return,
                "max_drawdown": 0.02,
                "trades": [{"code": "000001", "name": "Ping An", "return_pct": trade_return}],
            },
            "meta": {"strategy_code": strategy_code, "start_date": start_date, "end_date": end_date},
        }

    monkeypatch.setattr(backtest_api_service, "run_backtest", fake_run_backtest)
    authed = login_as(client, "editor_backtest_param_groups")

    response = authed.post(
        "/api/v1/strategies/2560/backtest",
        json={
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "holding_days": 5,
            "param_groups": [
                {"label": "fast", "holding_days": 3, "max_positions_per_day": 2},
                {"label": "slow", "holding_days": 10, "max_positions_per_day": 4, "benchmark_return_pct": 0.02},
            ],
        },
        headers=tenant_headers(authed, include_csrf=True),
    )
    data = response.get_json()["data"]

    assert response.status_code == 202
    assert [item["label"] for item in data["parameter_comparison"]] == ["fast", "slow"]
    assert data["parameter_comparison"][0]["summary"]["total_return"] == 0.03
    assert data["parameter_comparison"][1]["summary"]["excess_return"] == 0.08
    assert "highest_risk" in data["parameter_comparison"][0]["summary"]


def test_strategy_backtest_applies_execution_constraints(client, monkeypatch):
    from backend.application import backtest_api_service

    def fake_run_backtest(strategy_code, start_date, end_date, *, holding_days=5, max_positions_per_day=3):
        return {
            "success": True,
            "results": {
                "total_trades": 4,
                "win_rate": 0.75,
                "total_return": 0.35,
                "max_drawdown": 0.04,
                "trades": [
                    {"code": "000001", "name": "Valid", "entry_price": 10, "exit_price": 10.5, "return_pct": 0.05},
                    {"code": "000002", "name": "Limit Up", "entry_price": 8, "exit_price": 8.8, "return_pct": 0.1, "is_limit_up": True},
                    {"code": "000003", "name": "Suspended", "entry_price": 6, "exit_price": 5.88, "return_pct": -0.02, "is_suspended": True},
                    {"code": "000004", "name": "Bad Price", "entry_price": 0, "exit_price": 7.7, "return_pct": 0.1},
                ],
            },
            "meta": {"strategy_code": strategy_code, "start_date": start_date, "end_date": end_date},
        }

    monkeypatch.setattr(backtest_api_service, "run_backtest", fake_run_backtest)
    authed = login_as(client, "editor_backtest_constraints")

    response = authed.post(
        "/api/v1/strategies/2560/backtest",
        json={"start_date": "2026-01-01", "end_date": "2026-01-31", "limit_up_down_guard": True},
        headers=tenant_headers(authed, include_csrf=True),
    )
    data = response.get_json()["data"]
    constraints = data["summary"]["execution_constraints"]

    assert response.status_code == 202
    assert data["summary"]["raw_trade_count"] == 4
    assert data["summary"]["total_trades"] == 1
    assert data["summary"]["win_rate"] == 1.0
    assert data["summary"]["total_return"] == 0.05
    assert data["summary"]["trade_page"]["total"] == 1
    assert constraints["enabled"] is True
    assert constraints["excluded_count"] == 3
    assert constraints["reasons"]["limit_up"] == 1
    assert constraints["reasons"]["suspended"] == 1
    assert constraints["reasons"]["invalid_price"] == 1


def test_strategy_backtest_keeps_limit_trades_when_guard_disabled(client, monkeypatch):
    from backend.application import backtest_api_service

    def fake_run_backtest(strategy_code, start_date, end_date, *, holding_days=5, max_positions_per_day=3):
        return {
            "success": True,
            "results": {
                "total_trades": 3,
                "win_rate": 0.66,
                "total_return": 0.12,
                "max_drawdown": 0.02,
                "trades": [
                    {"code": "000001", "name": "Valid", "entry_price": 10, "exit_price": 10.5, "return_pct": 0.05},
                    {"code": "000002", "name": "Limit Up", "entry_price": 8, "exit_price": 8.8, "return_pct": 0.1, "is_limit_up": True},
                    {"code": "000003", "name": "Bad Price", "entry_price": 0, "exit_price": 7.7, "return_pct": 0.1},
                ],
            },
            "meta": {"strategy_code": strategy_code, "start_date": start_date, "end_date": end_date},
        }

    monkeypatch.setattr(backtest_api_service, "run_backtest", fake_run_backtest)
    authed = login_as(client, "editor_backtest_constraints_off")

    response = authed.post(
        "/api/v1/strategies/2560/backtest",
        json={"start_date": "2026-01-01", "end_date": "2026-01-31", "limit_up_down_guard": False},
        headers=tenant_headers(authed, include_csrf=True),
    )
    data = response.get_json()["data"]
    constraints = data["summary"]["execution_constraints"]

    assert response.status_code == 202
    assert data["summary"]["total_trades"] == 2
    assert data["summary"]["trade_page"]["total"] == 2
    assert [item["code"] for item in data["summary"]["trade_page"]["items"]] == ["000001", "000002"]
    assert constraints["enabled"] is False
    assert constraints["excluded_count"] == 1
    assert constraints["reasons"]["invalid_price"] == 1
    assert constraints["reasons"]["limit_up"] == 0



def test_strategy_backtest_history_is_paginated_with_explanation(client, monkeypatch):
    from backend.application import backtest_api_service

    monkeypatch.setattr(
        backtest_api_service,
        "get_strategy_backtest",
        lambda strategy_code: [
            {
                "id": 2,
                "strategy_code": strategy_code,
                "start_date": "2026-02-01",
                "end_date": "2026-02-28",
                "total_trades": 8,
                "win_rate": 0.625,
                "avg_return": 0.02,
                "max_return": 0.08,
                "max_drawdown": 0.04,
                "sharpe_ratio": 1.2,
                "total_return": 0.15,
            },
            {
                "id": 1,
                "strategy_code": strategy_code,
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "total_trades": 4,
                "win_rate": 0.5,
                "avg_return": 0.01,
                "max_return": 0.03,
                "max_drawdown": 0.08,
                "sharpe_ratio": 0.8,
                "total_return": 0.04,
            },
        ],
    )
    authed = login_as(client, "editor_backtest_history")

    response = authed.get("/api/v1/strategies/2560/backtests?page=1&page_size=1", headers=tenant_headers(authed))
    data = response.get_json()

    assert response.status_code == 200
    assert data["data"]["total"] == 2
    assert data["data"]["page_size"] == 1
    assert len(data["data"]["items"]) == 1
    assert data["data"]["items"][0]["explanation"]["schema_version"] == "backtest-explanation/v2"


def test_strategy_backtest_history_detail_includes_explanation_and_audit(client, monkeypatch):
    from backend.application import backtest_api_service
    from backend.application.audit_log_service import audit_log_service
    from backend.core.tenant_context import TenantContext

    monkeypatch.setattr(
        backtest_api_service,
        "get_strategy_backtest",
        lambda strategy_code: [
            {
                "id": 7,
                "strategy_code": strategy_code,
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
                "total_trades": 6,
                "win_rate": 0.5,
                "avg_return": 0.01,
                "max_return": 0.05,
                "max_drawdown": 0.07,
                "sharpe_ratio": 0.9,
                "total_return": 0.06,
                "backtest_date": "2026-04-01 09:00:00",
            }
        ],
    )
    authed = login_as(client, "editor_backtest_detail")
    with authed.application.test_request_context(headers={"X-Tenant-ID": "1"}):
        audit_log_service.record(
            context=TenantContext(tenant_id=1, user_id=1, role="editor"),
            username="editor_backtest_detail",
            action="strategy.backtest.create",
            resource_type="strategy",
            resource_id="2560",
            detail={"strategy_code": "2560", "params": {"start_date": "2026-03-01"}},
        )

    response = authed.get("/api/v1/strategies/2560/backtests/7", headers=tenant_headers(authed))
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["item"]["id"] == 7
    assert data["item"]["summary"]["total_trades"] == 6
    assert data["item"]["explanation"]["schema_version"] == "backtest-explanation/v2"
    assert data["audit_trail"]
    assert data["audit_trail"][0]["resource_id"] == "2560"


def test_scan_explanation_includes_strategy_signal_fields():
    from backend.application.scan_api_service import ScanApiService

    service = ScanApiService()
    explanation = service._build_explanation(
        {
            "code": "000001",
            "pick_price": 10.5,
            "signal": "站上25日均线",
            "note": "量能放大",
            "risk_score": 72,
            "total_score": 88,
            "vol_ratio": 1.8,
            "ma25": 10.1,
            "ma60": 9.8,
            "ma25_slope_5": 0.4,
            "ma60_slope_10": 0.2,
            "vr5_60": 1.3,
            "vr1_60": 1.9,
            "volume_phase": "active",
            "signal_subtype": "ma25_breakout",
        },
        {"actual_provider": "akshare", "provider_chain": ["akshare"], "fallback_used": False, "data_quality": "primary"},
        "2560",
    )

    assert explanation["schema_version"] == "scan-explanation/v2"
    assert explanation["confidence"] > 0
    assert explanation["risk_level"] == "medium"
    assert "策略信号：站上25日均线" in explanation["reasons"]
    assert explanation["indicators"]["risk_score"] == 72
    assert explanation["indicators"]["vol_ratio"] == 1.8
    assert explanation["indicators"]["ma60"] == 9.8
    assert explanation["indicators"]["ma25_slope_5"] == 0.4
    assert explanation["indicators"]["ma60_slope_10"] == 0.2
    assert explanation["indicators"]["vr5_60"] == 1.3
    assert explanation["indicators"]["vr1_60"] == 1.9
    assert explanation["indicators"]["volume_phase"] == "active"
    assert explanation["indicators"]["signal_subtype"] == "ma25_breakout"
    assert explanation["indicator_groups"]["technical"]["ma25"] == 10.1
    assert explanation["indicator_groups"]["technical"]["ma60"] == 9.8
    assert "action_suggestion" in explanation
    assert "策略风险偏高" in explanation["risk_tags"]


def test_scan_explanation_accepts_2560_signal_sections():
    from backend.application.scan_api_service import ScanApiService

    service = ScanApiService()
    explanation = service._build_explanation(
        {
            "schema_version": "strategy-signal/2560/v1",
            "signal": "25/60共振",
            "indicators": {
                "ma25": 10.2,
                "ma60": 9.7,
                "ma25_slope_5": 0.35,
                "ma60_slope_10": 0.18,
                "vr5_60": 1.4,
                "vr1_60": 2.1,
            },
            "phase": {
                "volume_phase": "expansion",
                "signal_subtype": "resonance",
            },
            "risk": {"risk_score": 22},
            "data": {"score": 82, "total_score": 86},
        },
        {"actual_provider": "akshare", "provider_chain": ["akshare"], "fallback_used": False, "data_quality": "primary"},
        "2560",
    )

    assert explanation["score"] == 86
    assert explanation["indicators"]["score"] == 82
    assert explanation["indicators"]["total_score"] == 86
    assert explanation["indicators"]["ma60"] == 9.7
    assert explanation["indicators"]["ma25_slope_5"] == 0.35
    assert explanation["indicators"]["ma60_slope_10"] == 0.18
    assert explanation["indicators"]["vr5_60"] == 1.4
    assert explanation["indicators"]["vr1_60"] == 2.1
    assert explanation["indicator_groups"]["signal"]["signal_subtype"] == "resonance"
    assert explanation["indicator_groups"]["technical"]["volume_phase"] == "expansion"
    assert explanation["indicator_groups"]["risk"]["risk_score"] == 22


def test_scan_normalized_strategy_pick_preserves_2560_signal_sections():
    from backend.application.scan_api_service import ScanApiService

    service = ScanApiService()
    normalized = service._normalize_strategy_pick(
        {
            "code": "000001",
            "name": "Ping An",
            "signal": "25/60共振",
            "indicators": {
                "ma60": 9.7,
                "ma25_slope_5": 0.35,
                "ma60_slope_10": 0.18,
                "vr5_60": 1.4,
                "vr1_60": 2.1,
            },
            "phase": {"volume_phase": "expansion", "signal_subtype": "resonance"},
            "risk": {"risk_score": 22},
            "data": {"score": 82, "total_score": 86},
        },
        {"actual_provider": "akshare", "provider_chain": ["akshare"], "fallback_used": False, "data_quality": "primary"},
        "2560",
    )

    assert normalized["ma60"] == 9.7
    assert normalized["volume_phase"] == "expansion"
    assert normalized["signal_subtype"] == "resonance"
    assert normalized["explanation"]["indicators"]["total_score"] == 86
    assert normalized["explanation"]["indicator_groups"]["technical"]["vr5_60"] == 1.4


def test_audit_log_integrity_hash_is_stable_for_same_payload():
    from backend.repositories.audit_logs_repo import build_integrity_hash

    payload = {
        "user_id": 1,
        "username": "admin",
        "tenant_id": 1,
        "action": "demo.action",
        "resource_type": "demo",
        "resource_id": "42",
        "result": "success",
        "detail": {"b": 2, "a": 1},
    }

    assert build_integrity_hash(**payload) == build_integrity_hash(**payload)
