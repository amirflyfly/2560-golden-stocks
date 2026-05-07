"""Paper trading ledger repository."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, func, select

from backend.core.config import get_settings
from backend.db.models import PaperAccount, PaperFill, PaperOrder, PaperPosition, TradeSignal
from backend.db.session import session_scope
from backend.infrastructure.market_data.utils import infer_security_type, normalize_bar_interval
from backend.repositories.db import execute as sqlite_execute
from backend.repositories.db import execute_many as sqlite_execute_many
from backend.repositories.db import q as sqlite_q
from backend.repositories.db import q1 as sqlite_q1


def _repo_backend() -> str:
    forced = (os.getenv("TRADING_REPOSITORY_BACKEND") or "auto").strip().lower()
    if forced in {"sqlite", "mysql"}:
        return forced
    settings = get_settings()
    return "mysql" if (settings.environment or "").strip().lower() in {"prod", "production"} else "sqlite"


def _decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value in (None, ""):
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _float(value: Any) -> float:
    return float(_decimal(value))


def _dt(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value)


def _parse_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value or {}, ensure_ascii=False)


def _json_value(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    try:
        decoded = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _security_type(value: Any = None, symbol: str = "") -> str:
    text = str(value or "").strip().lower()
    if text in {"", "all", "*", "any"}:
        return infer_security_type(symbol, symbol) if symbol else "stock"
    return text


def ensure_default_account(
    tenant_id: int,
    *,
    name: str = "Default Paper Account",
    initial_cash: Decimal | float | str = Decimal("1000000"),
) -> dict:
    initial = _decimal(initial_cash, Decimal("1000000"))
    if _repo_backend() == "sqlite":
        row = sqlite_q1("SELECT * FROM paper_accounts WHERE tenant_id=? AND name=?", (int(tenant_id or 0), name))
        if row:
            return _account_item(row)
        sqlite_execute_many(
            """INSERT OR IGNORE INTO paper_accounts
            (tenant_id, name, mode, broker_type, status, currency, initial_cash, cash, config_json, created_at, updated_at)
            VALUES (?, ?, 'paper', 'paper', 'active', 'CNY', ?, ?, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            [(int(tenant_id or 0), name, _float(initial), _float(initial))],
        )
        row = sqlite_q1("SELECT * FROM paper_accounts WHERE tenant_id=? AND name=?", (int(tenant_id or 0), name)) or {}
        return _account_item(row)

    with session_scope() as session:
        row = session.execute(
            select(PaperAccount).where(PaperAccount.tenant_id == int(tenant_id or 0), PaperAccount.name == name)
        ).scalar_one_or_none()
        if row is None:
            row = PaperAccount(
                tenant_id=int(tenant_id or 0),
                name=name,
                mode="paper",
                broker_type="paper",
                status="active",
                currency="CNY",
                initial_cash=initial,
                cash=initial,
                config_json={},
            )
            session.add(row)
            session.flush()
        return _account_item(_public_account(row))


def get_account(account_id: int) -> dict | None:
    if _repo_backend() == "sqlite":
        row = sqlite_q1("SELECT * FROM paper_accounts WHERE id=?", (int(account_id),))
        return _account_item(row) if row else None
    with session_scope() as session:
        row = session.get(PaperAccount, int(account_id))
        return _account_item(_public_account(row)) if row else None


def list_accounts(tenant_id: int) -> list[dict]:
    if _repo_backend() == "sqlite":
        return [_account_item(row) for row in sqlite_q("SELECT * FROM paper_accounts WHERE tenant_id=? ORDER BY id ASC", (int(tenant_id or 0),))]
    with session_scope() as session:
        rows = session.execute(select(PaperAccount).where(PaperAccount.tenant_id == int(tenant_id or 0)).order_by(PaperAccount.id.asc())).scalars().all()
        return [_account_item(_public_account(row)) for row in rows]


