"""UI settings and saved filter persistence."""

from __future__ import annotations

import base64
import hashlib
import hmac
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
EXTERNAL_PUSH_CHANNELS_KIND = "external_push_channels"
EXTERNAL_PUSH_ENCRYPTION_ALG = "kms-envelope-v1"
EXTERNAL_PUSH_LEGACY_ENCRYPTION_ALG = "sha256-stream-v1"
EXTERNAL_PUSH_ENCRYPTED_MARKER = "__external_push_encrypted__"
EXTERNAL_PUSH_SENSITIVE_CONFIG_KEYS = {
    "api_key",
    "authorization",
    "bearer_token",
    "password",
    "secret",
    "smtp_password",
    "token",
    "webhook_url",
    "x-api-key",
}


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


def list_external_push_channels(
    tenant_id: int,
    user_id: int | None = None,
    *,
    include_secrets: bool = False,
) -> list[dict]:
    items = [
        _external_push_channel_for_read(item, include_secrets=include_secrets)
        for item in _load_user_setting_list(tenant_id, user_id, EXTERNAL_PUSH_CHANNELS_KIND)
    ]
    if include_secrets:
        return items
    from backend.application.external_push import public_external_push_channel

    return [public_external_push_channel(item) for item in items]


def upsert_external_push_channel(tenant_id: int, user_id: int | None, payload: dict) -> dict:
    items = _load_user_setting_list(tenant_id, user_id, EXTERNAL_PUSH_CHANNELS_KIND)
    now = _now_iso()
    item_id = str(payload.get("id") or "").strip() or uuid4().hex
    existing = next((item for item in items if str(item.get("id")) == item_id), None)
    base = _external_push_channel_for_read(existing or {}, include_secrets=True)
    enabled = payload.get("enabled", base.get("enabled"))
    config = _dict_or_empty(base.get("config"))
    config.update(_external_push_payload_config(payload.get("config"), config))
    normalized = {
        "id": item_id,
        "name": str(payload.get("name") or payload.get("title") or base.get("name") or "Untitled push channel").strip(),
        "type": _normalize_external_push_type(payload.get("type") or base.get("type")),
        "enabled": True if enabled is None else _bool_value(enabled),
        "config": config,
        "metadata": _dict_or_empty(payload.get("metadata", base.get("metadata"))),
        "created_at": existing.get("created_at") if existing else now,
        "updated_at": now,
    }
    stored = _external_push_channel_for_storage(normalized)
    items = [item for item in items if str(item.get("id")) != item_id]
    items.insert(0, stored)
    _save_user_setting_list(tenant_id, user_id, EXTERNAL_PUSH_CHANNELS_KIND, items)
    from backend.application.external_push import public_external_push_channel

    return public_external_push_channel(_external_push_channel_for_read(stored, include_secrets=True))


def delete_external_push_channel(tenant_id: int, user_id: int | None, channel_id: str) -> int:
    return _delete_user_setting_item(tenant_id, user_id, EXTERNAL_PUSH_CHANNELS_KIND, channel_id)


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


def _normalize_external_push_type(value) -> str:
    channel_type = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "ding-talk": "dingtalk",
        "dingding": "dingtalk",
        "enterprise-wechat": "wecom",
        "wechat-work": "wecom",
        "weixin-work": "wecom",
        "smtp": "email",
        "smtp-email": "email",
        "generic-webhook": "webhook",
    }
    return aliases.get(channel_type, channel_type)


