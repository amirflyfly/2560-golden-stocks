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


def get_csrf_token(client) -> str | None:
    with client.session_transaction() as current_session:
        return current_session.get("_csrf_token")


def login_as(client, username: str, role: str = "admin", password: str = "testpass"):
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


def tenant_headers(client, *, include_csrf: bool = False, extra: dict | None = None) -> dict:
    headers = {"X-Tenant-ID": "1"}
    if include_csrf:
        headers["X-CSRF-Token"] = get_csrf_token(client) or ""
    if extra:
        headers.update(extra)
    return headers


def test_monitoring_requires_admin_role(client):
    viewer = login_as(client, "stage9_viewer", role="viewer")

    response = viewer.get("/api/v1/monitoring/overview", headers=tenant_headers(viewer))
    data = response.get_json()

    assert response.status_code == 403
    assert data["code"] == 403


def test_monitoring_overview_metrics_and_logs_for_admin(client):
    admin = login_as(client, "stage9_admin", role="admin")

    overview = admin.get("/api/v1/monitoring/overview", headers=tenant_headers(admin))
    metrics = admin.get("/api/v1/monitoring/metrics", headers=tenant_headers(admin))
    logs = admin.get("/api/v1/monitoring/logs?limit=5", headers=tenant_headers(admin))

    assert overview.status_code == 200
    assert overview.get_json()["data"]["database"]["ok"] in {True, False}
    assert "tasks_total" in metrics.get_json()["data"]
    log_data = logs.get_json()["data"]
    assert log_data["source"] in {"unavailable", "logs/app.log"}
    assert isinstance(log_data["items"], list)


def test_admin_user_management_requires_admin_and_csrf(client):
    editor = login_as(client, "stage9_editor", role="editor")

    forbidden = editor.get("/api/v1/admin/users", headers=tenant_headers(editor))
    assert forbidden.status_code == 403

    admin = client.application.test_client()
    login_as(admin, "stage9_admin_users", role="admin")

    users = admin.get("/api/v1/admin/users", headers=tenant_headers(admin))
    assert users.status_code == 200
    target = next(item for item in users.get_json()["data"]["items"] if item["username"] == "stage9_editor")

    missing_csrf = admin.patch(
        f"/api/v1/admin/users/{target['id']}/role",
        json={"role": "viewer"},
        headers=tenant_headers(admin),
    )
    assert missing_csrf.status_code == 403

    changed = admin.patch(
        f"/api/v1/admin/users/{target['id']}/role",
        json={"role": "viewer"},
        headers=tenant_headers(admin, include_csrf=True),
    )
    assert changed.status_code == 200
    assert changed.get_json()["data"]["role"] == "viewer"


