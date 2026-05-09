"""Strategy repository for multi-strategy support."""

from __future__ import annotations

import os
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select

from backend.core.config import get_settings
from backend.db.models import Pick, Strategy
from backend.db.session import session_scope
from backend.repositories.db import execute as sqlite_execute
from backend.repositories.db import q as sqlite_q
from backend.repositories.db import q1 as sqlite_q1


DEFAULT_TENANT_ID = int(os.getenv("STRATEGY_DEFAULT_TENANT_ID", "1"))


def _repo_backend() -> str:
    forced = (os.getenv("STRATEGY_REPOSITORY_BACKEND") or "auto").strip().lower()
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


def _json_load(value: Any, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _json_dump(value: Any) -> str:
    if value in (None, ""):
        return "{}"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _public_strategy(row: Strategy | dict) -> dict:
    if isinstance(row, dict):
        data = dict(row)
        data["enabled"] = bool(data.get("enabled", data.get("is_active", 1)))
        data["is_active"] = bool(data.get("is_active", data.get("enabled", 1)))
        data["config"] = _json_load(data.get("config_json"), {})
        data["config_json"] = _json_dump(data.get("config", data.get("config_json", {})))
        data["source_type"] = data.get("source_type") or "builtin"
        data["lifecycle_status"] = data.get("lifecycle_status") or ("deployed" if data["enabled"] else "disabled")
        data["version"] = int(data.get("version") or 1)
        data["code_body"] = data.get("code_body") or ""
        data["last_test_status"] = data.get("last_test_status") or ""
        data["last_test_message"] = data.get("last_test_message") or ""
        return data
    is_active = bool(row.is_active) and row.deleted_at is None
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "category": row.category or "",
        "description": row.description or "",
        "is_active": 1 if is_active else 0,
        "sort_order": row.sort_order or 0,
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
        "tenant_id": row.tenant_id,
        "enabled": bool(row.enabled),
        "source_type": row.source_type or "builtin",
        "lifecycle_status": row.lifecycle_status or ("deployed" if row.enabled else "disabled"),
        "version": row.version or 1,
        "config": row.config_json or {},
        "config_json": _json_dump(row.config_json or {}),
        "code_body": row.code_body or "",
        "deployed_at": _dt(row.deployed_at),
        "last_test_status": row.last_test_status or "",
        "last_test_message": row.last_test_message or "",
        "last_test_at": _dt(row.last_test_at),
    }


def list_strategies(active_only=True):
    """List all strategies, optionally filtering by active status."""
    if _repo_backend() == "sqlite":
        sql = "SELECT * FROM strategies"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY sort_order ASC, id ASC"
        return [_public_strategy(row) for row in sqlite_q(sql)]
    with session_scope() as session:
        statement = select(Strategy).where(Strategy.tenant_id == DEFAULT_TENANT_ID)
        if active_only:
            statement = statement.where(Strategy.is_active.is_(True), Strategy.deleted_at.is_(None))
        rows = session.execute(statement.order_by(Strategy.sort_order.asc(), Strategy.id.asc())).scalars().all()
        return [_public_strategy(row) for row in rows]


def get_strategy_by_id(sid):
    """Get a single strategy by ID."""
    if _repo_backend() == "sqlite":
        row = sqlite_q1("SELECT * FROM strategies WHERE id=?", (sid,))
        return _public_strategy(row) if row else None
    with session_scope() as session:
        row = session.get(Strategy, int(sid))
        if row is None or row.tenant_id != DEFAULT_TENANT_ID:
            return None
        return _public_strategy(row)


def get_strategy_by_code(code):
    """Get a single strategy by code."""
    if _repo_backend() == "sqlite":
        row = sqlite_q1("SELECT * FROM strategies WHERE code=?", (code,))
        return _public_strategy(row) if row else None
    with session_scope() as session:
        row = session.execute(
            select(Strategy).where(Strategy.tenant_id == DEFAULT_TENANT_ID, Strategy.code == code)
        ).scalar_one_or_none()
        return _public_strategy(row) if row is not None else None


