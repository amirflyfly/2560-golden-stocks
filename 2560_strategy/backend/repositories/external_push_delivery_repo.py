"""Persistence for external push delivery audit records."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from backend.core.config import get_settings
from backend.db.models.external_push import ExternalPushDelivery
from backend.db.session import session_scope
from backend.repositories.db import execute as sqlite_execute
from backend.repositories.db import execute_many as sqlite_execute_many
from backend.repositories.db import q as sqlite_q
from backend.repositories.db import q1 as sqlite_q1


DELIVERY_STATUSES = {"queued", "sent", "failed", "skipped"}


def _repo_backend() -> str:
    forced = (os.getenv("EXTERNAL_PUSH_DELIVERY_REPOSITORY_BACKEND") or "auto").strip().lower()
    if forced in {"sqlite", "mysql"}:
        return forced
    settings = get_settings()
    return "mysql" if (settings.environment or "").strip().lower() in {"prod", "production"} else "sqlite"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def ensure_schema() -> None:
    if _repo_backend() != "sqlite":
        return
    sqlite_execute(
        """CREATE TABLE IF NOT EXISTS external_push_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            user_id INTEGER DEFAULT NULL,
            delivery_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            task_id TEXT DEFAULT '',
            retry_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT DEFAULT '',
            channel_id TEXT DEFAULT '',
            channel_type TEXT DEFAULT '',
            notification_summary TEXT DEFAULT '{}',
            notification_payload TEXT DEFAULT '{}',
            queued_at TEXT DEFAULT NULL,
            sent_at TEXT DEFAULT NULL,
            failed_at TEXT DEFAULT NULL,
            skipped_at TEXT DEFAULT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, delivery_key)
        )"""
    )
    sqlite_execute("CREATE INDEX IF NOT EXISTS idx_external_push_deliveries_tenant_created ON external_push_deliveries(tenant_id, created_at)")
    sqlite_execute("CREATE INDEX IF NOT EXISTS idx_external_push_deliveries_status ON external_push_deliveries(status)")
    sqlite_execute("CREATE INDEX IF NOT EXISTS idx_external_push_deliveries_task_id ON external_push_deliveries(task_id)")
    sqlite_execute("CREATE INDEX IF NOT EXISTS idx_external_push_deliveries_channel ON external_push_deliveries(channel_type, channel_id)")


def record_queued_delivery(
    *,
    tenant_id: int,
    user_id: int | None,
    delivery_key: str,
    channel_id: str,
    channel_type: str,
    notification: dict,
    retry_count: int = 0,
) -> dict:
    ensure_schema()
    now = _now()
    summary = notification_summary(notification)
    if _repo_backend() == "sqlite":
        sqlite_execute_many(
            """INSERT INTO external_push_deliveries (
                tenant_id, user_id, delivery_key, status, task_id, retry_count, last_error,
                channel_id, channel_type, notification_summary, notification_payload, queued_at, sent_at, failed_at, skipped_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, 'queued', '', ?, '', ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
            ON CONFLICT(tenant_id, delivery_key) DO UPDATE SET
                status='queued',
                user_id=excluded.user_id,
                task_id='',
                retry_count=excluded.retry_count,
                last_error='',
                channel_id=excluded.channel_id,
                channel_type=excluded.channel_type,
                notification_summary=excluded.notification_summary,
                notification_payload=excluded.notification_payload,
                queued_at=excluded.queued_at,
                sent_at=NULL,
                failed_at=NULL,
                skipped_at=NULL,
                updated_at=excluded.updated_at""",
            [
                (
                    int(tenant_id or 0),
                    int(user_id) if user_id is not None else None,
                    str(delivery_key or ""),
                    max(0, int(retry_count or 0)),
                    str(channel_id or ""),
                    str(channel_type or ""),
                    _json(summary),
                    _json(notification),
                    now,
                    now,
                    now,
                )
            ],
        )
        return get_delivery_by_key(tenant_id, delivery_key) or {}
    with session_scope() as session:
        statement = mysql_insert(ExternalPushDelivery).values(
            tenant_id=int(tenant_id or 0),
            user_id=int(user_id) if user_id is not None else None,
            delivery_key=str(delivery_key or ""),
            status="queued",
            task_id="",
            retry_count=max(0, int(retry_count or 0)),
            last_error="",
            channel_id=str(channel_id or ""),
            channel_type=str(channel_type or ""),
            notification_summary=summary,
            notification_payload=notification if isinstance(notification, dict) else {},
            queued_at=datetime.fromisoformat(now),
        )
        statement = statement.on_duplicate_key_update(
            status="queued",
            user_id=statement.inserted.user_id,
            task_id="",
            retry_count=statement.inserted.retry_count,
            last_error="",
            channel_id=statement.inserted.channel_id,
            channel_type=statement.inserted.channel_type,
            notification_summary=statement.inserted.notification_summary,
            notification_payload=statement.inserted.notification_payload,
            queued_at=statement.inserted.queued_at,
            sent_at=None,
            failed_at=None,
            skipped_at=None,
            updated_at=func.now(),
        )
        session.execute(statement)
    return get_delivery_by_key(tenant_id, delivery_key) or {}


def update_delivery(
    delivery_id: int | None = None,
    *,
    tenant_id: int | None = None,
    delivery_key: str | None = None,
    status: str | None = None,
    task_id: str | None = None,
    retry_count: int | None = None,
    last_error: str | None = None,
) -> dict:
    ensure_schema()
    normalized_status = _normalize_status(status)
    now = _now()
    timestamp_updates = _status_timestamps(normalized_status, now)
    if _repo_backend() == "sqlite":
        where, params = _sqlite_identity(delivery_id, tenant_id, delivery_key)
        assignments = ["updated_at=?"]
        values: list[Any] = [now]
        if normalized_status:
            assignments.append("status=?")
            values.append(normalized_status)
        if task_id is not None:
            assignments.append("task_id=?")
            values.append(str(task_id or ""))
        if retry_count is not None:
            assignments.append("retry_count=?")
            values.append(max(0, int(retry_count or 0)))
        if last_error is not None:
            assignments.append("last_error=?")
            values.append(str(last_error or "")[:1000])
        for column, value in timestamp_updates.items():
            assignments.append(f"{column}=?")
            values.append(value)
        sqlite_execute(f"UPDATE external_push_deliveries SET {', '.join(assignments)} WHERE {where}", tuple(values + params))
        return get_delivery(delivery_id) if delivery_id else (get_delivery_by_key(int(tenant_id or 0), str(delivery_key or "")) or {})
    with session_scope() as session:
        row = _mysql_get_row(session, delivery_id, tenant_id, delivery_key)
        if row is None:
            return {}
        if normalized_status:
            row.status = normalized_status
        if task_id is not None:
            row.task_id = str(task_id or "")
        if retry_count is not None:
            row.retry_count = max(0, int(retry_count or 0))
        if last_error is not None:
            row.last_error = str(last_error or "")[:1000]
        for column, value in timestamp_updates.items():
            setattr(row, column, datetime.fromisoformat(value))
        row.updated_at = datetime.fromisoformat(now)
        session.flush()
        delivery_id = row.id
    return get_delivery(delivery_id)


def get_delivery(delivery_id: int | None) -> dict:
    ensure_schema()
    if not delivery_id:
        return {}
    if _repo_backend() == "sqlite":
        row = sqlite_q1("SELECT * FROM external_push_deliveries WHERE id=?", (int(delivery_id),))
        return _delivery_item(row)
    with session_scope() as session:
        row = session.get(ExternalPushDelivery, int(delivery_id))
        return _delivery_item(_model_delivery(row))


def get_delivery_by_key(tenant_id: int, delivery_key: str) -> dict | None:
    ensure_schema()
    if _repo_backend() == "sqlite":
        row = sqlite_q1(
            "SELECT * FROM external_push_deliveries WHERE tenant_id=? AND delivery_key=?",
            (int(tenant_id or 0), str(delivery_key or "")),
        )
        return _delivery_item(row) if row else None
    with session_scope() as session:
        row = session.execute(
            select(ExternalPushDelivery).where(
                ExternalPushDelivery.tenant_id == int(tenant_id or 0),
                ExternalPushDelivery.delivery_key == str(delivery_key or ""),
            )
        ).scalar_one_or_none()
        return _delivery_item(_model_delivery(row)) if row else None


def list_deliveries(*, tenant_id: int | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
    ensure_schema()
    safe_limit = max(1, min(int(limit or 50), 200))
    normalized_status = _normalize_status(status)
    if _repo_backend() == "sqlite":
        where = []
        params: list[Any] = []
        if tenant_id is not None:
            where.append("tenant_id=?")
            params.append(int(tenant_id or 0))
        if normalized_status:
            where.append("status=?")
            params.append(normalized_status)
        sql = "SELECT * FROM external_push_deliveries"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        rows = sqlite_q(sql, tuple(params + [safe_limit]))
        return [_delivery_item(row) for row in rows]
    with session_scope() as session:
        query = select(ExternalPushDelivery)
        if tenant_id is not None:
            query = query.where(ExternalPushDelivery.tenant_id == int(tenant_id or 0))
        if normalized_status:
            query = query.where(ExternalPushDelivery.status == normalized_status)
        rows = session.execute(query.order_by(ExternalPushDelivery.id.desc()).limit(safe_limit)).scalars().all()
        return [_delivery_item(_model_delivery(row)) for row in rows]


def delivery_stats(*, tenant_id: int | None = None) -> dict:
    ensure_schema()
    if _repo_backend() == "sqlite":
        if tenant_id is None:
            rows = sqlite_q("SELECT status, COUNT(*) AS cnt FROM external_push_deliveries GROUP BY status")
        else:
            rows = sqlite_q(
                "SELECT status, COUNT(*) AS cnt FROM external_push_deliveries WHERE tenant_id=? GROUP BY status",
                (int(tenant_id or 0),),
            )
        by_status = {str(row.get("status") or ""): int(row.get("cnt") or 0) for row in rows}
    else:
        with session_scope() as session:
            query = select(ExternalPushDelivery.status, func.count(ExternalPushDelivery.id))
            if tenant_id is not None:
                query = query.where(ExternalPushDelivery.tenant_id == int(tenant_id or 0))
            rows = session.execute(query.group_by(ExternalPushDelivery.status)).all()
        by_status = {str(status or ""): int(count or 0) for status, count in rows}
    return {
        "total": sum(by_status.values()),
        "by_status": {status: by_status.get(status, 0) for status in sorted(DELIVERY_STATUSES)},
        "failed": by_status.get("failed", 0),
        "queued": by_status.get("queued", 0),
        "sent": by_status.get("sent", 0),
        "skipped": by_status.get("skipped", 0),
    }


def notification_summary(notification: dict) -> dict:
    value = notification if isinstance(notification, dict) else {}
    entity = value.get("entity") if isinstance(value.get("entity"), dict) else {}
    match = value.get("match") if isinstance(value.get("match"), dict) else {}
    return {
        "id": str(value.get("id") or ""),
        "dedupe_key": str(value.get("dedupe_key") or ""),
        "title": str(value.get("title") or "")[:200],
        "rule_id": str(value.get("rule_id") or ""),
        "rule_name": str(value.get("rule_name") or "")[:200],
        "scope": str(value.get("scope") or ""),
        "entity": {
            "id": str(entity.get("id") or ""),
            "symbol": str(entity.get("symbol") or ""),
        },
        "match": {
            "field": str(match.get("field") or ""),
            "metric": str(match.get("metric") or ""),
        },
    }


def _normalize_status(status: str | None) -> str | None:
    if status is None:
        return None
    normalized = str(status or "").strip().lower()
    return normalized if normalized in DELIVERY_STATUSES else "failed"


def _status_timestamps(status: str | None, value: str) -> dict[str, str]:
    if status == "sent":
        return {"sent_at": value}
    if status == "failed":
        return {"failed_at": value}
    if status == "skipped":
        return {"skipped_at": value}
    if status == "queued":
        return {"queued_at": value}
    return {}


def _sqlite_identity(delivery_id: int | None, tenant_id: int | None, delivery_key: str | None) -> tuple[str, list[Any]]:
    if delivery_id:
        return "id=?", [int(delivery_id)]
    return "tenant_id=? AND delivery_key=?", [int(tenant_id or 0), str(delivery_key or "")]


def _loads(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    try:
        decoded = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _delivery_item(row: dict | None) -> dict:
    if not row:
        return {}
    item = dict(row)
    item["notification_summary"] = _loads(item.get("notification_summary"))
    item["notification_payload"] = _loads(item.get("notification_payload"))
    return item


def _model_delivery(row: ExternalPushDelivery | None) -> dict:
    if row is None:
        return {}
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "user_id": row.user_id,
        "delivery_key": row.delivery_key,
        "status": row.status,
        "task_id": row.task_id,
        "retry_count": row.retry_count,
        "last_error": row.last_error,
        "channel_id": row.channel_id,
        "channel_type": row.channel_type,
        "notification_summary": row.notification_summary,
        "notification_payload": row.notification_payload,
        "queued_at": row.queued_at.isoformat(timespec="seconds") if row.queued_at else None,
        "sent_at": row.sent_at.isoformat(timespec="seconds") if row.sent_at else None,
        "failed_at": row.failed_at.isoformat(timespec="seconds") if row.failed_at else None,
        "skipped_at": row.skipped_at.isoformat(timespec="seconds") if row.skipped_at else None,
        "created_at": row.created_at.isoformat(timespec="seconds") if row.created_at else None,
        "updated_at": row.updated_at.isoformat(timespec="seconds") if row.updated_at else None,
    }


def _mysql_get_row(session, delivery_id: int | None, tenant_id: int | None, delivery_key: str | None):
    if delivery_id:
        return session.get(ExternalPushDelivery, int(delivery_id))
    return session.execute(
        select(ExternalPushDelivery).where(
            ExternalPushDelivery.tenant_id == int(tenant_id or 0),
            ExternalPushDelivery.delivery_key == str(delivery_key or ""),
        )
    ).scalar_one_or_none()