def test_task_filters_and_cancel_endpoint(client):
    admin = login_as(client, "stage9_tasks", role="admin")

    created = admin.post(
        "/api/v1/market-data/sync",
        json={"symbols": ["000001"], "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=tenant_headers(admin, include_csrf=True),
    )
    assert created.status_code == 202
    task_id = created.get_json()["data"]["id"]

    listed = admin.get("/api/v1/tasks?name=market.sync", headers=tenant_headers(admin))
    assert listed.status_code == 200
    assert listed.get_json()["data"]["filters"]["name"] == "market.sync"

    cancelled = admin.post(
        f"/api/v1/tasks/{task_id}/cancel",
        json={},
        headers=tenant_headers(admin, include_csrf=True),
    )
    assert cancelled.status_code == 200
    data = cancelled.get_json()["data"]
    assert data["status"] in {"cancelled", "completed"}
    assert "duration_seconds" in data


def test_cancelled_task_is_not_overwritten_by_runner():
    from backend.infrastructure.tasks import queue

    original_executor = queue._executor

    class ManualExecutor:
        def __init__(self):
            self.runner = None

        def submit(self, runner):
            self.runner = runner
            return None

    manual_executor = ManualExecutor()
    queue._executor = manual_executor
    try:
        task = queue.enqueue_task("stage10.cancel", lambda: {"ok": True}, tenant_id=1)
        queue.update_task(task["id"], {"status": "cancelled", "error": "cancelled before start"})

        manual_executor.runner()
        stored = queue.get_task(task["id"])

        assert stored["status"] == "cancelled"
        assert stored["result"] is None
        assert stored["finished_at"]
        assert stored["duration_seconds"] is None
        assert stored["events"][-1]["status"] == "cancelled"
    finally:
        queue._executor = original_executor


def test_task_queue_records_retry_and_failure_metadata():
    from backend.infrastructure.tasks import queue

    original_executor = queue._executor

    class ImmediateExecutor:
        def submit(self, runner):
            runner()
            return None

    attempts = {"count": 0}

    def flaky_task():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ValueError("bad input")
        return {"ok": True}

    queue._executor = ImmediateExecutor()
    try:
        task = queue.enqueue_task("stage13.retry", flaky_task, tenant_id=1, payload={"symbol": "000001"}, max_retries=1)
        stored = queue.get_task(task["id"])
    finally:
        queue._executor = original_executor

    assert stored["status"] == "completed"
    assert stored["retry_count"] == 1
    assert stored["idempotency_key"]
    assert stored["duration_seconds"] is not None
    assert any(event["status"] == "retrying" for event in stored["events"])


def test_mark_stale_tasks_marks_expired_running_task():
    from backend.infrastructure.tasks import queue

    task = {
        "id": "stage13_stale_manual",
        "name": "stage13.stale",
        "tenant_id": 1,
        "status": "running",
        "payload": {},
        "events": [],
        "created_at": "2000-01-01T00:00:00",
        "started_at": "2000-01-01T00:00:00",
        "heartbeat_at": "2000-01-01T00:00:00",
        "finished_at": None,
        "result": None,
        "error": None,
    }
    queue.save_task(task)

    marked = queue.mark_stale_tasks(stale_after_seconds=1)
    stored = queue.get_task(task["id"])

    assert any(item["id"] == task["id"] for item in marked)
    assert stored["status"] == "stale"
    assert stored["failure_category"] == "stale"


def test_admin_can_manage_users_tenants_and_bindings(client):
    admin = login_as(client, "stage10_admin_crud", role="admin")

    created_tenant = admin.post(
        "/api/v1/admin/tenants",
        json={"code": "stage10", "name": "第十阶段租户", "plan": "pro"},
        headers=tenant_headers(admin, include_csrf=True),
    )
    assert created_tenant.status_code == 201
    tenant_id = created_tenant.get_json()["data"]["id"]

    updated_tenant = admin.patch(
        f"/api/v1/admin/tenants/{tenant_id}",
        json={"name": "第十阶段租户更新", "status": "disabled"},
        headers=tenant_headers(admin, include_csrf=True),
    )
    assert updated_tenant.status_code == 200
    assert updated_tenant.get_json()["data"]["status"] == "disabled"

    created_user = admin.post(
        "/api/v1/admin/users",
        json={"username": "stage10_managed", "password": "testpass10", "role": "viewer", "tenant_id": tenant_id},
        headers=tenant_headers(admin, include_csrf=True),
    )
    assert created_user.status_code == 201
    user_data = created_user.get_json()["data"]
    assert user_data["role"] == "viewer"
    assert user_data["tenants"][0]["tenant_id"] == tenant_id

    reset_password = admin.patch(
        f"/api/v1/admin/users/{user_data['id']}/password",
        json={"password": "newpass10"},
        headers=tenant_headers(admin, include_csrf=True),
    )
    assert reset_password.status_code == 200

    rebound = admin.post(
        f"/api/v1/admin/users/{user_data['id']}/tenants",
        json={"tenant_id": 1, "role": "editor", "is_default": True},
        headers=tenant_headers(admin, include_csrf=True),
    )
    assert rebound.status_code == 200
    tenant_ids = {item["tenant_id"] for item in rebound.get_json()["data"]["tenants"]}
    assert {1, tenant_id}.issubset(tenant_ids)

    unbound = admin.delete(
        f"/api/v1/admin/users/{user_data['id']}/tenants/{tenant_id}",
        headers=tenant_headers(admin, include_csrf=True),
    )
    assert unbound.status_code == 200
    assert all(item["tenant_id"] != tenant_id for item in unbound.get_json()["data"]["tenants"])


def test_admin_crud_requires_csrf(client):
    admin = login_as(client, "stage10_admin_csrf", role="admin")

    response = admin.post(
        "/api/v1/admin/tenants",
        json={"code": "csrf_fail", "name": "CSRF Fail"},
        headers=tenant_headers(admin),
    )

    assert response.status_code == 403


def test_tasks_and_scan_endpoints_have_lightweight_performance_baseline(client):
    admin = login_as(client, "stage10_perf", role="admin")

    for index in range(8):
        created = admin.post(
            "/api/v1/market-data/sync",
            json={"symbols": [f"00000{index}"], "start_date": "2026-01-01", "end_date": "2026-01-02"},
            headers=tenant_headers(admin, include_csrf=True),
        )
        assert created.status_code == 202

    started = time.perf_counter()
    tasks = admin.get("/api/v1/tasks?page=1&page_size=5&name=market.sync", headers=tenant_headers(admin))
    elapsed = time.perf_counter() - started
    data = tasks.get_json()["data"]

    assert tasks.status_code == 200
    assert len(data["items"]) <= 5
    assert data["filters"]["name"] == "market.sync"
    assert elapsed < 1.5

    started = time.perf_counter()
    scans = admin.get("/api/v1/scans?page=1&page_size=5", headers=tenant_headers(admin))
    elapsed = time.perf_counter() - started

    assert scans.status_code == 200
    assert "items" in scans.get_json()["data"]
    assert elapsed < 1.5


def test_scan_create_returns_quick_summary_without_sample_payload(client):
    editor = login_as(client, "stage9_scan", role="editor")

    response = editor.post(
        "/api/v1/scans",
        json={"strategy_code": "2560", "params": {}},
        headers=tenant_headers(editor, include_csrf=True),
    )
    data = response.get_json()["data"]

    assert response.status_code == 202
    assert data["market_data"]["sample_symbols"] == []
    assert data["task_id"]


def test_admin_audit_logs_capture_key_operations_and_redact_sensitive_fields(client):
    admin = login_as(client, "stage12_audit_admin", role="admin")

    created_user = admin.post(
        "/api/v1/admin/users",
        json={"username": "stage12_audited", "password": "testpass12", "role": "viewer", "tenant_id": 1},
        headers=tenant_headers(admin, include_csrf=True),
    )
    assert created_user.status_code == 201
    user_id = created_user.get_json()["data"]["id"]

    reset = admin.patch(
        f"/api/v1/admin/users/{user_id}/password",
        json={"password": "newpass12"},
        headers=tenant_headers(admin, include_csrf=True),
    )
    assert reset.status_code == 200

    audit = admin.get("/api/v1/admin/audit-logs?limit=10", headers=tenant_headers(admin))
    assert audit.status_code == 200
    items = audit.get_json()["data"]["items"]
    actions = {item["action"] for item in items}
    assert "admin.user.create" in actions
    assert "admin.user.password_reset" in actions
    serialized = str(items)
    assert "testpass12" not in serialized
    assert "newpass12" not in serialized
    assert "password_set" in serialized
    assert "password':" not in serialized


def test_scan_sync_and_task_cancel_are_audited(client):
    admin = login_as(client, "stage12_audit_ops", role="admin")

    scan = admin.post(
        "/api/v1/scans",
        json={"strategy_code": "2560", "params": {}},
        headers=tenant_headers(admin, include_csrf=True),
    )
    assert scan.status_code == 202

    sync = admin.post(
        "/api/v1/market-data/sync",
        json={"symbols": ["000001"], "start_date": "2026-01-01", "end_date": "2026-01-02"},
        headers=tenant_headers(admin, include_csrf=True),
    )
    assert sync.status_code == 202
    task_id = sync.get_json()["data"]["id"]

    cancelled = admin.post(
        f"/api/v1/tasks/{task_id}/cancel",
        json={},
        headers=tenant_headers(admin, include_csrf=True),
    )
    assert cancelled.status_code == 200

    audit = admin.get("/api/v1/admin/audit-logs?limit=20", headers=tenant_headers(admin))
    actions = {item["action"] for item in audit.get_json()["data"]["items"]}
    assert {"scan.create", "market.sync.create", "task.cancel"}.issubset(actions)
