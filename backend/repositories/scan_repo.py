"""Persistent scan task/result repository."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from backend.core.config import get_settings
from backend.db.models import ScanResult, ScanTask, Strategy
from backend.db.session import session_scope
from backend.repositories import strategy_repo
from backend.repositories.db import execute as sqlite_execute
from backend.repositories.db import execute_many as sqlite_execute_many
from backend.repositories.db import q as sqlite_q
from backend.repositories.db import q1 as sqlite_q1

DEFAULT_TENANT_ID = int(os.getenv("SCAN_DEFAULT_TENANT_ID", "1"))


def _repo_backend() -> str:
    forced = (os.getenv("SCAN_REPOSITORY_BACKEND") or os.getenv("STRATEGY_REPOSITORY_BACKEND") or "auto").strip().lower()
    if forced in {"sqlite", "mysql"}:
        return forced
    settings = get_settings()
    environment = (settings.environment or "").strip().lower()
    if environment in {"prod", "production"}:
        return "mysql"
    return "sqlite"


def _json_dump(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def _json_load(value: Any, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _dt(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return value


def _date(value: Any) -> date:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return date.today()


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _strategy_code_candidates(code: str) -> list[str]:
    raw = str(code or "").strip()
    lowered = raw.lower()
    candidates = [raw]
    aliases = {
        "FIRST_LIMIT_UP": "first_limit_up",
        "first_board": "first_limit_up",
        "limit_up_return": "LIMIT_UP_RETURN",
        "limitup_return": "LIMIT_UP_RETURN",
    }
    if raw in aliases:
        candidates.append(aliases[raw])
    if lowered in aliases:
        candidates.append(aliases[lowered])
    if raw == "LIMIT_UP_RETURN":
        candidates.append("limit_up_return")
    return [item for index, item in enumerate(candidates) if item and item not in candidates[:index]]


def _strategy_for_code(code: str) -> dict | None:
    for candidate in _strategy_code_candidates(code):
        strategy = strategy_repo.get_strategy_by_code(candidate)
        if strategy:
            return strategy
    return None


def _task_item(row: ScanTask | dict) -> dict:
    if isinstance(row, dict):
        return {
            "id": row.get("id"),
            "tenant_id": int(row.get("tenant_id") or 0),
            "strategy_id": row.get("strategy_id"),
            "task_no": row.get("task_no") or "",
            "status": row.get("status") or "pending",
            "params": _json_load(row.get("params_json"), {}),
            "started_at": _dt(row.get("started_at")),
            "finished_at": _dt(row.get("finished_at")),
            "error_message": row.get("error_message") or "",
            "created_by": row.get("created_by"),
            "created_at": _dt(row.get("created_at")),
        }
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "strategy_id": row.strategy_id,
        "task_no": row.task_no,
        "status": row.status,
        "params": row.params_json or {},
        "started_at": _dt(row.started_at),
        "finished_at": _dt(row.finished_at),
        "error_message": row.error_message or "",
        "created_by": row.created_by,
        "created_at": _dt(row.created_at),
    }


def _result_item(row: ScanResult | dict) -> dict:
    if isinstance(row, dict):
        return {
            "id": row.get("id"),
            "scan_task_id": row.get("scan_task_id"),
            "strategy_id": row.get("strategy_id"),
            "tenant_id": int(row.get("tenant_id") or 0),
            "symbol": row.get("symbol") or "",
            "stock_name": row.get("stock_name") or "",
            "trade_date": str(row.get("trade_date") or ""),
            "score": float(row.get("score")) if row.get("score") is not None else None,
            "signals": _json_load(row.get("signals_json"), {}),
            "reason": row.get("reason") or "",
            "created_at": _dt(row.get("created_at")),
        }
    return {
        "id": row.id,
        "scan_task_id": row.scan_task_id,
        "strategy_id": row.strategy_id,
        "tenant_id": row.tenant_id,
        "symbol": row.symbol,
        "stock_name": row.stock_name or "",
        "trade_date": row.trade_date.isoformat() if row.trade_date else "",
        "score": float(row.score) if row.score is not None else None,
        "signals": row.signals_json or {},
        "reason": row.reason or "",
        "created_at": _dt(row.created_at),
    }


def persist_scan_result(
    tenant_id: int,
    *,
    task_no: str,
    strategy_code: str,
    params: dict,
    status: str,
    result: dict,
    error_message: str = "",
) -> dict | None:
    task_key = str(task_no or "").strip()
    if not task_key:
        return None
    strategy = _strategy_for_code(strategy_code)
    if not strategy:
        return None
    strategy_id = int(strategy["id"])
    now = datetime.now()
    market_data = result.get("market_data") or {}
    items = list(market_data.get("sample_symbols") or [])
    if _repo_backend() == "sqlite":
        sqlite_execute(
            """INSERT INTO scan_tasks
            (tenant_id, strategy_id, task_no, status, params_json, started_at, finished_at, error_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(task_no) DO UPDATE SET
                status=excluded.status,
                params_json=excluded.params_json,
                finished_at=excluded.finished_at,
                error_message=excluded.error_message""",
            (int(tenant_id or 0), strategy_id, task_key, status, _json_dump(params), now.isoformat(timespec="seconds"), now.isoformat(timespec="seconds"), error_message or ""),
        )
        task = sqlite_q1("SELECT * FROM scan_tasks WHERE tenant_id=? AND task_no=?", (int(tenant_id or 0), task_key))
        if not task:
            return None
        sqlite_execute("DELETE FROM scan_results WHERE tenant_id=? AND scan_task_id=?", (int(tenant_id or 0), int(task["id"])))
        sqlite_execute_many(
            """INSERT INTO scan_results
            (tenant_id, scan_task_id, strategy_id, symbol, stock_name, trade_date, score, signals_json, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            [_result_row(int(tenant_id or 0), int(task["id"]), strategy_id, item) for item in items],
        )
        return get_scan_bundle(tenant_id, task_key)

    with session_scope() as session:
        stmt = mysql_insert(ScanTask).values(
            tenant_id=int(tenant_id or 0),
            strategy_id=strategy_id,
            task_no=task_key,
            status=status,
            params_json=params or {},
            started_at=now,
            finished_at=now,
            error_message=error_message or "",
            created_at=now,
        )
        session.execute(
            stmt.on_duplicate_key_update(
                status=stmt.inserted.status,
                params_json=stmt.inserted.params_json,
                finished_at=stmt.inserted.finished_at,
                error_message=stmt.inserted.error_message,
            )
        )
        task = session.execute(
            select(ScanTask).where(ScanTask.tenant_id == int(tenant_id or 0), ScanTask.task_no == task_key)
        ).scalar_one()
        session.execute(delete(ScanResult).where(ScanResult.tenant_id == int(tenant_id or 0), ScanResult.scan_task_id == task.id))
        for item in items:
            session.add(
                ScanResult(
                    tenant_id=int(tenant_id or 0),
                    scan_task_id=task.id,
                    strategy_id=strategy_id,
                    symbol=str(item.get("symbol") or item.get("code") or "").strip(),
                    stock_name=item.get("stock_name") or item.get("name") or "",
                    trade_date=_date(item.get("trade_date") or item.get("date")),
                    score=_decimal(item.get("total_score") if item.get("total_score") is not None else item.get("score")),
                    signals_json=item,
                    reason=str(item.get("reason") or item.get("note") or item.get("signal") or ""),
                    created_at=now,
                )
            )
        session.flush()
    return get_scan_bundle(tenant_id, task_key)


def _result_row(tenant_id: int, scan_task_id: int, strategy_id: int, item: dict) -> tuple:
    return (
        tenant_id,
        scan_task_id,
        strategy_id,
        str(item.get("symbol") or item.get("code") or "").strip(),
        item.get("stock_name") or item.get("name") or "",
        _date(item.get("trade_date") or item.get("date")).isoformat(),
        float(_decimal(item.get("total_score") if item.get("total_score") is not None else item.get("score")) or 0),
        _json_dump(item),
        str(item.get("reason") or item.get("note") or item.get("signal") or ""),
    )


def get_scan_bundle(tenant_id: int, task_no: str) -> dict | None:
    task_key = str(task_no or "").strip()
    if _repo_backend() == "sqlite":
        task = sqlite_q1("SELECT * FROM scan_tasks WHERE tenant_id=? AND task_no=?", (int(tenant_id or 0), task_key))
        if not task:
            return None
        rows = sqlite_q(
            "SELECT * FROM scan_results WHERE tenant_id=? AND scan_task_id=? ORDER BY id ASC",
            (int(tenant_id or 0), int(task["id"])),
        )
        return {"task": _task_item(task), "items": [_result_item(row) for row in rows]}
    with session_scope() as session:
        task = session.execute(
            select(ScanTask).where(ScanTask.tenant_id == int(tenant_id or 0), ScanTask.task_no == task_key)
        ).scalar_one_or_none()
        if task is None:
            return None
        rows = session.execute(
            select(ScanResult).where(ScanResult.tenant_id == int(tenant_id or 0), ScanResult.scan_task_id == task.id).order_by(ScanResult.id.asc())
        ).scalars().all()
        return {"task": _task_item(task), "items": [_result_item(row) for row in rows]}


def list_persistent_scans(tenant_id: int, *, limit: int = 200) -> list[dict]:
    safe_limit = max(1, min(int(limit or 200), 500))
    if _repo_backend() == "sqlite":
        rows = sqlite_q("SELECT * FROM scan_tasks WHERE tenant_id=? ORDER BY id DESC LIMIT ?", (int(tenant_id or 0), safe_limit))
        return [_task_item(row) for row in rows]
    with session_scope() as session:
        rows = session.execute(
            select(ScanTask).where(ScanTask.tenant_id == int(tenant_id or 0)).order_by(ScanTask.id.desc()).limit(safe_limit)
        ).scalars().all()
        return [_task_item(row) for row in rows]