def create_strategy(
    code,
    name,
    category="",
    description="",
    sort_order=0,
    *,
    code_body="",
    config_json=None,
    source_type="custom",
    lifecycle_status="draft",
    enabled=False,
    created_by=None,
):
    """Create a new strategy."""
    if _repo_backend() == "sqlite":
        return sqlite_execute(
            """INSERT INTO strategies
               (code, name, category, description, sort_order, code_body, config_json,
                source_type, lifecycle_status, enabled, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                code,
                name,
                category,
                description,
                sort_order,
                code_body or "",
                _json_dump(config_json),
                source_type or "custom",
                lifecycle_status or "draft",
                1 if enabled else 0,
            ),
        )
    with session_scope() as session:
        session.add(
            Strategy(
                tenant_id=DEFAULT_TENANT_ID,
                code=code,
                name=name,
                category=category or "",
                description=description or "",
                config_json=_json_load(config_json, {}) or {},
                code_body=code_body or "",
                source_type=source_type or "custom",
                lifecycle_status=lifecycle_status or "draft",
                version=1,
                enabled=bool(enabled),
                is_active=True,
                sort_order=int(sort_order or 0),
                created_by=created_by,
            )
        )
        session.flush()
    return 1


def update_strategy(
    sid,
    code=None,
    name=None,
    category=None,
    description=None,
    is_active=None,
    sort_order=None,
    enabled=None,
    code_body=None,
    config_json=None,
    source_type=None,
    lifecycle_status=None,
    version=None,
    deployed_at=None,
    last_test_status=None,
    last_test_message=None,
    last_test_at=None,
):
    """Update a strategy. Only updates provided fields."""
    if _repo_backend() == "sqlite":
        strategy = get_strategy_by_id(sid)
        if not strategy:
            return 0

        fields = []
        args = []

        if code is not None:
            fields.append("code=?")
            args.append(code)
        if name is not None:
            fields.append("name=?")
            args.append(name)
        if category is not None:
            fields.append("category=?")
            args.append(category)
        if description is not None:
            fields.append("description=?")
            args.append(description)
        if is_active is not None:
            fields.append("is_active=?")
            args.append(1 if is_active else 0)
        if sort_order is not None:
            fields.append("sort_order=?")
            args.append(sort_order)
        if enabled is not None:
            fields.append("enabled=?")
            args.append(1 if enabled else 0)
        if code_body is not None:
            fields.append("code_body=?")
            args.append(code_body)
        if config_json is not None:
            fields.append("config_json=?")
            args.append(_json_dump(config_json))
        if source_type is not None:
            fields.append("source_type=?")
            args.append(source_type)
        if lifecycle_status is not None:
            fields.append("lifecycle_status=?")
            args.append(lifecycle_status)
        if version is not None:
            fields.append("version=?")
            args.append(int(version))
        if deployed_at is not None:
            fields.append("deployed_at=?")
            args.append(_dt(deployed_at))
        if last_test_status is not None:
            fields.append("last_test_status=?")
            args.append(last_test_status)
        if last_test_message is not None:
            fields.append("last_test_message=?")
            args.append(last_test_message)
        if last_test_at is not None:
            fields.append("last_test_at=?")
            args.append(_dt(last_test_at))

        if not fields:
            return 0

        args.append(sid)
        return sqlite_execute(
            f"UPDATE strategies SET {', '.join(fields)}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            args,
        )

    with session_scope() as session:
        row = session.get(Strategy, int(sid))
        if row is None or row.tenant_id != DEFAULT_TENANT_ID:
            return 0
        if code is not None:
            row.code = code
        if name is not None:
            row.name = name
        if category is not None:
            row.category = category
        if description is not None:
            row.description = description
        if is_active is not None:
            row.is_active = bool(is_active)
            row.enabled = bool(is_active)
            row.deleted_at = None if is_active else datetime.now()
        if sort_order is not None:
            row.sort_order = int(sort_order)
        if enabled is not None:
            row.enabled = bool(enabled)
        if code_body is not None:
            row.code_body = code_body
        if config_json is not None:
            row.config_json = _json_load(config_json, {}) or {}
        if source_type is not None:
            row.source_type = source_type
        if lifecycle_status is not None:
            row.lifecycle_status = lifecycle_status
        if version is not None:
            row.version = int(version)
        if deployed_at is not None:
            row.deployed_at = deployed_at if isinstance(deployed_at, datetime) else datetime.now()
        if last_test_status is not None:
            row.last_test_status = last_test_status
        if last_test_message is not None:
            row.last_test_message = last_test_message
        if last_test_at is not None:
            row.last_test_at = last_test_at if isinstance(last_test_at, datetime) else datetime.now()
        row.updated_at = datetime.now()
        session.flush()
    return 1


def delete_strategy(sid):
    """Delete a strategy (soft delete by deactivating)."""
    return update_strategy(sid, is_active=False)


def toggle_strategy_active(sid):
    """Toggle strategy active status."""
    strategy = get_strategy_by_id(sid)
    if not strategy:
        return 0
    new_status = 0 if strategy.get("is_active") else 1
    return update_strategy(sid, is_active=new_status)


def get_strategy_names_for_dropdown():
    """Get strategy names for dropdown, returns list of {code, name}."""
    strategies = list_strategies(active_only=True)
    return [{"code": s["code"], "name": s["name"]} for s in strategies]


def get_strategy_daily_summary(target_date):
    """Get daily summary for all strategies on a specific date."""
    if _repo_backend() == "sqlite":
        strategies = list_strategies(active_only=True)
        picks_data = sqlite_q(
            """SELECT COALESCE(NULLIF(p.strategy_name,''),'2560') as strategy_name,
                      COUNT(*) as total,
                      SUM(CASE WHEN COALESCE(NULLIF(p.review_status,''),'鏈鐩?)='鍊煎緱澶嶈' THEN 1 ELSE 0 END) as worthy_total,
                      SUM(CASE WHEN COALESCE(NULLIF(p.deal_status,''),'鏈垚浜?)='宸叉垚浜? THEN 1 ELSE 0 END) as deal_total
               FROM picks p
               WHERE COALESCE(p.archived,0)=0 AND p.pick_date=?
               GROUP BY strategy_name""",
            (target_date,),
        )
    else:
        strategies = list_strategies(active_only=True)
        with session_scope() as session:
            picks = session.execute(
                select(Pick).where(
                    Pick.tenant_id == DEFAULT_TENANT_ID,
                    Pick.trade_date == target_date,
                    Pick.deleted_at.is_(None),
                )
            ).scalars().all()
            strategy_ids = {pick.strategy_id for pick in picks if pick.strategy_id}
            strategy_code_by_id = {
                item.id: item.code
                for item in session.execute(select(Strategy).where(Strategy.id.in_(strategy_ids))).scalars().all()
            } if strategy_ids else {}
        summary: dict[str, dict[str, Any]] = {}
        for pick in picks:
            strategy_name = strategy_code_by_id.get(pick.strategy_id or 0, "2560")
            legacy = pick.legacy_payload_json or {}
            if isinstance(legacy, dict):
                strategy_name = legacy.get("strategy_name") or strategy_name
            item = summary.setdefault(strategy_name, {"strategy_name": strategy_name, "total": 0, "worthy_total": 0, "deal_total": 0})
            item["total"] += 1
            review_status = pick.status or (legacy.get("review_status") if isinstance(legacy, dict) else "")
            if review_status == "鍊煎緱澶嶈":
                item["worthy_total"] += 1
            if pick.deal_status == "宸叉垚浜?":
                item["deal_total"] += 1
        picks_data = list(summary.values())

    picks_lookup = {p["strategy_name"]: p for p in picks_data}
    result = []
    for strategy in strategies:
        code = strategy["code"]
        pick_info = picks_lookup.get(code, {"total": 0, "worthy_total": 0, "deal_total": 0})
        result.append(
            {
                "strategy_code": code,
                "strategy_name": strategy["name"],
                "category": strategy["category"],
                "total": pick_info["total"],
                "worthy_total": pick_info["worthy_total"],
                "deal_total": pick_info["deal_total"],
                "has_picks": pick_info["total"] > 0,
            }
        )

    return result
