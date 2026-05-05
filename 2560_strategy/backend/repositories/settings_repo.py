"""UI settings and saved filter persistence."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from backend.core.config import get_settings
from backend.db.models import SavedFilter, UiSetting
from backend.db.session import session_scope
from backend.repositories.db import execute as sqlite_execute
from backend.repositories.db import q as sqlite_q
from backend.repositories.db import q1 as sqlite_q1


TRADINGAGENTS_RUNTIME_CONFIG_KEY = "tradingagents_runtime_config"
SAVED_VIEWS_KIND = "saved_views"
ALERT_RULES_KIND = "alert_rules"
NOTIFICATIONS_KIND = "notifications"


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


def list_saved_views(tenant_id: int, user_id: int | None = None) -> list[dict]:
    return _load_user_setting_list(tenant_id, user_id, SAVED_VIEWS_KIND)


def upsert_saved_view(tenant_id: int, user_id: int | None, payload: dict) -> dict:
    items = _load_user_setting_list(tenant_id, user_id, SAVED_VIEWS_KIND)
    now = _now_iso()
    item_id = str(payload.get("id") or "").strip() or uuid4().hex
    existing = next((item for item in items if str(item.get("id")) == item_id), None)
    base = existing or {}
    normalized = {
        "id": item_id,
        "name": str(payload.get("name") or payload.get("title") or base.get("name") or "Untitled view").strip(),
        "page": str(payload.get("page") or payload.get("view_type") or base.get("page") or "picks").strip() or "picks",
        "filters": _dict_or_empty(payload.get("filters", base.get("filters"))),
        "query": str(payload.get("query") or payload.get("query_string") or base.get("query") or "").strip(),
        "sort": _dict_or_empty(payload.get("sort", base.get("sort"))),
        "columns": _list_or_empty(payload.get("columns", base.get("columns"))),
        "metadata": _dict_or_empty(payload.get("metadata", base.get("metadata"))),
        "created_at": existing.get("created_at") if existing else now,
        "updated_at": now,
    }
    items = [item for item in items if str(item.get("id")) != item_id]
    items.insert(0, normalized)
    _save_user_setting_list(tenant_id, user_id, SAVED_VIEWS_KIND, items)
    return normalized


def delete_saved_view(tenant_id: int, user_id: int | None, view_id: str) -> int:
    return _delete_user_setting_item(tenant_id, user_id, SAVED_VIEWS_KIND, view_id)


def list_alert_rules(tenant_id: int, user_id: int | None = None) -> list[dict]:
    return _load_user_setting_list(tenant_id, user_id, ALERT_RULES_KIND)


def upsert_alert_rule(tenant_id: int, user_id: int | None, payload: dict) -> dict:
    items = _load_user_setting_list(tenant_id, user_id, ALERT_RULES_KIND)
    now = _now_iso()
    item_id = str(payload.get("id") or "").strip() or uuid4().hex
    existing = next((item for item in items if str(item.get("id")) == item_id), None)
    base = existing or {}
    enabled = payload.get("enabled", base.get("enabled"))
    normalized = {
        "id": item_id,
        "name": str(payload.get("name") or payload.get("title") or base.get("name") or "Untitled alert").strip(),
        "scope": str(payload.get("scope") or base.get("scope") or "symbol").strip() or "symbol",
        "target": str(payload.get("target") or payload.get("symbol") or base.get("target") or "").strip(),
        "rule": _dict_or_empty(payload.get("rule", base.get("rule"))),
        "channels": _list_or_empty(payload.get("channels", base.get("channels"))),
        "enabled": True if enabled is None else _bool_value(enabled),
        "last_triggered_at": payload.get("last_triggered_at", base.get("last_triggered_at")),
        "last_evaluated_at": payload.get("last_evaluated_at", base.get("last_evaluated_at")),
        "metadata": _dict_or_empty(payload.get("metadata", base.get("metadata"))),
        "created_at": existing.get("created_at") if existing else now,
        "updated_at": now,
    }
    items = [item for item in items if str(item.get("id")) != item_id]
    items.insert(0, normalized)
    _save_user_setting_list(tenant_id, user_id, ALERT_RULES_KIND, items)
    return normalized


def delete_alert_rule(tenant_id: int, user_id: int | None, alert_id: str) -> int:
    return _delete_user_setting_item(tenant_id, user_id, ALERT_RULES_KIND, alert_id)


def list_all_alert_rules(tenant_id: int | None = None, user_id: int | None = None) -> list[dict]:
    rows = _list_user_setting_rows(ALERT_RULES_KIND)
    records = []
    for row in rows:
        parsed = _parse_user_setting_key(row.get("setting_key"), ALERT_RULES_KIND)
        if parsed is None:
            continue
        row_tenant_id, row_user_id = parsed
        if tenant_id is not None and int(tenant_id) != row_tenant_id:
            continue
        if user_id is not None and int(user_id or 0) != row_user_id:
            continue
        for item in _decode_setting_list(row.get("setting_value")):
            records.append({"tenant_id": row_tenant_id, "user_id": row_user_id, "item": item})
    return records


def update_alert_rule_trigger_state(
    tenant_id: int,
    user_id: int | None,
    alert_id: str,
    *,
    evaluated_at: str,
    triggered_at: str | None = None,
    match_count: int = 0,
) -> dict | None:
    items = _load_user_setting_list(tenant_id, user_id, ALERT_RULES_KIND)
    updated = None
    for item in items:
        if str(item.get("id")) != str(alert_id):
            continue
        metadata = _dict_or_empty(item.get("metadata"))
        metadata.update({"last_match_count": int(match_count or 0)})
        item["metadata"] = metadata
        item["last_evaluated_at"] = evaluated_at
        if triggered_at:
            item["last_triggered_at"] = triggered_at
        item["updated_at"] = evaluated_at
        updated = item
        break
    if updated is None:
        return None
    _save_user_setting_list(tenant_id, user_id, ALERT_RULES_KIND, items)
    return updated


def list_notifications(
    tenant_id: int,
    user_id: int | None = None,
    *,
    unread_only: bool = False,
    limit: int = 50,
) -> list[dict]:
    safe_limit = max(1, min(int(limit or 50), 200))
    items = _load_user_setting_list(tenant_id, user_id, NOTIFICATIONS_KIND)
    if unread_only:
        items = [item for item in items if not item.get("read_at")]
    return items[:safe_limit]


def count_unread_notifications(tenant_id: int, user_id: int | None = None) -> int:
    return len(list_notifications(tenant_id, user_id, unread_only=True, limit=200))


def upsert_notification(tenant_id: int, user_id: int | None, payload: dict) -> dict:
    items = _load_user_setting_list(tenant_id, user_id, NOTIFICATIONS_KIND)
    now = _now_iso()
    dedupe_key = str(payload.get("dedupe_key") or "").strip()
    item_id = str(payload.get("id") or "").strip() or uuid4().hex
    existing = next(
        (
            item
            for item in items
            if (dedupe_key and str(item.get("dedupe_key") or "") == dedupe_key)
            or str(item.get("id") or "") == item_id
        ),
        None,
    )
    base = existing or {}
    normalized = {
        "id": str(base.get("id") or item_id),
        "type": str(payload.get("type") or base.get("type") or "alert_triggered"),
        "channel": str(payload.get("channel") or base.get("channel") or "in_app"),
        "severity": str(payload.get("severity") or base.get("severity") or "warning"),
        "title": str(payload.get("title") or base.get("title") or "Alert triggered"),
        "body": str(payload.get("body") or base.get("body") or ""),
        "rule_id": str(payload.get("rule_id") or base.get("rule_id") or ""),
        "rule_name": str(payload.get("rule_name") or base.get("rule_name") or ""),
        "scope": str(payload.get("scope") or base.get("scope") or ""),
        "source": str(payload.get("source") or base.get("source") or ""),
        "entity": _dict_or_empty(payload.get("entity", base.get("entity"))),
        "match": _dict_or_empty(payload.get("match", base.get("match"))),
        "metadata": _dict_or_empty(payload.get("metadata", base.get("metadata"))),
        "dedupe_key": dedupe_key or str(base.get("dedupe_key") or ""),
        "read_at": payload.get("read_at", base.get("read_at")),
        "created_at": base.get("created_at") or now,
        "updated_at": now,
        "last_seen_at": now,
        "occurrence_count": int(base.get("occurrence_count") or 0) + 1,
    }
    items = [item for item in items if str(item.get("id") or "") != normalized["id"]]
    if normalized["dedupe_key"]:
        items = [item for item in items if str(item.get("dedupe_key") or "") != normalized["dedupe_key"]]
    items.insert(0, normalized)
    _save_user_setting_list(tenant_id, user_id, NOTIFICATIONS_KIND, items, max_items=500)
    return normalized


def mark_notification_read(
    tenant_id: int,
    user_id: int | None,
    notification_id: str,
    *,
    read: bool = True,
) -> dict | None:
    items = _load_user_setting_list(tenant_id, user_id, NOTIFICATIONS_KIND)
    now = _now_iso()
    updated = None
    for item in items:
        if str(item.get("id")) != str(notification_id):
            continue
        item["read_at"] = now if read else None
        item["updated_at"] = now
        updated = item
        break
    if updated is None:
        return None
    _save_user_setting_list(tenant_id, user_id, NOTIFICATIONS_KIND, items, max_items=500)
    return updated


def _load_user_setting_list(tenant_id: int, user_id: int | None, kind: str) -> list[dict]:
    raw = get_ui_setting(_user_setting_key(tenant_id, user_id, kind), "[]")
    return _decode_setting_list(raw)


def _decode_setting_list(raw: Any) -> list[dict]:
    try:
        decoded = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        decoded = []
    if not isinstance(decoded, list):
        return []
    return [item for item in decoded if isinstance(item, dict)]


def _save_user_setting_list(tenant_id: int, user_id: int | None, kind: str, items: list[dict], *, max_items: int = 200) -> int:
    safe_items = items[: max(1, int(max_items or 200))]
    return set_ui_setting(
        _user_setting_key(tenant_id, user_id, kind),
        json.dumps(safe_items, ensure_ascii=False),
    )


def _delete_user_setting_item(tenant_id: int, user_id: int | None, kind: str, item_id: str) -> int:
    items = _load_user_setting_list(tenant_id, user_id, kind)
    remaining = [item for item in items if str(item.get("id")) != str(item_id)]
    if len(remaining) == len(items):
        return 0
    _save_user_setting_list(tenant_id, user_id, kind, remaining)
    return 1


def _user_setting_key(tenant_id: int, user_id: int | None, kind: str) -> str:
    normalized_user = int(user_id or 0)
    return f"ui:{int(tenant_id)}:{normalized_user}:{kind}"


def _list_user_setting_rows(kind: str) -> list[dict]:
    pattern = f"ui:%:%:{kind}"
    if _repo_backend() == "sqlite":
        return sqlite_q(
            "SELECT setting_key, setting_value FROM ui_settings WHERE setting_key LIKE ?",
            (pattern,),
        )
    with session_scope() as session:
        rows = session.execute(
            select(UiSetting.setting_key, UiSetting.setting_value).where(UiSetting.setting_key.like(pattern))
        ).mappings().all()
    return [dict(row) for row in rows]


def _parse_user_setting_key(setting_key: Any, kind: str) -> tuple[int, int] | None:
    parts = str(setting_key or "").split(":")
    if len(parts) != 4 or parts[0] != "ui" or parts[3] != kind:
        return None
    try:
        tenant_id = int(parts[1])
        user_id = int(parts[2])
    except ValueError:
        return None
    if tenant_id <= 0 or user_id < 0:
        return None
    return tenant_id, user_id


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _dict_or_empty(value) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _list_or_empty(value) -> list:
    return list(value) if isinstance(value, list) else []


def _bool_value(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}
