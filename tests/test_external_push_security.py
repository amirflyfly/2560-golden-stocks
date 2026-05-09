from __future__ import annotations


def test_external_push_channel_storage_encrypts_sensitive_config(monkeypatch):
    from backend.repositories import settings_repo

    monkeypatch.setenv("EXTERNAL_PUSH_SECRET_KEY", "unit-test-secret")
    monkeypatch.setenv("EXTERNAL_PUSH_KMS_PROVIDER", "local-env")
    monkeypatch.setenv("EXTERNAL_PUSH_KMS_KEY_ID", "unit-key")
    stored = settings_repo._external_push_channel_for_storage(
        {
            "id": "ch-1",
            "type": "webhook",
            "enabled": True,
            "config": {
                "webhook_url": "https://alerts.example.com/hook",
                "bearer_token": "secret-token",
                "headers": {"X-Source": "strategy"},
            },
            "metadata": {},
        }
    )

    assert stored["config"]["headers"] == {"X-Source": "strategy"}
    assert "webhook_url" not in stored["config"]
    assert "bearer_token" not in stored["config"]
    assert settings_repo.EXTERNAL_PUSH_ENCRYPTED_MARKER in stored["config"]
    assert "secret-token" not in str(stored)
    assert stored["metadata"]["encryption_status"] == "encrypted"
    assert stored["metadata"]["encryption_alg"] == "kms-envelope-v1"
    assert stored["metadata"]["key_provider"] == "local-env"
    assert stored["metadata"]["key_id"] == "unit-key"
    encrypted = stored["config"][settings_repo.EXTERNAL_PUSH_ENCRYPTED_MARKER]["bearer_token"]
    assert encrypted["alg"] == "kms-envelope-v1"
    assert encrypted["wrapped_data_key"]

    restored = settings_repo._external_push_channel_for_read(stored, include_secrets=True)
    assert restored["config"]["webhook_url"] == "https://alerts.example.com/hook"
    assert restored["config"]["bearer_token"] == "secret-token"


