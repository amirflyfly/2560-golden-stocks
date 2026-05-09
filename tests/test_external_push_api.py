from __future__ import annotations

import os
import tempfile

import pytest

from backend import create_app


@pytest.fixture
def app(monkeypatch):
    import backend.repositories.db as db_module

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = db_path
    monkeypatch.setenv("EXTERNAL_PUSH_DELIVERY_REPOSITORY_BACKEND", "sqlite")

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


def login_api(client, username: str = "admin", password: str = "admin123"):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return client


def tenant_headers(client, tenant_id: int = 1, *, include_csrf: bool = False) -> dict:
    headers = {"X-Tenant-ID": str(tenant_id)}
    if include_csrf:
        with client.session_transaction() as current_session:
            headers["X-CSRF-Token"] = current_session.get("_csrf_token") or ""
    return headers


def test_external_push_deliveries_list_returns_stats_and_items(client):
    from backend.repositories import external_push_delivery_repo

    authed = login_api(client)
    failed = external_push_delivery_repo.record_queued_delivery(
        tenant_id=1,
        user_id=1,
        delivery_key="external_push.dispatch:failed-api",
        channel_id="webhook-api",
        channel_type="webhook",
        notification={"title": "API failed", "dedupe_key": "api-failed"},
    )
    external_push_delivery_repo.update_delivery(failed["id"], status="failed", last_error="timeout")
    sent = external_push_delivery_repo.record_queued_delivery(
        tenant_id=1,
        user_id=1,
        delivery_key="external_push.dispatch:sent-api",
        channel_id="email-api",
        channel_type="email",
        notification={"title": "API sent", "dedupe_key": "api-sent"},
    )
    external_push_delivery_repo.update_delivery(sent["id"], status="sent")
    external_push_delivery_repo.record_queued_delivery(
        tenant_id=2,
        user_id=1,
        delivery_key="external_push.dispatch:other-tenant",
        channel_id="webhook-api",
        channel_type="webhook",
        notification={"title": "Other tenant"},
    )

    response = authed.get(
        "/api/v1/settings/external-push-deliveries?status=failed&limit=10",
        headers=tenant_headers(authed),
    )
    data = response.get_json()["data"]

    assert response.status_code == 200
    assert data["tenant_id"] == 1
    assert data["total"] == 1
    assert data["items"][0]["id"] == failed["id"]
    assert data["items"][0]["status"] == "failed"
    assert data["items"][0]["last_error"] == "timeout"
    assert data["items"][0]["notification_summary"]["title"] == "API failed"
    assert data["stats"]["total"] == 2
    assert data["stats"]["failed"] == 1
    assert data["stats"]["sent"] == 1
    assert data["stats"]["by_status"]["queued"] == 0


def test_external_push_delivery_retry_requeues_failed_delivery(client, monkeypatch):
    import backend.application.external_push as external_push_module
    from backend.infrastructure.tasks import queue
    from backend.repositories import external_push_delivery_repo

    authed = login_api(client)
    failed = external_push_delivery_repo.record_queued_delivery(
        tenant_id=1,
        user_id=1,
        delivery_key="external_push.dispatch:retry-api",
        channel_id="webhook-retry",
        channel_type="webhook",
        notification={"title": "Retry API", "dedupe_key": "retry-api"},
    )
    external_push_delivery_repo.update_delivery(failed["id"], status="failed", last_error="timeout")
    monkeypatch.setattr(
        external_push_module.settings_repo,
        "list_external_push_channels",
        lambda *args, **kwargs: [
            {
                "id": "webhook-retry",
                "type": "webhook",
                "enabled": True,
                "config": {"webhook_url": "https://alerts.example.com/hook"},
            }
        ],
    )

    def fake_enqueue_task(name, func, *args, tenant_id=None, payload=None, idempotency_key=None, max_retries=0):
        return {"id": "retry-task-api", "status": "pending", "retry_count": 0}

    monkeypatch.setattr(queue, "enqueue_task", fake_enqueue_task)

    response = authed.post(
        f"/api/v1/settings/external-push-deliveries/{failed['id']}/retry",
        json={},
        headers=tenant_headers(authed, include_csrf=True),
    )
    data = response.get_json()["data"]

    assert response.status_code == 202
    assert data["status"] == "queued"
    assert data["task_id"] == "retry-task-api"
    assert data["channel_id"] == "webhook-retry"
    saved = external_push_delivery_repo.get_delivery(failed["id"])
    assert saved["status"] == "queued"
    assert saved["retry_count"] == 1
    assert saved["last_error"] == ""


def test_external_push_delivery_retry_rejects_non_retryable_delivery(client):
    from backend.repositories import external_push_delivery_repo

    authed = login_api(client)
    queued = external_push_delivery_repo.record_queued_delivery(
        tenant_id=1,
        user_id=1,
        delivery_key="external_push.dispatch:queued-api",
        channel_id="webhook-queued",
        channel_type="webhook",
        notification={"title": "Queued API", "dedupe_key": "queued-api"},
    )

    response = authed.post(
        f"/api/v1/settings/external-push-deliveries/{queued['id']}/retry",
        json={},
        headers=tenant_headers(authed, include_csrf=True),
    )
    data = response.get_json()

    assert response.status_code == 400
    assert data["code"] == 400
    assert "only failed or skipped deliveries can be retried" in data["message"]
