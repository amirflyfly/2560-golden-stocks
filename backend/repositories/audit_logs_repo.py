"""Repository helpers for structured audit logs."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from typing import Any

from sqlalchemy import select

from backend.core.config import get_settings
from backend.db.models import AuditLog
from backend.db.session import session_scope
from backend.repositories.db import execute as sqlite_execute
from backend.repositories.db import q as sqlite_q


def _repo_backend() -> str:
    forced = (os.getenv("AUDIT_REPOSITORY_BACKEND") or "auto").strip().lower()
    if forced in {"sqlite", "mysql"}:
        return forced
    settings = get_settings()
    environment = (settings.environment or "").strip().lower()
    if environment in {"prod", "production"}:
        return "mysql"
    return "sqlite"


def _format_datetime(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


def _public_audit_log(row: AuditLog | dict) -> dict:
    if isinstance(row, dict):
        item = dict(row)
    else:
        item = {
            "id": row.id,
            "user_id": row.user_id,
            "username": row.username,
            "tenant_id": row.tenant_id,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "result": row.result,
            "ip": row.ip,
            "user_agent": row.user_agent,
            "detail_json": row.detail_json,
            "created_at": _format_datetime(row.created_at),
        }
    raw_detail = item.get("detail_json") or "{}"
    try:
        item["detail"] = json.loads(raw_detail)
    except (TypeError, json.JSONDecodeError):
        item["detail"] = {}
    item["integrity_hash"] = item["detail"].get("integrity_hash", "")
    return item


def build_integrity_hash(*, user_id: int | None, username: str, tenant_id: int | None, action: str, resource_type: str, resource_id: str, result: str, detail: dict[str, Any] | None) -> str:
    payload = {
        "user_id": user_id,
        "username": username or "",
        "tenant_id": tenant_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id or "",
        "result": result or "success",
        "detail": detail or {},
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def insert_audit_log(
    *,
    user_id: int | None,
    username: str,
    tenant_id: int | None,
    action: str,
    resource_type: str,
    resource_id: str = "",
    result: str = "success",
    ip: str = "",
    user_agent: str = "",
    detail: dict[str, Any] | None = None,
) -> int:
    safe_detail = detail or {}
    integrity_hash = build_integrity_hash(
        user_id=user_id,
        username=username or "",
        tenant_id=tenant_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id or "",
        result=result or "success",
        detail=safe_detail,
    )
    safe_detail = {**safe_detail, "integrity_hash": integrity_hash}
    detail_json = json.dumps(safe_detail, ensure_ascii=False, sort_keys=True)
    if _repo_backend() == "sqlite":
        return sqlite_execute(
            """INSERT INTO audit_logs (
                user_id, username, tenant_id, action, resource_type, resource_id,
                result, ip, user_agent, detail_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                username or "",
                tenant_id,
                action,
                resource_type,
                resource_id or "",
                result or "success",
                ip or "",
                user_agent or "",
                detail_json,
            ),
        )
    with session_scope() as session:
        session.add(
            AuditLog(
                user_id=user_id,
                username=username or "",
                tenant_id=tenant_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id or "",
                result=result or "success",
                ip=ip or "",
                user_agent=user_agent or "",
                detail_json=detail_json,
                created_at=datetime.now(),
            )
        )
        session.flush()
    return 1


def list_audit_logs(
    *,
    limit: int = 50,
    tenant_id: int | None = None,
    action: str | None = None,
    result: str | None = None,
) -> list[dict]:
    safe_limit = max(1, min(int(limit or 50), 200))
    if _repo_backend() == "sqlite":
        where = []
        params: list[Any] = []
        if tenant_id is not None:
            where.append("tenant_id=?")
            params.append(int(tenant_id))
        if action:
            where.append("action=?")
            params.append(action)
        if result:
            where.append("result=?")
            params.append(result)
        sql = "SELECT * FROM audit_logs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(safe_limit)
        return [_public_audit_log(item) for item in sqlite_q(sql, tuple(params))]

    with session_scope() as session:
        statement = select(AuditLog)
        if tenant_id is not None:
            statement = statement.where(AuditLog.tenant_id == int(tenant_id))
        if action:
            statement = statement.where(AuditLog.action == action)
        if result:
            statement = statement.where(AuditLog.result == result)
        rows = session.execute(statement.order_by(AuditLog.id.desc()).limit(safe_limit)).scalars().all()
        return [_public_audit_log(row) for row in rows]