def test_external_push_channel_storage_reads_legacy_ciphertext(monkeypatch):
    import base64
    import hashlib
    import hmac
    import json
    import os

    from backend.repositories import settings_repo

    secret = "unit-test-secret"
    monkeypatch.setenv("EXTERNAL_PUSH_SECRET_KEY", secret)
    key = hashlib.sha256(secret.encode("utf-8")).digest()
    plaintext = json.dumps("legacy-token", ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    nonce = os.urandom(16)
    stream = settings_repo._secret_stream(key, nonce, len(plaintext))
    ciphertext = bytes(byte ^ stream[index] for index, byte in enumerate(plaintext))
    legacy = {
        "alg": settings_repo.EXTERNAL_PUSH_LEGACY_ENCRYPTION_ALG,
        "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
        "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
        "mac": base64.urlsafe_b64encode(hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()).decode("ascii"),
    }

    restored = settings_repo._external_push_channel_for_read(
        {
            "id": "ch-legacy",
            "type": "webhook",
            "enabled": True,
            "config": {settings_repo.EXTERNAL_PUSH_ENCRYPTED_MARKER: {"bearer_token": legacy}},
            "metadata": {},
        },
        include_secrets=True,
    )

    assert restored["config"]["bearer_token"] == "legacy-token"


def test_external_push_dispatch_for_alert_queues_default_delivery(monkeypatch):
    import backend.application.external_push as external_push_module
    from backend.application.external_push import ExternalPushService

    configs = [
        {
            "id": "webhook-1",
            "type": "webhook",
            "enabled": True,
            "config": {"webhook_url": "https://alerts.example.com/hook"},
        }
    ]
    queued = []
    deliveries = []

    monkeypatch.setattr(external_push_module.settings_repo, "list_external_push_channels", lambda *args, **kwargs: configs)
    monkeypatch.setattr(
        external_push_module.external_push_delivery_repo,
        "record_queued_delivery",
        lambda **kwargs: deliveries.append(kwargs) or {"id": 7},
    )
    monkeypatch.setattr(
        external_push_module.external_push_delivery_repo,
        "update_delivery",
        lambda *args, **kwargs: deliveries.append({"update_args": args, **kwargs}) or {},
    )

    def fake_enqueue_task(name, func, *args, tenant_id=None, payload=None, idempotency_key=None, max_retries=0):
        queued.append(
            {
                "name": name,
                "tenant_id": tenant_id,
                "payload": payload,
                "idempotency_key": idempotency_key,
                "max_retries": max_retries,
            }
        )
        return {"id": "task-1", "status": "pending"}

    from backend.infrastructure.tasks import queue

    monkeypatch.setattr(queue, "enqueue_task", fake_enqueue_task)
    result = ExternalPushService().dispatch_for_alert(
        tenant_id=1,
        user_id=2,
        alert_rule={"id": "rule-1", "channels": ["webhook"]},
        notification={"title": "Alert", "dedupe_key": "alert-1"},
    )

    assert result[0]["status"] == "queued"
    assert result[0]["task_id"] == "task-1"
    assert queued[0]["name"] == "external_push.dispatch"
    assert queued[0]["max_retries"] == 2
    assert queued[0]["payload"]["delivery_id"] == 7
    assert queued[0]["payload"]["delivery_key"].startswith("external_push.dispatch:")
    assert deliveries[0]["channel_id"] == "webhook-1"
    assert deliveries[0]["channel_type"] == "webhook"
    assert deliveries[1]["task_id"] == "task-1"


def test_external_push_retry_delivery_requeues_failed_delivery(monkeypatch):
    import backend.application.external_push as external_push_module
    from backend.application.external_push import ExternalPushService

    delivery = {
        "id": 5,
        "tenant_id": 1,
        "user_id": 2,
        "delivery_key": "external_push.dispatch:failed",
        "status": "failed",
        "channel_id": "webhook-1",
        "channel_type": "webhook",
        "notification_payload": {"title": "Retry alert", "dedupe_key": "retry-alert"},
        "notification_summary": {"title": "Retry alert"},
    }
    configs = [{"id": "webhook-1", "type": "webhook", "enabled": True, "config": {"webhook_url": "https://alerts.example.com/hook"}}]
    queued = []

    monkeypatch.setattr(external_push_module.external_push_delivery_repo, "get_delivery", lambda delivery_id: delivery if delivery_id == 5 else {})
    monkeypatch.setattr(external_push_module.settings_repo, "list_external_push_channels", lambda *args, **kwargs: configs)
    monkeypatch.setattr(external_push_module.external_push_delivery_repo, "record_queued_delivery", lambda **kwargs: {"id": 6})
    monkeypatch.setattr(external_push_module.external_push_delivery_repo, "update_delivery", lambda *args, **kwargs: {})

    def fake_enqueue_task(name, func, *args, tenant_id=None, payload=None, idempotency_key=None, max_retries=0):
        queued.append({"name": name, "payload": payload, "idempotency_key": idempotency_key})
        return {"id": "retry-task", "status": "pending"}

    from backend.infrastructure.tasks import queue

    monkeypatch.setattr(queue, "enqueue_task", fake_enqueue_task)

    result = ExternalPushService().retry_delivery(1, 5)

    assert result["status"] == "queued"
    assert result["task_id"] == "retry-task"
    assert queued[0]["payload"]["notification"]["title"] == "Retry alert"
    assert queued[0]["payload"]["retry_count"] == 1


def test_external_push_dispatch_task_updates_delivery_sent(monkeypatch):
    import backend.application.external_push as external_push_module

    configs = [
        {
            "id": "webhook-1",
            "type": "webhook",
            "enabled": True,
            "config": {"webhook_url": "https://alerts.example.com/hook"},
        }
    ]
    updates = []

    monkeypatch.setattr(external_push_module.settings_repo, "list_external_push_channels", lambda *args, **kwargs: configs)
    monkeypatch.setattr(external_push_module, "_require_public_https_url", lambda value: str(value or ""))
    monkeypatch.setattr(external_push_module.ExternalPushService, "_post_json", lambda self, url, payload, headers: {"ok": True, "status": "sent", "message": "webhook accepted", "status_code": 204})
    monkeypatch.setattr(
        external_push_module.external_push_delivery_repo,
        "update_delivery",
        lambda *args, **kwargs: updates.append({"args": args, **kwargs}) or {},
    )

    result = external_push_module.dispatch_external_push_task(
        {
            "tenant_id": 1,
            "user_id": 2,
            "channel_id": "webhook-1",
            "channel_type": "webhook",
            "delivery_id": 9,
            "delivery_key": "external_push.dispatch:test",
            "task_id": "task-1",
            "retry_count": 1,
            "notification": {"title": "Alert"},
        }
    )

    assert result["status"] == "sent"
    assert updates[0]["args"] == (9,)
    assert updates[0]["status"] == "sent"
    assert updates[0]["task_id"] == "task-1"
    assert updates[0]["retry_count"] == 1
    assert updates[0]["last_error"] == ""


def test_external_push_dispatch_task_updates_delivery_skipped(monkeypatch):
    import backend.application.external_push as external_push_module

    updates = []

    monkeypatch.setattr(external_push_module.settings_repo, "list_external_push_channels", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        external_push_module.external_push_delivery_repo,
        "update_delivery",
        lambda *args, **kwargs: updates.append({"args": args, **kwargs}) or {},
    )

    result = external_push_module.dispatch_external_push_task(
        {
            "tenant_id": 1,
            "user_id": 2,
            "channel_id": "missing",
            "channel_type": "webhook",
            "delivery_id": 9,
            "delivery_key": "external_push.dispatch:test",
            "notification": {"title": "Alert"},
        }
    )

    assert result["status"] == "skipped"
    assert updates[0]["status"] == "skipped"
    assert updates[0]["last_error"] == "external push channel not found"


def test_external_push_dispatch_task_creates_failure_notification(monkeypatch):
    import backend.application.external_push as external_push_module

    configs = [
        {
            "id": "webhook-1",
            "type": "webhook",
            "enabled": True,
            "config": {"webhook_url": "https://alerts.example.com/hook"},
        }
    ]
    notifications = []

    monkeypatch.setattr(external_push_module.settings_repo, "list_external_push_channels", lambda *args, **kwargs: configs)
    monkeypatch.setattr(external_push_module.ExternalPushService, "_post_json", lambda self, url, payload, headers: {"ok": False, "status": "failed", "message": "timeout", "status_code": 504})
    monkeypatch.setattr(external_push_module.external_push_delivery_repo, "update_delivery", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        external_push_module.settings_repo,
        "upsert_notification",
        lambda *args, **kwargs: notifications.append({"args": args, "payload": args[2]}) or {},
    )

    result = external_push_module.dispatch_external_push_task(
        {
            "tenant_id": 1,
            "user_id": 2,
            "channel_id": "webhook-1",
            "channel_type": "webhook",
            "delivery_id": 9,
            "delivery_key": "external_push.dispatch:failed",
            "task_id": "task-1",
            "notification": {"title": "Alert"},
        }
    )

    assert result["status"] == "failed"
    assert notifications[0]["args"][:2] == (1, 2)
    assert notifications[0]["payload"]["type"] == "external_push_delivery_failed"
    assert notifications[0]["payload"]["metadata"]["task_id"] == "task-1"


def test_external_push_delivery_repo_records_payload_and_stats(monkeypatch):
    import os
    import tempfile

    import backend.repositories.db as db_module
    from backend.repositories import external_push_delivery_repo

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = db_path
    monkeypatch.setenv("EXTERNAL_PUSH_DELIVERY_REPOSITORY_BACKEND", "sqlite")
    try:
        delivery = external_push_delivery_repo.record_queued_delivery(
            tenant_id=1,
            user_id=2,
            delivery_key="external_push.dispatch:repo",
            channel_id="webhook-1",
            channel_type="webhook",
            notification={"title": "Repo alert", "dedupe_key": "repo-alert"},
        )
        external_push_delivery_repo.update_delivery(delivery["id"], status="failed", last_error="timeout")
        stats = external_push_delivery_repo.delivery_stats(tenant_id=1)
        saved = external_push_delivery_repo.get_delivery(delivery["id"])
    finally:
        db_module.DB_PATH = original_db_path
        os.close(db_fd)
        os.unlink(db_path)

    assert saved["notification_payload"]["title"] == "Repo alert"
    assert saved["status"] == "failed"
    assert stats["failed"] == 1
    assert stats["total"] == 1


def test_external_push_delivery_repo_clears_terminal_state_when_requeued(monkeypatch):
    import os
    import tempfile

    import backend.repositories.db as db_module
    from backend.repositories import external_push_delivery_repo

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = db_path
    monkeypatch.setenv("EXTERNAL_PUSH_DELIVERY_REPOSITORY_BACKEND", "sqlite")
    try:
        first = external_push_delivery_repo.record_queued_delivery(
            tenant_id=1,
            user_id=2,
            delivery_key="external_push.dispatch:requeue",
            channel_id="webhook-1",
            channel_type="webhook",
            notification={"title": "First alert", "dedupe_key": "requeue-alert"},
        )
        external_push_delivery_repo.update_delivery(first["id"], status="failed", last_error="timeout")
        second = external_push_delivery_repo.record_queued_delivery(
            tenant_id=1,
            user_id=2,
            delivery_key="external_push.dispatch:requeue",
            channel_id="webhook-1",
            channel_type="webhook",
            notification={"title": "First alert", "dedupe_key": "requeue-alert"},
            retry_count=1,
        )
    finally:
        db_module.DB_PATH = original_db_path
        os.close(db_fd)
        os.unlink(db_path)

    assert second["id"] == first["id"]
    assert second["status"] == "queued"
    assert second["retry_count"] == 1
    assert second["last_error"] == ""
    assert second["failed_at"] is None