def list_positions(tenant_id: int, account_id: int | None = None, *, active_only: bool = False) -> list[dict]:
    if _repo_backend() == "sqlite":
        where = ["tenant_id=?"]
        params: list[Any] = [int(tenant_id or 0)]
        if account_id:
            where.append("account_id=?")
            params.append(int(account_id))
        if active_only:
            where.append("quantity>0")
        rows = sqlite_q(f"SELECT * FROM paper_positions WHERE {' AND '.join(where)} ORDER BY market_value DESC, symbol ASC", tuple(params))
        return [_position_item(row) for row in rows]

    with session_scope() as session:
        query = select(PaperPosition).where(PaperPosition.tenant_id == int(tenant_id or 0))
        if account_id:
            query = query.where(PaperPosition.account_id == int(account_id))
        if active_only:
            query = query.where(PaperPosition.quantity > 0)
        rows = session.execute(query.order_by(PaperPosition.market_value.desc(), PaperPosition.symbol.asc())).scalars().all()
        return [_position_item(_public_position(row)) for row in rows]


def get_position(tenant_id: int, account_id: int, symbol: str) -> dict | None:
    normalized_symbol = str(symbol or "").strip()
    if _repo_backend() == "sqlite":
        row = sqlite_q1(
            "SELECT * FROM paper_positions WHERE tenant_id=? AND account_id=? AND symbol=?",
            (int(tenant_id or 0), int(account_id), normalized_symbol),
        )
        return _position_item(row) if row else None
    with session_scope() as session:
        row = session.execute(
            select(PaperPosition).where(
                PaperPosition.tenant_id == int(tenant_id or 0),
                PaperPosition.account_id == int(account_id),
                PaperPosition.symbol == normalized_symbol,
            )
        ).scalar_one_or_none()
        return _position_item(_public_position(row)) if row else None


def order_exists(tenant_id: int, idempotency_key: str) -> bool:
    if _repo_backend() == "sqlite":
        row = sqlite_q1("SELECT id FROM paper_orders WHERE tenant_id=? AND idempotency_key=?", (int(tenant_id or 0), idempotency_key))
        return bool(row)
    with session_scope() as session:
        found = session.execute(
            select(PaperOrder.id).where(PaperOrder.tenant_id == int(tenant_id or 0), PaperOrder.idempotency_key == idempotency_key)
        ).first()
        return bool(found)


def upsert_trade_signal(
    tenant_id: int,
    *,
    account_id: int | None,
    strategy_id: int | None,
    strategy_code: str,
    symbol: str,
    signal_date: str | None,
    signal_type: str,
    source_hash: str,
    score: Any = None,
    price_ref: Any = None,
    data_quality: str | None = None,
    security_type: str | None = None,
    bar_interval: str | None = "1d",
    payload: dict | None = None,
) -> dict:
    normalized_type = str(signal_type or "BUY").upper()
    normalized_symbol = str(symbol or "").strip()
    normalized_security_type = _security_type(security_type, normalized_symbol)
    normalized_bar_interval = normalize_bar_interval(bar_interval)
    if _repo_backend() == "sqlite":
        sqlite_execute_many(
            """INSERT INTO trade_signals
            (tenant_id, account_id, strategy_id, strategy_code, symbol, security_type, bar_interval, signal_date, signal_type,
             score, price_ref, data_quality, status, source_hash, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(tenant_id, source_hash) DO UPDATE SET
                account_id=excluded.account_id,
                strategy_id=excluded.strategy_id,
                strategy_code=excluded.strategy_code,
                symbol=excluded.symbol,
                security_type=excluded.security_type,
                bar_interval=excluded.bar_interval,
                signal_date=excluded.signal_date,
                signal_type=excluded.signal_type,
                score=excluded.score,
                price_ref=excluded.price_ref,
                data_quality=excluded.data_quality,
                payload_json=excluded.payload_json,
                updated_at=CURRENT_TIMESTAMP""",
            [
                (
                    int(tenant_id or 0),
                    account_id,
                    strategy_id,
                    str(strategy_code or ""),
                    normalized_symbol,
                    normalized_security_type,
                    normalized_bar_interval,
                    signal_date,
                    normalized_type,
                    _float(score) if score is not None else None,
                    _float(price_ref) if price_ref is not None else None,
                    data_quality or "",
                    source_hash,
                    _json_text(payload),
                )
            ],
        )
        row = sqlite_q1("SELECT * FROM trade_signals WHERE tenant_id=? AND source_hash=?", (int(tenant_id or 0), source_hash)) or {}
        return _signal_item(row)

    with session_scope() as session:
        row = session.execute(
            select(TradeSignal).where(TradeSignal.tenant_id == int(tenant_id or 0), TradeSignal.source_hash == source_hash)
        ).scalar_one_or_none()
        if row is None:
            row = TradeSignal(tenant_id=int(tenant_id or 0), source_hash=source_hash)
            session.add(row)
        row.account_id = account_id
        row.strategy_id = strategy_id
        row.strategy_code = str(strategy_code or "")
        row.symbol = normalized_symbol
        row.security_type = normalized_security_type
        row.bar_interval = normalized_bar_interval
        row.signal_date = _parse_date(signal_date)
        row.signal_type = normalized_type
        row.score = _decimal(score) if score is not None else None
        row.price_ref = _decimal(price_ref) if price_ref is not None else None
        row.data_quality = data_quality
        row.status = row.status or "open"
        row.payload_json = payload or {}
        session.flush()
        return _signal_item(_public_signal(row))


