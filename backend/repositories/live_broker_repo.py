"""Persistence for guarded live broker requests and fills."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from backend.core.config import get_settings
from backend.db.models.live_broker import LiveBrokerFill, LiveBrokerReconciliation, LiveBrokerRequest
from backend.db.session import session_scope
from backend.repositories.db import execute as sqlite_execute
from backend.repositories.db import execute_many as sqlite_execute_many
from backend.repositories.db import q as sqlite_q
from backend.repositories.db import q1 as sqlite_q1


def _repo_backend() -> str:
    settings = get_settings()
    return "mysql" if (settings.environment or "").strip().lower() in {"prod", "production"} else "sqlite"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def request_hash(payload: dict) -> str:
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def ensure_schema() -> None:
    if _repo_backend() != "sqlite":
        return
    sqlite_execute(
        """CREATE TABLE IF NOT EXISTS live_broker_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            adapter TEXT NOT NULL,
            account_id TEXT DEFAULT '',
            idempotency_key TEXT NOT NULL,
            request_hash TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            reason TEXT DEFAULT '',
            broker_order_id TEXT DEFAULT '',
            client_order_id TEXT DEFAULT '',
            payload_json TEXT DEFAULT '{}',
            response_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, idempotency_key)
        )"""
    )
    sqlite_execute("CREATE INDEX IF NOT EXISTS idx_live_broker_requests_created ON live_broker_requests(created_at)")
    sqlite_execute(
        """CREATE TABLE IF NOT EXISTS live_broker_fills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            account_id TEXT DEFAULT '',
            broker_order_id TEXT DEFAULT '',
            client_order_id TEXT DEFAULT '',
            symbol TEXT DEFAULT '',
            side TEXT DEFAULT '',
            quantity INTEGER DEFAULT 0,
            price REAL DEFAULT NULL,
            amount REAL DEFAULT NULL,
            fee REAL DEFAULT NULL,
            currency TEXT DEFAULT 'CNY',
            filled_at TEXT DEFAULT NULL,
            fill_key TEXT NOT NULL,
            source TEXT DEFAULT 'callback',
            payload_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, fill_key)
        )"""
    )
    sqlite_execute(
        """CREATE TABLE IF NOT EXISTS live_broker_reconciliations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            account_id TEXT DEFAULT '',
            idempotency_key TEXT NOT NULL,
            status TEXT DEFAULT 'reconciled',
            differences_count INTEGER DEFAULT 0,
            request_json TEXT DEFAULT '{}',
            result_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, idempotency_key)
        )"""
    )


def get_request(tenant_id: int, idempotency_key: str) -> dict | None:
    ensure_schema()
    if _repo_backend() == "sqlite":
        row = sqlite_q1(
            "SELECT * FROM live_broker_requests WHERE tenant_id=? AND idempotency_key=?",
            (int(tenant_id or 0), str(idempotency_key or "")),
        )
        return _request_item(row) if row else None
    with session_scope() as session:
        row = session.execute(
            select(LiveBrokerRequest).where(
                LiveBrokerRequest.tenant_id == int(tenant_id or 0),
                LiveBrokerRequest.idempotency_key == str(idempotency_key or ""),
            )
        ).scalar_one_or_none()
        return _request_item(_model_request(row)) if row else None


def record_request(
    tenant_id: int,
    *,
    action: str,
    adapter: str,
    account_id: str,
    idempotency_key: str,
    payload: dict,
    status: str,
    reason: str = "",
    response: dict | None = None,
    broker_order_id: str = "",
    client_order_id: str = "",
) -> dict:
    ensure_schema()
    hashed = request_hash(payload)
    now = _now()
    if _repo_backend() == "sqlite":
        sqlite_execute_many(
            """INSERT INTO live_broker_requests
            (tenant_id, action, adapter, account_id, idempotency_key, request_hash, status, reason,
             broker_order_id, client_order_id, payload_json, response_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, idempotency_key) DO UPDATE SET
                status=excluded.status,
                reason=excluded.reason,
                broker_order_id=excluded.broker_order_id,
                client_order_id=excluded.client_order_id,
                response_json=excluded.response_json,
                updated_at=excluded.updated_at
            WHERE live_broker_requests.request_hash=excluded.request_hash""",
            [
                (
                    int(tenant_id or 0),
                    action,
                    adapter,
                    account_id,
                    idempotency_key,
                    hashed,
                    status,
                    reason,
                    broker_order_id,
                    client_order_id,
                    _json(payload),
                    _json(response),
                    now,
                    now,
                )
            ],
        )
        return get_request(tenant_id, idempotency_key) or {}
    with session_scope() as session:
        statement = mysql_insert(LiveBrokerRequest).values(
            tenant_id=int(tenant_id or 0),
            action=action,
            adapter=adapter,
            account_id=account_id,
            idempotency_key=idempotency_key,
            request_hash=hashed,
            status=status,
            reason=reason,
            broker_order_id=broker_order_id or None,
            client_order_id=client_order_id or None,
            payload_json=payload,
            response_json=response or {},
        )
        statement = statement.on_duplicate_key_update(
            status=case((LiveBrokerRequest.request_hash == statement.inserted.request_hash, statement.inserted.status), else_=LiveBrokerRequest.status),
            reason=case((LiveBrokerRequest.request_hash == statement.inserted.request_hash, statement.inserted.reason), else_=LiveBrokerRequest.reason),
            broker_order_id=case(
                (LiveBrokerRequest.request_hash == statement.inserted.request_hash, statement.inserted.broker_order_id),
                else_=LiveBrokerRequest.broker_order_id,
            ),
            client_order_id=case(
                (LiveBrokerRequest.request_hash == statement.inserted.request_hash, statement.inserted.client_order_id),
                else_=LiveBrokerRequest.client_order_id,
            ),
            response_json=case((LiveBrokerRequest.request_hash == statement.inserted.request_hash, statement.inserted.response_json), else_=LiveBrokerRequest.response_json),
        )
        session.execute(statement)
    return get_request(tenant_id, idempotency_key) or {}


def count_recent_requests(tenant_id: int, *, action: str, since_seconds: int = 60) -> int:
    ensure_schema()
    cutoff = (datetime.now() - timedelta(seconds=max(1, int(since_seconds or 60)))).isoformat(timespec="seconds")
    if _repo_backend() == "sqlite":
        row = sqlite_q1(
            "SELECT COUNT(*) AS cnt FROM live_broker_requests WHERE tenant_id=? AND action=? AND created_at>=?",
            (int(tenant_id or 0), action, cutoff),
        ) or {}
        return int(row.get("cnt") or 0)
    with session_scope() as session:
        rows = session.execute(
            select(LiveBrokerRequest.id).where(
                LiveBrokerRequest.tenant_id == int(tenant_id or 0),
                LiveBrokerRequest.action == action,
                LiveBrokerRequest.created_at >= datetime.fromisoformat(cutoff),
            )
        ).all()
        return len(rows)


def upsert_fills(tenant_id: int, fills: list[dict]) -> int:
    ensure_schema()
    normalized = [_fill_payload(item) for item in fills]
    normalized = [item for item in normalized if item["fill_key"]]
    if not normalized:
        return 0
    if _repo_backend() == "sqlite":
        return sqlite_execute_many(
            """INSERT INTO live_broker_fills
            (tenant_id, account_id, broker_order_id, client_order_id, symbol, side, quantity, price, amount,
             fee, currency, filled_at, fill_key, source, payload_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(tenant_id, fill_key) DO UPDATE SET
                account_id=excluded.account_id,
                broker_order_id=excluded.broker_order_id,
                client_order_id=excluded.client_order_id,
                symbol=excluded.symbol,
                side=excluded.side,
                quantity=excluded.quantity,
                price=excluded.price,
                amount=excluded.amount,
                fee=excluded.fee,
                currency=excluded.currency,
                filled_at=excluded.filled_at,
                source=excluded.source,
                payload_json=excluded.payload_json,
                updated_at=CURRENT_TIMESTAMP""",
            [
                (
                    int(tenant_id or 0),
                    item["account_id"],
                    item["broker_order_id"],
                    item["client_order_id"],
                    item["symbol"],
                    item["side"],
                    item["quantity"],
                    item["price"],
                    item["amount"],
                    item["fee"],
                    item["currency"],
                    item["filled_at"],
                    item["fill_key"],
                    item["source"],
                    _json(item["payload"]),
                )
                for item in normalized
            ],
        )
    with session_scope() as session:
        for item in normalized:
            statement = mysql_insert(LiveBrokerFill).values(tenant_id=int(tenant_id or 0), **{k: v for k, v in item.items() if k != "payload"}, payload_json=item["payload"])
            statement = statement.on_duplicate_key_update(payload_json=statement.inserted.payload_json)
            session.execute(statement)
    return len(normalized)


def list_fills(tenant_id: int, *, account_id: str = "", limit: int = 100) -> list[dict]:
    ensure_schema()
    safe_limit = max(1, min(int(limit or 100), 500))
    if _repo_backend() == "sqlite":
        where = ["tenant_id=?"]
        params: list[Any] = [int(tenant_id or 0)]
        if account_id:
            where.append("account_id=?")
            params.append(account_id)
        rows = sqlite_q(
            f"SELECT * FROM live_broker_fills WHERE {' AND '.join(where)} ORDER BY COALESCE(filled_at, created_at) DESC LIMIT ?",
            tuple(params + [safe_limit]),
        )
        return [_fill_item(row) for row in rows]
    with session_scope() as session:
        query = select(LiveBrokerFill).where(LiveBrokerFill.tenant_id == int(tenant_id or 0))
        if account_id:
            query = query.where(LiveBrokerFill.account_id == account_id)
        rows = session.execute(query.order_by(LiveBrokerFill.created_at.desc()).limit(safe_limit)).scalars().all()
        return [_fill_item(_model_fill(row)) for row in rows]


def record_reconciliation(tenant_id: int, *, account_id: str, idempotency_key: str, request: dict, result: dict) -> dict:
    ensure_schema()
    differences = result.get("differences") if isinstance(result.get("differences"), list) else []
    status = "reconciled" if not differences else "differences_found"
    if _repo_backend() == "sqlite":
        sqlite_execute_many(
            """INSERT INTO live_broker_reconciliations
            (tenant_id, account_id, idempotency_key, status, differences_count, request_json, result_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(tenant_id, idempotency_key) DO UPDATE SET
                status=excluded.status,
                differences_count=excluded.differences_count,
                result_json=excluded.result_json,
                updated_at=CURRENT_TIMESTAMP""",
            [(int(tenant_id or 0), account_id, idempotency_key, status, len(differences), _json(request), _json(result))],
        )
        row = sqlite_q1(
            "SELECT * FROM live_broker_reconciliations WHERE tenant_id=? AND idempotency_key=?",
            (int(tenant_id or 0), idempotency_key),
        )
        return dict(row) if row else {}
    with session_scope() as session:
        statement = mysql_insert(LiveBrokerReconciliation).values(
            tenant_id=int(tenant_id or 0),
            account_id=account_id,
            idempotency_key=idempotency_key,
            status=status,
            differences_count=len(differences),
            request_json=request,
            result_json=result,
        )
        statement = statement.on_duplicate_key_update(status=statement.inserted.status, differences_count=statement.inserted.differences_count, result_json=statement.inserted.result_json)
        session.execute(statement)
    return {"status": status, "differences_count": len(differences)}


def _fill_payload(item: dict) -> dict:
    payload = dict(item or {})
    quantity = int(_decimal(payload.get("quantity") or payload.get("filled_quantity")))
    price = _decimal(payload.get("price") or payload.get("filled_price"))
    amount = _decimal(payload.get("amount"), price * Decimal(quantity) if price and quantity else Decimal("0"))
    fill_key = str(payload.get("fill_key") or payload.get("fill_id") or payload.get("id") or "").strip()
    if not fill_key:
        fill_key = request_hash(payload)[:32]
    return {
        "account_id": str(payload.get("account_id") or "").strip(),
        "broker_order_id": str(payload.get("broker_order_id") or payload.get("order_id") or "").strip(),
        "client_order_id": str(payload.get("client_order_id") or "").strip(),
        "symbol": str(payload.get("symbol") or "").strip(),
        "side": str(payload.get("side") or "").strip().upper(),
        "quantity": quantity,
        "price": float(price) if price else None,
        "amount": float(amount) if amount else None,
        "fee": float(_decimal(payload.get("fee"))) if payload.get("fee") not in (None, "") else None,
        "currency": str(payload.get("currency") or "CNY").strip() or "CNY",
        "filled_at": str(payload.get("filled_at") or payload.get("trade_time") or _now()),
        "fill_key": fill_key,
        "source": str(payload.get("source") or "callback").strip() or "callback",
        "payload": payload,
    }


def _decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value in (None, ""):
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _loads(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw or "{}")
    except Exception:
        return {}


def _request_item(row: dict | None) -> dict:
    if not row:
        return {}
    item = dict(row)
    item["payload"] = _loads(item.pop("payload_json", {}))
    item["response"] = _loads(item.pop("response_json", {}))
    return item


def _fill_item(row: dict | None) -> dict:
    if not row:
        return {}
    item = dict(row)
    item["payload"] = _loads(item.pop("payload_json", {}))
    return item


def _model_request(row: LiveBrokerRequest | None) -> dict:
    if row is None:
        return {}
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "action": row.action,
        "adapter": row.adapter,
        "account_id": row.account_id,
        "idempotency_key": row.idempotency_key,
        "request_hash": row.request_hash,
        "status": row.status,
        "reason": row.reason,
        "broker_order_id": row.broker_order_id,
        "client_order_id": row.client_order_id,
        "payload_json": row.payload_json,
        "response_json": row.response_json,
        "created_at": row.created_at.isoformat(timespec="seconds") if row.created_at else None,
        "updated_at": row.updated_at.isoformat(timespec="seconds") if row.updated_at else None,
    }


def _model_fill(row: LiveBrokerFill | None) -> dict:
    if row is None:
        return {}
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "account_id": row.account_id,
        "broker_order_id": row.broker_order_id,
        "client_order_id": row.client_order_id,
        "symbol": row.symbol,
        "side": row.side,
        "quantity": row.quantity,
        "price": float(row.price) if row.price is not None else None,
        "amount": float(row.amount) if row.amount is not None else None,
        "fee": float(row.fee) if row.fee is not None else None,
        "currency": row.currency,
        "filled_at": row.filled_at.isoformat(timespec="seconds") if row.filled_at else None,
        "fill_key": row.fill_key,
        "source": row.source,
        "payload_json": row.payload_json,
        "created_at": row.created_at.isoformat(timespec="seconds") if row.created_at else None,
    }
