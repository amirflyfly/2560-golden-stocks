"""Operation logs repository."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from sqlalchemy import select

from backend.core.config import get_settings
from backend.db.models import OperationLog
from backend.db.session import session_scope
from backend.repositories.db import execute as sqlite_execute
from backend.repositories.db import q as sqlite_q


def _repo_backend() -> str:
    forced = (os.getenv("LOGS_REPOSITORY_BACKEND") or "auto").strip().lower()
    if forced in {"sqlite", "mysql"}:
        return forced
    settings = get_settings()
    environment = (settings.environment or "").strip().lower()
    if environment in {"prod", "production"}:
        return "mysql"
    return "sqlite"


def _dt(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


def _public_log(row: OperationLog | dict) -> dict:
    if isinstance(row, dict):
        return dict(row)
    return {
        "created_at": _dt(row.created_at),
        "username": row.username,
        "ip": row.ip,
        "action": row.action,
        "target_ids": row.target_ids,
        "detail": row.detail,
    }


def insert_log(action, target_ids_csv="", detail="", user_id=None, username="", ip="", user_agent=""):
    username = username or ""
    ip = ip or ""
    user_agent = user_agent or ""
    safe_detail = (detail or "")[:1000]
    if _repo_backend() == "sqlite":
        return sqlite_execute(
            "INSERT INTO operation_logs (action, target_ids, detail, user_id, username, ip, user_agent) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (action, target_ids_csv, safe_detail, user_id, username[:64], ip[:64], user_agent[:200]),
        )
    with session_scope() as session:
        session.add(
            OperationLog(
                action=action,
                target_ids=target_ids_csv or "",
                detail=safe_detail,
                user_id=user_id,
                username=username[:64],
                ip=ip[:64],
                user_agent=user_agent[:200],
                created_at=datetime.now(),
            )
        )
        session.flush()
    return 1


def recent_logs(limit=15):
    safe_limit = max(1, min(int(limit or 15), 200))
    if _repo_backend() == "sqlite":
        return sqlite_q(
            "SELECT created_at, username, ip, action, target_ids, detail FROM operation_logs ORDER BY id DESC LIMIT ?",
            (safe_limit,),
        )
    with session_scope() as session:
        rows = session.execute(
            select(OperationLog).order_by(OperationLog.id.desc()).limit(safe_limit)
        ).scalars().all()
        return [_public_log(row) for row in rows]
