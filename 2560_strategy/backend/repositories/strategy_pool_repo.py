"""Strategy pool repository."""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from backend.core.config import get_settings
from backend.db.models import BacktestResult, StrategyPool
from backend.db.session import session_scope
from backend.repositories.db import execute as sqlite_execute
from backend.repositories.db import q as sqlite_q


def _repo_backend() -> str:
    forced = (os.getenv("STRATEGY_POOL_REPOSITORY_BACKEND") or "auto").strip().lower()
    if forced in {"sqlite", "mysql"}:
        return forced
    settings = get_settings()
    environment = (settings.environment or "").strip().lower()
    if environment in {"prod", "production"}:
        return "mysql"
    return "sqlite"


def _plain(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, Decimal):
        return float(value)
    return value


def _public_model(row: Any) -> dict:
    return {column.name: _plain(getattr(row, column.name)) for column in row.__table__.columns}


def get_pool_by_strategy(strategy_code: str) -> List[Dict[str, Any]]:
    """Get pool stocks by strategy code."""
    if _repo_backend() == "sqlite":
        return sqlite_q(
            """
            SELECT * FROM strategy_pools
            WHERE strategy_code = ? AND status = 'active'
            ORDER BY add_date DESC
            """,
            (strategy_code,),
        )
    with session_scope() as session:
        rows = session.execute(
            select(StrategyPool)
            .where(StrategyPool.strategy_code == strategy_code, StrategyPool.status == "active")
            .order_by(StrategyPool.add_date.desc(), StrategyPool.id.desc())
        ).scalars().all()
        return [_public_model(row) for row in rows]


def add_to_pool(strategy_code: str, code: str, name: str, add_date: str, add_price: float, reason: str = "") -> bool:
    """Add stock to strategy pool."""
    try:
        if _repo_backend() == "sqlite":
            sqlite_execute(
                """
                INSERT OR IGNORE INTO strategy_pools
                (strategy_code, code, name, add_date, add_price, reason)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (strategy_code, code, name, add_date, add_price, reason),
            )
            return True
        with session_scope() as session:
            statement = mysql_insert(StrategyPool).values(
                strategy_code=strategy_code,
                code=code,
                name=name,
                add_date=add_date,
                add_price=add_price,
                reason=reason or "",
                status="active",
                created_at=datetime.now(),
            )
            statement = statement.prefix_with("IGNORE")
            session.execute(statement)
        return True
    except Exception:
        return False


def remove_from_pool(strategy_code: str, code: str) -> bool:
    """Remove stock from strategy pool."""
    try:
        if _repo_backend() == "sqlite":
            sqlite_execute(
                "UPDATE strategy_pools SET status = 'removed' WHERE strategy_code = ? AND code = ?",
                (strategy_code, code),
            )
            return True
        with session_scope() as session:
            row = session.execute(
                select(StrategyPool).where(StrategyPool.strategy_code == strategy_code, StrategyPool.code == code)
            ).scalar_one_or_none()
            if row is not None:
                row.status = "removed"
                session.flush()
        return True
    except Exception:
        return False


def get_backtest_results(strategy_code: str) -> List[Dict[str, Any]]:
    """Get backtest results by strategy."""
    if _repo_backend() == "sqlite":
        return sqlite_q(
            """
            SELECT * FROM backtest_results
            WHERE strategy_code = ?
            ORDER BY backtest_date DESC
            """,
            (strategy_code,),
        )
    with session_scope() as session:
        rows = session.execute(
            select(BacktestResult)
            .where(BacktestResult.strategy_code == strategy_code)
            .order_by(BacktestResult.backtest_date.desc(), BacktestResult.id.desc())
        ).scalars().all()
        return [_public_model(row) for row in rows]


def save_backtest_result(strategy_code: str, start_date: str, end_date: str, results: Dict[str, Any]) -> bool:
    """Save backtest result."""
    try:
        payload = {
            "strategy_code": strategy_code,
            "start_date": start_date,
            "end_date": end_date,
            "total_trades": results.get("total_trades"),
            "win_rate": results.get("win_rate"),
            "avg_return": results.get("avg_return"),
            "max_return": results.get("max_return"),
            "max_drawdown": results.get("max_drawdown"),
            "sharpe_ratio": results.get("sharpe_ratio"),
            "total_return": results.get("total_return"),
        }
        if _repo_backend() == "sqlite":
            sqlite_execute(
                """
                INSERT INTO backtest_results
                (strategy_code, start_date, end_date, total_trades, win_rate, avg_return,
                 max_return, max_drawdown, sharpe_ratio, total_return)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["strategy_code"],
                    payload["start_date"],
                    payload["end_date"],
                    payload["total_trades"],
                    payload["win_rate"],
                    payload["avg_return"],
                    payload["max_return"],
                    payload["max_drawdown"],
                    payload["sharpe_ratio"],
                    payload["total_return"],
                ),
            )
            return True
        with session_scope() as session:
            session.add(BacktestResult(**payload, backtest_date=datetime.now()))
            session.flush()
        return True
    except Exception:
        return False