def _bool_value(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _external_push_payload_config(payload_config, base_config: dict | None = None) -> dict:
    incoming = _dict_or_empty(payload_config)
    base = dict(base_config or {})
    for key, value in incoming.items():
        if _is_external_push_secret_key(key) and value == "***configured***":
            continue
        base[key] = value
    return base


def _external_push_channel_for_storage(item: dict) -> dict:
    stored = dict(item or {})
    config = _dict_or_empty(stored.get("config"))
    encrypted_values: dict[str, dict] = {}
    public_config: dict[str, Any] = {}
    encryption_status = "unconfigured"
    for key, value in config.items():
        if _is_external_push_secret_key(key):
            encrypted = _encrypt_external_push_secret(value)
            if encrypted is None:
                public_config[key] = value
            else:
                encrypted_values[key] = encrypted
                encryption_status = "encrypted"
        else:
            public_config[key] = value
    if encrypted_values:
        public_config[EXTERNAL_PUSH_ENCRYPTED_MARKER] = encrypted_values
    stored["config"] = public_config
    metadata = _dict_or_empty(stored.get("metadata"))
    metadata["encryption_status"] = encryption_status
    metadata["encryption_alg"] = EXTERNAL_PUSH_ENCRYPTION_ALG if encryption_status == "encrypted" else ""
    metadata["key_provider"] = _external_push_key_provider() if encryption_status == "encrypted" else ""
    metadata["key_id"] = _external_push_key_id() if encryption_status == "encrypted" else ""
    stored["metadata"] = metadata
    return stored


def _external_push_channel_for_read(item: dict, *, include_secrets: bool) -> dict:
    readable = dict(item or {})
    config = _dict_or_empty(readable.get("config"))
    encrypted_values = _dict_or_empty(config.pop(EXTERNAL_PUSH_ENCRYPTED_MARKER, {}))
    metadata = _dict_or_empty(readable.get("metadata"))
    for key, encrypted in encrypted_values.items():
        decrypted = _decrypt_external_push_secret(encrypted)
        if include_secrets:
            config[key] = decrypted if decrypted is not None else ""
        else:
            config[key] = "***configured***" if decrypted is not None or encrypted else ""
    if include_secrets:
        for key in list(config.keys()):
            value = config[key]
            if _is_external_push_secret_key(key) and isinstance(value, dict):
                config[key] = _decrypt_external_push_secret(value) or ""
    metadata.setdefault("encryption_status", "encrypted" if encrypted_values else "unconfigured")
    readable["config"] = config
    readable["metadata"] = metadata
    return readable


def _is_external_push_secret_key(key: Any) -> bool:
    normalized = str(key or "").strip().lower()
    return normalized in EXTERNAL_PUSH_SENSITIVE_CONFIG_KEYS or any(part in normalized for part in ("secret", "token", "password", "webhook_url"))


def _external_push_key_provider() -> str:
    return str(os.getenv("EXTERNAL_PUSH_KMS_PROVIDER") or os.getenv("EXTERNAL_PUSH_SECRET_PROVIDER") or "local-env").strip() or "local-env"


def _external_push_key_id() -> str:
    return str(os.getenv("EXTERNAL_PUSH_KMS_KEY_ID") or os.getenv("EXTERNAL_PUSH_KEY_ID") or "external-push-local").strip() or "external-push-local"


def _external_push_secret_key() -> bytes | None:
    raw = os.getenv("EXTERNAL_PUSH_SECRET_KEY") or os.getenv("SETTINGS_SECRET_KEY")
    if not raw:
        return None
    return hashlib.sha256(str(raw).encode("utf-8")).digest()


def _encrypt_external_push_secret(value: Any) -> dict | None:
    kek = _external_push_secret_key()
    if kek is None:
        return None
    plaintext = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    data_key = os.urandom(32)
    data_nonce = os.urandom(16)
    wrap_nonce = os.urandom(16)
    stream = _secret_stream(data_key, data_nonce, len(plaintext))
    ciphertext = bytes(byte ^ stream[index] for index, byte in enumerate(plaintext))
    wrap_stream = _secret_stream(kek, wrap_nonce, len(data_key))
    wrapped_data_key = bytes(byte ^ wrap_stream[index] for index, byte in enumerate(data_key))
    mac = hmac.new(data_key, data_nonce + ciphertext, hashlib.sha256).digest()
    wrapped_mac = hmac.new(kek, wrap_nonce + wrapped_data_key, hashlib.sha256).digest()
    return {
        "alg": EXTERNAL_PUSH_ENCRYPTION_ALG,
        "provider": _external_push_key_provider(),
        "key_id": _external_push_key_id(),
        "wrap_nonce": base64.urlsafe_b64encode(wrap_nonce).decode("ascii"),
        "wrapped_data_key": base64.urlsafe_b64encode(wrapped_data_key).decode("ascii"),
        "wrapped_mac": base64.urlsafe_b64encode(wrapped_mac).decode("ascii"),
        "nonce": base64.urlsafe_b64encode(data_nonce).decode("ascii"),
        "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
        "mac": base64.urlsafe_b64encode(mac).decode("ascii"),
    }


def _decrypt_external_push_secret(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    key = _external_push_secret_key()
    if key is None:
        return None
    if value.get("alg") == EXTERNAL_PUSH_LEGACY_ENCRYPTION_ALG:
        return _decrypt_legacy_external_push_secret(value, key)
    if value.get("alg") != EXTERNAL_PUSH_ENCRYPTION_ALG:
        return None
    try:
        wrap_nonce = base64.urlsafe_b64decode(str(value.get("wrap_nonce") or ""))
        wrapped_data_key = base64.urlsafe_b64decode(str(value.get("wrapped_data_key") or ""))
        expected_wrapped_mac = base64.urlsafe_b64decode(str(value.get("wrapped_mac") or ""))
        data_nonce = base64.urlsafe_b64decode(str(value.get("nonce") or ""))
        ciphertext = base64.urlsafe_b64decode(str(value.get("ciphertext") or ""))
        expected_mac = base64.urlsafe_b64decode(str(value.get("mac") or ""))
    except Exception:
        return None
    actual_wrapped_mac = hmac.new(key, wrap_nonce + wrapped_data_key, hashlib.sha256).digest()
    if not hmac.compare_digest(actual_wrapped_mac, expected_wrapped_mac):
        return None
    wrap_stream = _secret_stream(key, wrap_nonce, len(wrapped_data_key))
    data_key = bytes(byte ^ wrap_stream[index] for index, byte in enumerate(wrapped_data_key))
    actual_mac = hmac.new(data_key, data_nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(actual_mac, expected_mac):
        return None
    stream = _secret_stream(data_key, data_nonce, len(ciphertext))
    plaintext = bytes(byte ^ stream[index] for index, byte in enumerate(ciphertext))
    try:
        return json.loads(plaintext.decode("utf-8"))
    except Exception:
        return None


def _decrypt_legacy_external_push_secret(value: dict, key: bytes) -> Any:
    try:
        nonce = base64.urlsafe_b64decode(str(value.get("nonce") or ""))
        ciphertext = base64.urlsafe_b64decode(str(value.get("ciphertext") or ""))
        expected_mac = base64.urlsafe_b64decode(str(value.get("mac") or ""))
    except Exception:
        return None
    actual_mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(actual_mac, expected_mac):
        return None
    stream = _secret_stream(key, nonce, len(ciphertext))
    plaintext = bytes(byte ^ stream[index] for index, byte in enumerate(ciphertext))
    try:
        return json.loads(plaintext.decode("utf-8"))
    except Exception:
        return None


def _secret_stream(key: bytes, nonce: bytes, length: int) -> bytes:
    chunks = []
    counter = 0
    while sum(len(chunk) for chunk in chunks) < length:
        chunks.append(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    return b"".join(chunks)[:length]
