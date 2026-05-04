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


def test_api_v1_health_response_shape():
    app = create_app({"TESTING": True})
    client = app.test_client()

    response = client.get("/api/v1/health")
    data = response.get_json()

    assert response.status_code == 200
    assert data["code"] == 0
    assert data["message"] == "ok"
    assert data["data"]["status"] == "ok"



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
    assert data["data"]["market_data"]["actual_provider"] == "mock"
    assert data["data"]["market_data"]["data_quality"] == "mock"
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

    response = authed.get("/api/v1/tasks?page=1&page_size=5&status=failed", headers=tenant_headers(authed))
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["page_size"] == 5
    assert data["items"][0]["failure_category"] == "validation"
    assert data["items"][0]["error_summary"] == "bad input"
    assert data["items"][0]["events"]


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
                    "provider": "mock",
                    "primary_provider": "mock",
                    "actual_provider": "mock",
                    "provider_chain": ["mock"],
                    "fallback_used": False,
                    "data_quality": "mock",
                    "errors": [],
                    "healthy": True,
                    "sample_symbols": [
                        {
                            "symbol": "000001",
                            "name": "平安银行",
                            "exchange": "SZ",
                            "market": "A",
                            "market_data_source": "mock",
                            "data_quality": "mock",
                            "fallback_used": False,
                        }
                    ],
                }
            },
        },
    )

    response = authed.get(f"/api/v1/scans/{scan_id}/results", headers=tenant_headers(authed))
    data = response.get_json()

    assert response.status_code == 200
    assert data["data"]["market_data"]["actual_provider"] == "mock"
    assert data["data"]["market_data"]["data_quality"] == "mock"
    assert data["data"]["items"][0]["market_data_source"] == "mock"
    assert data["data"]["items"][0]["data_quality"] == "mock"
    assert data["data"]["items"][0]["explanation"]["schema_version"] == "scan-explanation/v2"
    assert data["data"]["items"][0]["explanation"]["risk_level"] == "high"



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

    for payload in [
        {"symbol": "000001", "stock_name": "Primary", "source": "manual", "data_quality": "primary", "market_data_source": "akshare"},
        {"symbol": "000002", "stock_name": "Fallback", "source": "scan", "data_quality": "primary", "market_data_source": "akshare", "fallback_used": True},
        {"symbol": "000003", "stock_name": "Mock", "source": "scan", "data_quality": "mock", "market_data_source": "mock"},
    ]:
        response = authed.post(
            "/api/v1/picks",
            json={**payload, "trade_date": "2026-05-04", "strategy_code": "2560"},
            headers=tenant_headers(authed, include_csrf=True),
        )
        assert response.status_code == 201

    response = authed.get("/api/v1/reports/summary?period=week", headers=tenant_headers(authed))
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["summary"]["data_quality"]["primary"] == 1
    assert data["summary"]["data_quality"]["fallback"] == 1
    assert data["summary"]["data_quality"]["mock"] == 1
    assert data["groups"][0]["data_quality"]["primary"] == 1
    assert data["groups"][0]["data_quality"]["fallback"] == 1
    assert data["drilldowns"]["picks"]["page"] == "picks"
    assert data["groups"][0]["drilldowns"]["picks"]["filters"]["strategy_code"] == "2560"
    assert data["groups"][0]["drilldowns"]["backtests"]["page"] == "strategies"
    assert data["groups"][0]["data_quality"]["mock"] == 1


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
        },
        {"actual_provider": "mock", "provider_chain": ["mock"], "fallback_used": False, "data_quality": "mock"},
        "2560",
    )

    assert explanation["schema_version"] == "scan-explanation/v2"
    assert explanation["confidence"] > 0
    assert explanation["risk_level"] == "high"
    assert "策略信号：站上25日均线" in explanation["reasons"]
    assert explanation["indicators"]["risk_score"] == 72
    assert explanation["indicators"]["vol_ratio"] == 1.8
    assert explanation["indicator_groups"]["technical"]["ma25"] == 10.1
    assert "action_suggestion" in explanation
    assert "策略风险偏高" in explanation["risk_tags"]


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