def list_trade_signals(tenant_id: int, *, limit: int = 100) -> list[dict]:
    safe_limit = max(1, min(int(limit or 100), 500))
    if _repo_backend() == "sqlite":
        rows = sqlite_q("SELECT * FROM trade_signals WHERE tenant_id=? ORDER BY id DESC LIMIT ?", (int(tenant_id or 0), safe_limit))
        return [_signal_item(row) for row in rows]
    with session_scope() as session:
        rows = session.execute(
            select(TradeSignal).where(TradeSignal.tenant_id == int(tenant_id or 0)).order_by(TradeSignal.id.desc()).limit(safe_limit)
        ).scalars().all()
        return [_signal_item(_public_signal(row)) for row in rows]


def create_filled_order(
    tenant_id: int,
    *,
    account_id: int,
    symbol: str,
    side: str,
    quantity: int,
    price: Decimal | float | str,
    strategy_id: int | None = None,
    strategy_code: str | None = None,
    idempotency_key: str,
    source_signal_hash: str | None = None,
    reason: str = "",
    metadata: dict | None = None,
    security_type: str | None = None,
    bar_interval: str | None = "1d",
    fee_rate: Decimal | float | str = Decimal("0"),
) -> dict:
    normalized_side = str(side or "").upper()
    normalized_symbol = str(symbol or "").strip()
    normalized_security_type = _security_type(security_type, normalized_symbol)
    normalized_bar_interval = normalize_bar_interval(bar_interval)
    qty = max(0, int(quantity or 0))
    fill_price = _decimal(price)
    fee = (fill_price * Decimal(qty) * _decimal(fee_rate)).quantize(Decimal("0.0001"))
    amount = (fill_price * Decimal(qty)).quantize(Decimal("0.0001"))
    filled_at = datetime.now()
    if qty <= 0 or fill_price <= 0:
        raise ValueError("quantity and price must be positive")
    if order_exists(tenant_id, idempotency_key):
        return {"created": False, "order": get_order_by_idempotency(tenant_id, idempotency_key)}

    if _repo_backend() == "sqlite":
        account = get_account(account_id)
        if not account:
            raise ValueError("paper account not found")
        cash = _decimal(account.get("cash"))
        signed_cash = -amount - fee if normalized_side == "BUY" else amount - fee
        if normalized_side == "BUY" and cash + signed_cash < 0:
            raise ValueError("paper account cash is insufficient")
        sqlite_execute_many(
            """INSERT INTO paper_orders
            (tenant_id, account_id, strategy_id, strategy_code, symbol, security_type, bar_interval, side, quantity, order_type,
             requested_price, status, filled_quantity, avg_fill_price, idempotency_key,
             source_signal_hash, reason, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'market', ?, 'filled', ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            [
                (
                    int(tenant_id or 0),
                    int(account_id),
                    strategy_id,
                    strategy_code or "",
                    normalized_symbol,
                    normalized_security_type,
                    normalized_bar_interval,
                    normalized_side,
                    qty,
                    _float(fill_price),
                    qty,
                    _float(fill_price),
                    idempotency_key,
                    source_signal_hash or "",
                    reason,
                    _json_text(metadata),
                )
            ],
        )
        order = get_order_by_idempotency(tenant_id, idempotency_key)
        sqlite_execute_many(
            """INSERT INTO paper_fills
            (tenant_id, account_id, order_id, symbol, security_type, bar_interval, side, quantity, price, amount, fee, filled_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            [(int(tenant_id or 0), int(account_id), int(order["id"]), normalized_symbol, normalized_security_type, normalized_bar_interval, normalized_side, qty, _float(fill_price), _float(amount), _float(fee), filled_at.isoformat(timespec="seconds"))],
        )
        sqlite_execute(
            "UPDATE paper_accounts SET cash=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (_float(cash + signed_cash), int(account_id)),
        )
        _apply_position_fill_sqlite(int(tenant_id or 0), int(account_id), normalized_symbol, normalized_side, qty, fill_price, filled_at, security_type=normalized_security_type, bar_interval=normalized_bar_interval)
        return {"created": True, "order": get_order_by_idempotency(tenant_id, idempotency_key)}

    with session_scope() as session:
        account = session.get(PaperAccount, int(account_id))
        if account is None:
            raise ValueError("paper account not found")
        signed_cash = -amount - fee if normalized_side == "BUY" else amount - fee
        if normalized_side == "BUY" and account.cash + signed_cash < 0:
            raise ValueError("paper account cash is insufficient")
        order = PaperOrder(
            tenant_id=int(tenant_id or 0),
            account_id=int(account_id),
            strategy_id=strategy_id,
            strategy_code=strategy_code,
            symbol=normalized_symbol,
            security_type=normalized_security_type,
            bar_interval=normalized_bar_interval,
            side=normalized_side,
            quantity=qty,
            order_type="market",
            requested_price=fill_price,
            status="filled",
            filled_quantity=qty,
            avg_fill_price=fill_price,
            idempotency_key=idempotency_key,
            source_signal_hash=source_signal_hash,
            reason=reason,
            metadata_json=metadata or {},
        )
        session.add(order)
        session.flush()
        session.add(
            PaperFill(
                tenant_id=int(tenant_id or 0),
                account_id=int(account_id),
                order_id=order.id,
                symbol=normalized_symbol,
                security_type=normalized_security_type,
                bar_interval=normalized_bar_interval,
                side=normalized_side,
                quantity=qty,
                price=fill_price,
                amount=amount,
                fee=fee,
                filled_at=filled_at,
            )
        )
        account.cash = account.cash + signed_cash
        _apply_position_fill_mysql(session, int(tenant_id or 0), int(account_id), normalized_symbol, normalized_side, qty, fill_price, filled_at, security_type=normalized_security_type, bar_interval=normalized_bar_interval)
        session.flush()
        return {"created": True, "order": _order_item(_public_order(order))}


def get_order_by_idempotency(tenant_id: int, idempotency_key: str) -> dict | None:
    if _repo_backend() == "sqlite":
        row = sqlite_q1("SELECT * FROM paper_orders WHERE tenant_id=? AND idempotency_key=?", (int(tenant_id or 0), idempotency_key))
        return _order_item(row) if row else None
    with session_scope() as session:
        row = session.execute(
            select(PaperOrder).where(PaperOrder.tenant_id == int(tenant_id or 0), PaperOrder.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        return _order_item(_public_order(row)) if row else None


def list_orders(tenant_id: int, account_id: int | None = None, *, limit: int = 100) -> list[dict]:
    safe_limit = max(1, min(int(limit or 100), 500))
    if _repo_backend() == "sqlite":
        where = ["tenant_id=?"]
        params: list[Any] = [int(tenant_id or 0)]
        if account_id:
            where.append("account_id=?")
            params.append(int(account_id))
        rows = sqlite_q(f"SELECT * FROM paper_orders WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?", tuple(params + [safe_limit]))
        return [_order_item(row) for row in rows]
    with session_scope() as session:
        query = select(PaperOrder).where(PaperOrder.tenant_id == int(tenant_id or 0))
        if account_id:
            query = query.where(PaperOrder.account_id == int(account_id))
        rows = session.execute(query.order_by(PaperOrder.id.desc()).limit(safe_limit)).scalars().all()
        return [_order_item(_public_order(row)) for row in rows]


def list_fills(tenant_id: int, account_id: int | None = None, *, limit: int = 100) -> list[dict]:
    safe_limit = max(1, min(int(limit or 100), 500))
    if _repo_backend() == "sqlite":
        where = ["tenant_id=?"]
        params: list[Any] = [int(tenant_id or 0)]
        if account_id:
            where.append("account_id=?")
            params.append(int(account_id))
        rows = sqlite_q(f"SELECT * FROM paper_fills WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?", tuple(params + [safe_limit]))
        return [_fill_item(row) for row in rows]
    with session_scope() as session:
        query = select(PaperFill).where(PaperFill.tenant_id == int(tenant_id or 0))
        if account_id:
            query = query.where(PaperFill.account_id == int(account_id))
        rows = session.execute(query.order_by(PaperFill.id.desc()).limit(safe_limit)).scalars().all()
        return [_fill_item(_public_fill(row)) for row in rows]


def summary(tenant_id: int, account_id: int | None = None) -> dict:
    accounts = list_accounts(tenant_id)
    if account_id:
        accounts = [item for item in accounts if int(item.get("id") or 0) == int(account_id)]
    positions = list_positions(tenant_id, account_id, active_only=True)
    cash = sum(_decimal(item.get("cash")) for item in accounts)
    initial_cash = sum(_decimal(item.get("initial_cash")) for item in accounts)
    market_value = sum(_decimal(item.get("market_value")) for item in positions)
    unrealized_pnl = sum(_decimal(item.get("unrealized_pnl")) for item in positions)
    realized_pnl = sum(_decimal(item.get("realized_pnl")) for item in positions)
    equity = cash + market_value
    return {
        "tenant_id": int(tenant_id or 0),
        "account_count": len(accounts),
        "cash": _float(cash),
        "initial_cash": _float(initial_cash),
        "market_value": _float(market_value),
        "equity": _float(equity),
        "realized_pnl": _float(realized_pnl),
        "unrealized_pnl": _float(unrealized_pnl),
        "total_return_pct": _float((equity - initial_cash) / initial_cash) if initial_cash else 0,
        "active_positions": len(positions),
        "mode": "paper",
        "live_trading": {
            "supported": True,
            "default_enabled": False,
            "adapter_contract": "BrokerAdapter.submit_order/reconcile_orders",
            "guard": "paper ledger never sends broker orders; live adapters are configured outside paper trading",
        },
    }


def reset_account(tenant_id: int, account_id: int) -> int:
    account = get_account(account_id)
    if not account or int(account.get("tenant_id") or 0) != int(tenant_id or 0):
        return 0
    initial_cash = _decimal(account.get("initial_cash"), Decimal("1000000"))
    if _repo_backend() == "sqlite":
        sqlite_execute("DELETE FROM paper_fills WHERE tenant_id=? AND account_id=?", (int(tenant_id or 0), int(account_id)))
        sqlite_execute("DELETE FROM paper_orders WHERE tenant_id=? AND account_id=?", (int(tenant_id or 0), int(account_id)))
        sqlite_execute("DELETE FROM paper_positions WHERE tenant_id=? AND account_id=?", (int(tenant_id or 0), int(account_id)))
        sqlite_execute("UPDATE paper_accounts SET cash=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (_float(initial_cash), int(account_id)))
        return 1
    with session_scope() as session:
        session.execute(delete(PaperFill).where(PaperFill.tenant_id == int(tenant_id or 0), PaperFill.account_id == int(account_id)))
        session.execute(delete(PaperOrder).where(PaperOrder.tenant_id == int(tenant_id or 0), PaperOrder.account_id == int(account_id)))
        session.execute(delete(PaperPosition).where(PaperPosition.tenant_id == int(tenant_id or 0), PaperPosition.account_id == int(account_id)))
        row = session.get(PaperAccount, int(account_id))
        if row:
            row.cash = initial_cash
    return 1


def _apply_position_fill_sqlite(
    tenant_id: int,
    account_id: int,
    symbol: str,
    side: str,
    quantity: int,
    price: Decimal,
    filled_at: datetime,
    *,
    security_type: str = "stock",
    bar_interval: str = "1d",
) -> None:
    normalized_security_type = _security_type(security_type, symbol)
    normalized_bar_interval = normalize_bar_interval(bar_interval)
    row = get_position(tenant_id, account_id, symbol)
    if not row:
        row = {
            "quantity": 0,
            "avg_cost": 0,
            "realized_pnl": 0,
        }
        sqlite_execute_many(
            """INSERT OR IGNORE INTO paper_positions
            (tenant_id, account_id, symbol, security_type, bar_interval, quantity, avg_cost, market_price, market_value, realized_pnl, unrealized_pnl, opened_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 0, 0, NULL, 0, 0, 0, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            [(tenant_id, account_id, symbol, normalized_security_type, normalized_bar_interval, filled_at.isoformat(timespec="seconds"))],
        )
    current_qty = int(row.get("quantity") or 0)
    avg_cost = _decimal(row.get("avg_cost"))
    realized = _decimal(row.get("realized_pnl"))
    if side == "BUY":
        new_qty = current_qty + quantity
        new_avg = ((avg_cost * Decimal(current_qty)) + (price * Decimal(quantity))) / Decimal(new_qty)
        realized_delta = Decimal("0")
    else:
        sell_qty = min(current_qty, quantity)
        new_qty = current_qty - sell_qty
        new_avg = avg_cost if new_qty > 0 else Decimal("0")
        realized_delta = (price - avg_cost) * Decimal(sell_qty)
    market_value = price * Decimal(new_qty)
    unrealized = (price - new_avg) * Decimal(new_qty) if new_qty > 0 else Decimal("0")
    sqlite_execute(
        """UPDATE paper_positions
        SET security_type=?, bar_interval=?, quantity=?, avg_cost=?, market_price=?, market_value=?, realized_pnl=?,
            unrealized_pnl=?, opened_at=COALESCE(opened_at, ?), updated_at=CURRENT_TIMESTAMP
        WHERE tenant_id=? AND account_id=? AND symbol=?""",
        (
            normalized_security_type,
            normalized_bar_interval,
            new_qty,
            _float(new_avg),
            _float(price),
            _float(market_value),
            _float(realized + realized_delta),
            _float(unrealized),
            filled_at.isoformat(timespec="seconds"),
            tenant_id,
            account_id,
            symbol,
        ),
    )


def _apply_position_fill_mysql(
    session,
    tenant_id: int,
    account_id: int,
    symbol: str,
    side: str,
    quantity: int,
    price: Decimal,
    filled_at: datetime,
    *,
    security_type: str = "stock",
    bar_interval: str = "1d",
) -> None:
    normalized_security_type = _security_type(security_type, symbol)
    normalized_bar_interval = normalize_bar_interval(bar_interval)
    row = session.execute(
        select(PaperPosition).where(PaperPosition.tenant_id == tenant_id, PaperPosition.account_id == account_id, PaperPosition.symbol == symbol)
    ).scalar_one_or_none()
    if row is None:
        row = PaperPosition(
            tenant_id=tenant_id,
            account_id=account_id,
            symbol=symbol,
            security_type=normalized_security_type,
            bar_interval=normalized_bar_interval,
            quantity=0,
            avg_cost=Decimal("0"),
            market_value=Decimal("0"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            opened_at=filled_at,
        )
        session.add(row)
        session.flush()
    row.security_type = normalized_security_type
    row.bar_interval = normalized_bar_interval
    if side == "BUY":
        new_qty = int(row.quantity or 0) + quantity
        row.avg_cost = ((row.avg_cost * Decimal(row.quantity or 0)) + (price * Decimal(quantity))) / Decimal(new_qty)
        row.quantity = new_qty
    else:
        sell_qty = min(int(row.quantity or 0), quantity)
        row.realized_pnl = row.realized_pnl + ((price - row.avg_cost) * Decimal(sell_qty))
        row.quantity = int(row.quantity or 0) - sell_qty
        if row.quantity <= 0:
            row.avg_cost = Decimal("0")
    row.market_price = price
    row.market_value = price * Decimal(row.quantity or 0)
    row.unrealized_pnl = (price - row.avg_cost) * Decimal(row.quantity or 0) if row.quantity > 0 else Decimal("0")


def _account_item(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "tenant_id": int(row.get("tenant_id") or 0),
        "name": row.get("name") or "",
        "mode": row.get("mode") or "paper",
        "broker_type": row.get("broker_type") or "paper",
        "status": row.get("status") or "active",
        "currency": row.get("currency") or "CNY",
        "initial_cash": _float(row.get("initial_cash")),
        "cash": _float(row.get("cash")),
        "config": _json_value(row.get("config_json")),
        "created_at": _dt(row.get("created_at")),
        "updated_at": _dt(row.get("updated_at")),
    }


def _position_item(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "tenant_id": int(row.get("tenant_id") or 0),
        "account_id": row.get("account_id"),
        "symbol": row.get("symbol") or "",
        "security_type": row.get("security_type") or _security_type(None, row.get("symbol") or ""),
        "bar_interval": row.get("bar_interval") or "1d",
        "quantity": int(row.get("quantity") or 0),
        "avg_cost": _float(row.get("avg_cost")),
        "market_price": _float(row.get("market_price")) if row.get("market_price") is not None else None,
        "market_value": _float(row.get("market_value")),
        "realized_pnl": _float(row.get("realized_pnl")),
        "unrealized_pnl": _float(row.get("unrealized_pnl")),
        "opened_at": _dt(row.get("opened_at")),
        "created_at": _dt(row.get("created_at")),
        "updated_at": _dt(row.get("updated_at")),
    }


def _order_item(row: dict | None) -> dict | None:
    if not row:
        return None
    return {
        "id": row.get("id"),
        "tenant_id": int(row.get("tenant_id") or 0),
        "account_id": row.get("account_id"),
        "strategy_id": row.get("strategy_id"),
        "strategy_code": row.get("strategy_code") or "",
        "symbol": row.get("symbol") or "",
        "security_type": row.get("security_type") or _security_type(None, row.get("symbol") or ""),
        "bar_interval": row.get("bar_interval") or "1d",
        "side": row.get("side") or "",
        "quantity": int(row.get("quantity") or 0),
        "order_type": row.get("order_type") or "market",
        "requested_price": _float(row.get("requested_price")) if row.get("requested_price") is not None else None,
        "limit_price": _float(row.get("limit_price")) if row.get("limit_price") is not None else None,
        "status": row.get("status") or "",
        "filled_quantity": int(row.get("filled_quantity") or 0),
        "avg_fill_price": _float(row.get("avg_fill_price")) if row.get("avg_fill_price") is not None else None,
        "idempotency_key": row.get("idempotency_key") or "",
        "source_signal_hash": row.get("source_signal_hash") or "",
        "reason": row.get("reason") or "",
        "metadata": _json_value(row.get("metadata_json")),
        "created_at": _dt(row.get("created_at")),
        "updated_at": _dt(row.get("updated_at")),
    }


def _signal_item(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "tenant_id": int(row.get("tenant_id") or 0),
        "account_id": row.get("account_id"),
        "strategy_id": row.get("strategy_id"),
        "strategy_code": row.get("strategy_code") or "",
        "symbol": row.get("symbol") or "",
        "security_type": row.get("security_type") or _security_type(None, row.get("symbol") or ""),
        "bar_interval": row.get("bar_interval") or "1d",
        "signal_date": _dt(row.get("signal_date"))[:10] if _dt(row.get("signal_date")) else None,
        "signal_type": row.get("signal_type") or "BUY",
        "score": _float(row.get("score")) if row.get("score") is not None else None,
        "price_ref": _float(row.get("price_ref")) if row.get("price_ref") is not None else None,
        "data_quality": row.get("data_quality") or "",
        "status": row.get("status") or "open",
        "source_hash": row.get("source_hash") or "",
        "payload": _json_value(row.get("payload_json")),
        "created_at": _dt(row.get("created_at")),
        "updated_at": _dt(row.get("updated_at")),
    }


def _fill_item(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "tenant_id": int(row.get("tenant_id") or 0),
        "account_id": row.get("account_id"),
        "order_id": row.get("order_id"),
        "symbol": row.get("symbol") or "",
        "security_type": row.get("security_type") or _security_type(None, row.get("symbol") or ""),
        "bar_interval": row.get("bar_interval") or "1d",
        "side": row.get("side") or "",
        "quantity": int(row.get("quantity") or 0),
        "price": _float(row.get("price")),
        "amount": _float(row.get("amount")),
        "fee": _float(row.get("fee")),
        "filled_at": _dt(row.get("filled_at")),
        "created_at": _dt(row.get("created_at")),
        "updated_at": _dt(row.get("updated_at")),
    }


def _public_signal(row: TradeSignal) -> dict:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "account_id": row.account_id,
        "strategy_id": row.strategy_id,
        "strategy_code": row.strategy_code,
        "symbol": row.symbol,
        "security_type": row.security_type,
        "bar_interval": row.bar_interval,
        "signal_date": row.signal_date,
        "signal_type": row.signal_type,
        "score": row.score,
        "price_ref": row.price_ref,
        "data_quality": row.data_quality,
        "status": row.status,
        "source_hash": row.source_hash,
        "payload_json": row.payload_json or {},
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _public_account(row: PaperAccount) -> dict:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "name": row.name,
        "mode": row.mode,
        "broker_type": row.broker_type,
        "status": row.status,
        "currency": row.currency,
        "initial_cash": row.initial_cash,
        "cash": row.cash,
        "config_json": row.config_json or {},
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _public_position(row: PaperPosition) -> dict:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "account_id": row.account_id,
        "symbol": row.symbol,
        "security_type": row.security_type,
        "bar_interval": row.bar_interval,
        "quantity": row.quantity,
        "avg_cost": row.avg_cost,
        "market_price": row.market_price,
        "market_value": row.market_value,
        "realized_pnl": row.realized_pnl,
        "unrealized_pnl": row.unrealized_pnl,
        "opened_at": row.opened_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _public_order(row: PaperOrder) -> dict:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "account_id": row.account_id,
        "strategy_id": row.strategy_id,
        "strategy_code": row.strategy_code,
        "symbol": row.symbol,
        "security_type": row.security_type,
        "bar_interval": row.bar_interval,
        "side": row.side,
        "quantity": row.quantity,
        "order_type": row.order_type,
        "requested_price": row.requested_price,
        "limit_price": row.limit_price,
        "status": row.status,
        "filled_quantity": row.filled_quantity,
        "avg_fill_price": row.avg_fill_price,
        "idempotency_key": row.idempotency_key,
        "source_signal_hash": row.source_signal_hash,
        "reason": row.reason,
        "metadata_json": row.metadata_json or {},
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _public_fill(row: PaperFill) -> dict:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "account_id": row.account_id,
        "order_id": row.order_id,
        "symbol": row.symbol,
        "security_type": row.security_type,
        "bar_interval": row.bar_interval,
        "side": row.side,
        "quantity": row.quantity,
        "price": row.price,
        "amount": row.amount,
        "fee": row.fee,
        "filled_at": row.filled_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
