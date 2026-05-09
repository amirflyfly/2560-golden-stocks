"""Paper trading API routes."""

from __future__ import annotations

from flask import Blueprint, request

from backend.application.audit_log_service import audit_log_service
from backend.application.live_broker_service import live_broker_service
from backend.application.paper_trading_service import PaperTradingService
from backend.core.errors import NotFoundError
from backend.core.responses import success
from backend.core.tenant_context import get_authenticated_tenant_context, require_role
from backend.repositories import paper_trading_repo

bp = Blueprint("api_v1_trading", __name__)
service = PaperTradingService()


@bp.get("/trading/paper/summary")
def paper_summary():
    context = get_authenticated_tenant_context()
    account_id = request.args.get("account_id")
    if not account_id:
        service.ensure_default_account(context.tenant_id)
    return success(service.summary(context.tenant_id, int(account_id) if account_id else None))


@bp.get("/trading/paper/accounts")
def paper_accounts():
    context = get_authenticated_tenant_context()
    account = service.ensure_default_account(context.tenant_id)
    items = paper_trading_repo.list_accounts(context.tenant_id)
    return success({"items": items, "default_account": account, "total": len(items), "tenant_id": context.tenant_id})


@bp.get("/trading/paper/positions")
def paper_positions():
    context = get_authenticated_tenant_context()
    account_id = request.args.get("account_id")
    active_only = str(request.args.get("active_only") or "0").lower() in {"1", "true", "yes"}
    items = paper_trading_repo.list_positions(context.tenant_id, int(account_id) if account_id else None, active_only=active_only)
    return success({"items": items, "total": len(items), "tenant_id": context.tenant_id})


@bp.get("/trading/paper/orders")
def paper_orders():
    context = get_authenticated_tenant_context()
    account_id = request.args.get("account_id")
    limit = int(request.args.get("limit") or 100)
    items = paper_trading_repo.list_orders(context.tenant_id, int(account_id) if account_id else None, limit=limit)
    return success({"items": items, "total": len(items), "tenant_id": context.tenant_id})


@bp.get("/trading/signals")
def trade_signals():
    context = get_authenticated_tenant_context()
    limit = int(request.args.get("limit") or 100)
    items = paper_trading_repo.list_trade_signals(context.tenant_id, limit=limit)
    return success({"items": items, "total": len(items), "tenant_id": context.tenant_id})


@bp.get("/trading/paper/fills")
def paper_fills():
    context = get_authenticated_tenant_context()
    account_id = request.args.get("account_id")
    limit = int(request.args.get("limit") or 100)
    items = paper_trading_repo.list_fills(context.tenant_id, int(account_id) if account_id else None, limit=limit)
    return success({"items": items, "total": len(items), "tenant_id": context.tenant_id})


@bp.get("/trading/live/broker/status")
def live_broker_status():
    context = get_authenticated_tenant_context()
    require_role(context, "admin", "editor")
    return success(live_broker_service.broker_status())


@bp.post("/trading/live/orders")
def submit_live_order():
    context = get_authenticated_tenant_context()
    require_role(context, "admin")
    payload = request.get_json(silent=True) or {}
    result = live_broker_service.submit_order(context.tenant_id, payload)
    audit_log_service.record(
        context=context,
        action="live_broker.submit_order",
        resource_type="broker_order",
        resource_id=(result.get("audit") or {}).get("idempotency_key") or "",
        result=(result.get("audit") or {}).get("result") or result.get("status") or "unknown",
        detail=result.get("audit") or {},
    )
    return success(result)


@bp.post("/trading/live/reconcile")
def reconcile_live_orders():
    context = get_authenticated_tenant_context()
    require_role(context, "admin")
    payload = request.get_json(silent=True) or {}
    result = live_broker_service.reconcile_orders(context.tenant_id, payload)
    audit_log_service.record(
        context=context,
        action="live_broker.reconcile_orders",
        resource_type="broker_account",
        resource_id=(result.get("audit") or {}).get("account_id") or "",
        result=(result.get("audit") or {}).get("result") or result.get("status") or "unknown",
        detail=result.get("audit") or {},
    )
    return success(result)


@bp.post("/trading/live/orders/cancel")
def cancel_live_order():
    context = get_authenticated_tenant_context()
    require_role(context, "admin")
    payload = request.get_json(silent=True) or {}
    result = live_broker_service.cancel_order(context.tenant_id, payload)
    audit_log_service.record(
        context=context,
        action="live_broker.cancel_order",
        resource_type="broker_order",
        resource_id=(result.get("audit") or {}).get("idempotency_key") or "",
        result=(result.get("audit") or {}).get("result") or result.get("status") or "unknown",
        detail=result.get("audit") or {},
    )
    return success(result)


@bp.post("/trading/live/fills/callback")
def live_broker_fills_callback():
    context = get_authenticated_tenant_context()
    require_role(context, "admin")
    payload = request.get_json(silent=True) or {}
    result = live_broker_service.ingest_fills(context.tenant_id, payload)
    audit_log_service.record(
        context=context,
        action="live_broker.ingest_fills",
        resource_type="broker_fill",
        resource_id=str(result.get("persisted") or 0),
        result="success",
        detail={"received": result.get("received"), "persisted": result.get("persisted")},
    )
    return success(result)


@bp.get("/trading/live/fills")
def live_broker_fills():
    context = get_authenticated_tenant_context()
    require_role(context, "admin", "editor")
    payload = {"account_id": request.args.get("account_id") or "", "limit": request.args.get("limit") or 100}
    return success(live_broker_service.list_fills(context.tenant_id, payload))


@bp.post("/trading/paper/evaluate-exits")
def evaluate_paper_exits():
    context = get_authenticated_tenant_context()
    require_role(context, "admin", "editor")
    payload = request.get_json(silent=True) or {}
    account = service.ensure_default_account(context.tenant_id, payload)
    account_id = int(payload.get("account_id") or account["id"])
    result = service.evaluate_exits(context.tenant_id, account_id, payload)
    audit_log_service.record(
        context=context,
        action="paper_trading.evaluate_exits",
        resource_type="paper_account",
        resource_id=str(account_id),
        detail={"orders": len(result.get("orders") or []), "skipped": result.get("skipped") or []},
    )
    return success(result)


@bp.post("/trading/paper/accounts/<int:account_id>/reset")
def reset_paper_account(account_id: int):
    context = get_authenticated_tenant_context()
    require_role(context, "admin")
    count = paper_trading_repo.reset_account(context.tenant_id, account_id)
    if not count:
        raise NotFoundError("paper account not found")
    audit_log_service.record(
        context=context,
        action="paper_trading.reset",
        resource_type="paper_account",
        resource_id=str(account_id),
        detail={"account_id": account_id},
    )
    return success({"reset": True, "account_id": account_id})
