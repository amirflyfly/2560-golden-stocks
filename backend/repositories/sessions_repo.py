"""Session repository."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select

from backend.core.config import get_settings
from backend.db.models import User, UserSession
from backend.db.session import session_scope
from backend.repositories.db import execute as sqlite_execute
from backend.repositories.db import q1 as sqlite_q1


def _repo_backend() -> str:
    forced = (os.getenv("AUTH_REPOSITORY_BACKEND") or "auto").strip().lower()
    if forced in {"sqlite", "mysql"}:
        return forced
    settings = get_settings()
    environment = (settings.environment or "").strip().lower()
    if environment in {"prod", "production"}:
        return "mysql"
    return "sqlite"


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _format_datetime(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


def create_session(session_token: str, user_id: int, expires_at_iso: str):
    if _repo_backend() == "sqlite":
        return sqlite_execute(
            "INSERT INTO sessions (session_token, user_id, expires_at, last_seen_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (session_token, int(user_id), expires_at_iso),
        )
    now = datetime.now()
    with session_scope() as session:
        session.add(
            UserSession(
                session_token=session_token,
                user_id=int(user_id),
                created_at=now,
                expires_at=_parse_datetime(expires_at_iso),
                last_seen_at=now,
            )
        )
        session.flush()
    return 1


def get_session(session_token: str):
    if _repo_backend() == "sqlite":
        return sqlite_q1(
            """SELECT s.session_token, s.user_id, s.expires_at, s.last_seen_at, u.username, u.role, u.is_active
               FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.session_token=? AND s.expires_at >= datetime('now')""",
            (session_token,),
        )
    with session_scope() as session:
        row = session.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(UserSession.session_token == session_token, UserSession.expires_at >= datetime.now())
        ).first()
        if row is None:
            return None
        auth_session, user = row
        from backend.repositories import users_repo

        user_row = users_repo.get_user_by_id(user.id) or {}
        return {
            "session_token": auth_session.session_token,
            "user_id": auth_session.user_id,
            "expires_at": _format_datetime(auth_session.expires_at),
            "last_seen_at": _format_datetime(auth_session.last_seen_at),
            "username": user.username,
            "role": user_row.get("role") or "editor",
            "is_active": user_row.get("is_active", 0),
        }


def touch_session(session_token: str):
    if _repo_backend() == "sqlite":
        return sqlite_execute("UPDATE sessions SET last_seen_at=CURRENT_TIMESTAMP WHERE session_token=?", (session_token,))
    with session_scope() as session:
        auth_session = session.execute(
            select(UserSession).where(UserSession.session_token == session_token)
        ).scalar_one_or_none()
        if auth_session is None:
            return 0
        auth_session.last_seen_at = datetime.now()
        session.flush()
    return 1


def delete_session(session_token: str):
    if _repo_backend() == "sqlite":
        return sqlite_execute("DELETE FROM sessions WHERE session_token=?", (session_token,))
    with session_scope() as session:
        result = session.execute(delete(UserSession).where(UserSession.session_token == session_token))
        return result.rowcount or 0


def delete_expired_sessions():
    if _repo_backend() == "sqlite":
        return sqlite_execute("DELETE FROM sessions WHERE expires_at < datetime('now')")
    with session_scope() as session:
        result = session.execute(delete(UserSession).where(UserSession.expires_at < datetime.now()))
        return result.rowcount or 0
