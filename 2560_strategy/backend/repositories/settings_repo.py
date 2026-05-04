"""UI settings and saved filter persistence."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from backend.core.config import get_settings
from backend.db.models import SavedFilter, UiSetting
from backend.db.session import session_scope
from backend.repositories.db import execute as sqlite_execute
from backend.repositories.db import q as sqlite_q
from backend.repositories.db import q1 as sqlite_q1


TRADINGAGENTS_RUNTIME_CONFIG_KEY = "tradingagents_runtime_config"


DEFAULT_TRADINGAGENTS_RUNTIME_CONFIG = {
    "llm_provider": "openai",
    "backend_url": "https://api.openai.com/v1",
    "deep_think_llm": "gpt-4o",
    "quick_think_llm": "gpt-4o-mini",
    "max_debate_rounds": 2,
    "max_risk_discuss_rounds": 1,
    "api_key": "",
}


def _repo_backend() -> str:
    forced = (os.getenv("SETTINGS_REPOSITORY_BACKEND") or "auto").strip().lower()
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


def _public_saved_filter(row: SavedFilter | dict) -> dict:
    if isinstance(row, dict):
        return dict(row)
    return {
        "id": row.id,
        "name": row.name,
        "query_string": row.query_string,
        "created_at": _dt(row.created_at),
    }


def get_saved_filters(limit=12):
    safe_limit = max(1, min(int(limit or 12), 200))
    if _repo_backend() == "sqlite":
        return sqlite_q(
            "SELECT id, name, query_string, created_at "
            "FROM saved_filters ORDER BY id DESC LIMIT ?",
            (safe_limit,),
        )
    with session_scope() as session:
        rows = session.execute(
            select(SavedFilter).order_by(SavedFilter.id.desc()).limit(safe_limit)
        ).scalars().all()
        return [_public_saved_filter(row) for row in rows]


def delete_saved_filter(filter_id):
    if _repo_backend() == "sqlite":
        return sqlite_execute("DELETE FROM saved_filters WHERE id=?", (filter_id,))
    with session_scope() as session:
        result = session.execute(delete(SavedFilter).where(SavedFilter.id == int(filter_id)))
        return result.rowcount or 0


def rename_saved_filter(filter_id, new_name):
    if _repo_backend() == "sqlite":
        return sqlite_execute("UPDATE saved_filters SET name=? WHERE id=?", (new_name, filter_id))
    with session_scope() as session:
        row = session.get(SavedFilter, int(filter_id))
        if row is None:
            return 0
        row.name = new_name
        session.flush()
    return 1


def create_saved_filter(name, query_string):
    if _repo_backend() == "sqlite":
        return sqlite_execute(
            "INSERT INTO saved_filters (name, query_string) VALUES (?, ?)",
            (name, query_string),
        )
    with session_scope() as session:
        session.add(
            SavedFilter(
                name=name,
                query_string=query_string,
                created_at=datetime.now(),
            )
        )
        session.flush()
    return 1


def get_dashboard_order(default="kpi,trend,filters,actions,records,logs"):
    return get_ui_setting("dashboard_order", default)


def set_dashboard_order(value):
    return set_ui_setting("dashboard_order", value)


def get_ui_setting(setting_key, default=""):
    if _repo_backend() == "sqlite":
        row = sqlite_q1("SELECT setting_value FROM ui_settings WHERE setting_key=?", (setting_key,))
        if not row:
            return default
        return row.get("setting_value") or default
    with session_scope() as session:
        row = session.get(UiSetting, setting_key)
        if row is None:
            return default
        return row.setting_value or default


def set_ui_setting(setting_key, setting_value):
    if _repo_backend() == "sqlite":
        return sqlite_execute(
            "INSERT INTO ui_settings (setting_key, setting_value, updated_at) "
            "VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(setting_key) DO UPDATE SET "
            "setting_value=excluded.setting_value, updated_at=CURRENT_TIMESTAMP",
            (setting_key, setting_value),
        )
    now = datetime.now()
    with session_scope() as session:
        statement = mysql_insert(UiSetting).values(
            setting_key=setting_key,
            setting_value=setting_value,
            updated_at=now,
        )
        statement = statement.on_duplicate_key_update(
            setting_value=statement.inserted.setting_value,
            updated_at=now,
        )
        result = session.execute(statement)
        return result.rowcount or 1


def get_tradingagents_runtime_config():
    raw = get_ui_setting(TRADINGAGENTS_RUNTIME_CONFIG_KEY, "")
    if not raw:
        return dict(DEFAULT_TRADINGAGENTS_RUNTIME_CONFIG)
    try:
        data = json.loads(raw)
    except Exception:
        return dict(DEFAULT_TRADINGAGENTS_RUNTIME_CONFIG)
    config = dict(DEFAULT_TRADINGAGENTS_RUNTIME_CONFIG)
    if isinstance(data, dict):
        config.update(data)
    return config


def save_tradingagents_runtime_config(config):
    payload = dict(DEFAULT_TRADINGAGENTS_RUNTIME_CONFIG)
    payload.update(config or {})
    return set_ui_setting(
        TRADINGAGENTS_RUNTIME_CONFIG_KEY,
        json.dumps(payload, ensure_ascii=False),
    )
