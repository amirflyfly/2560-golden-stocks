"""Strategy repository for multi-strategy support."""

from __future__ import annotations

import os
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


def _public_strategy(row: Strategy | dict) -> dict:
    if isinstance(row, dict):
        return dict(row)
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
        "enabled": 1 if row.enabled else 0,
    }


def list_strategies(active_only=True):
    """List all strategies, optionally filtering by active status."""
    if _repo_backend() == "sqlite":
        sql = "SELECT * FROM strategies"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY sort_order ASC, id ASC"
        return sqlite_q(sql)
    with session_scope() as session:
        statement = select(Strategy).where(Strategy.tenant_id == DEFAULT_TENANT_ID)
        if active_only:
            statement = statement.where(Strategy.is_active.is_(True), Strategy.deleted_at.is_(None))
        rows = session.execute(statement.order_by(Strategy.sort_order.asc(), Strategy.id.asc())).scalars().all()
        return [_public_strategy(row) for row in rows]


def get_strategy_by_id(sid):
    """Get a single strategy by ID."""
    if _repo_backend() == "sqlite":
        return sqlite_q1("SELECT * FROM strategies WHERE id=?", (sid,))
    with session_scope() as session:
        row = session.get(Strategy, int(sid))
        if row is None or row.tenant_id != DEFAULT_TENANT_ID:
            return None
        return _public_strategy(row)


def get_strategy_by_code(code):
    """Get a single strategy by code."""
    if _repo_backend() == "sqlite":
        return sqlite_q1("SELECT * FROM strategies WHERE code=?", (code,))
    with session_scope() as session:
        row = session.execute(
            select(Strategy).where(Strategy.tenant_id == DEFAULT_TENANT_ID, Strategy.code == code)
        ).scalar_one_or_none()
        return _public_strategy(row) if row is not None else None


def create_strategy(code, name, category="", description="", sort_order=0):
    """Create a new strategy."""
    if _repo_backend() == "sqlite":
        return sqlite_execute(
            """INSERT INTO strategies (code, name, category, description, sort_order)
               VALUES (?, ?, ?, ?, ?)""",
            (code, name, category, description, sort_order),
        )
    with session_scope() as session:
        session.add(
            Strategy(
                tenant_id=DEFAULT_TENANT_ID,
                code=code,
                name=name,
                category=category or "",
                description=description or "",
                config_json=None,
                enabled=True,
                is_active=True,
                sort_order=int(sort_order or 0),
                created_by=None,
            )
        )
        session.flush()
    return 1


def update_strategy(sid, code=None, name=None, category=None, description=None, is_active=None, sort_order=None):
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
