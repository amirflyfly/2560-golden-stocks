"""Paper trading API routes."""

from __future__ import annotations

import os
from datetime import datetime

from flask import Blueprint, request

from backend.application.audit_log_service import audit_log_service
from backend.application.live_broker_service import live_broker_service
from backend.application.paper_trading_service import PaperTradingService
from backend.application.strategy_api_service import StrategyApiService
from backend.application.sync_api_service import SyncApiService
from backend.core.errors import NotFoundError
from backend.core.responses import success
from backend.core.tenant_context import get_authenticated_tenant_context, require_role
from backend.repositories import market_data_repo, paper_trading_repo, strategy_repo

bp = Blueprint("api_v1_trading", __name__)
service = PaperTradingService()


def _bool_payload(value, default=False) -> bool:
    if value is None:
        return bool(default)
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _int_payload(value, default: int, *, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(default)
    number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _selected_strategy_ids(payload: dict) -> set[int]:
    raw = payload.get("strategy_ids")
    if raw in (None, ""):
        return set()
    if isinstance(raw, str):
        raw_items = [item.strip() for item in raw.split(",")]
    elif isinstance(raw, (list, tuple, set)):
        raw_items = list(raw)
    else:
        raw_items = [raw]
    selected = set()
    for item in raw_items:
        try:
            selected.add(int(item))
        except (TypeError, ValueError):
            continue
    return selected


def _strategy_run_summary(result: dict) -> dict:
    scan = result.get("scan") or {}
    paper = result.get("paper_trading") or {}
    exits = paper.get("exits") or {}
    orders = paper.get("orders") or []
    skipped = paper.get("skipped") or []
    blocked = paper.get("blocked") or []
    return {
        "production_status": result.get("production_status") or "unknown",
        "matched_count": int(scan.get("matched_count") or len((scan.get("items") or [])) or 0),
        "buy_orders": len(orders),
        "buy_skipped": len(skipped),
        "buy_blocked": len(blocked),
        "pre_buy_exit_orders": len(exits.get("orders") or []),
    }


def _run_complete_paper_loop(tenant_id: int, account_id: int, payload: dict) -> dict:
    source = str(payload.get("source") or "paper-closed-loop").strip()
    run_strategies = _bool_payload(payload.get("run_strategies"), True)
    sync_snapshots = _bool_payload(payload.get("sync_snapshots"), True)
    evaluate_exits = _bool_payload(payload.get("evaluate_exits"), True)
    max_strategies = _int_payload(payload.get("max_strategies") or os.getenv("PAPER_CLOSED_LOOP_MAX_STRATEGIES"), 4, minimum=0, maximum=50)
    selected_ids = _selected_strategy_ids(payload)
    strategy_params = dict(payload.get("strategy_params") or payload.get("params") or {})
    strategy_params.update({"paper_trade": True, "paper_account_id": account_id})

    strategy_rows = [
        item
        for item in strategy_repo.list_strategies(active_only=True)
        if bool(item.get("enabled")) and item.get("lifecycle_status") == "deployed"
    ]
    if selected_ids:
        strategy_rows = [item for item in strategy_rows if int(item.get("id") or 0) in selected_ids]
    if max_strategies:
        strategy_rows = strategy_rows[:max_strategies]

    strategy_service = StrategyApiService()
    strategy_runs = []
    totals = {
        "available": len(strategy_rows),
        "executed": 0,
        "failed": 0,
        "matched_count": 0,
        "buy_orders": 0,
        "buy_skipped": 0,
        "buy_blocked": 0,
        "pre_buy_exit_orders": 0,
    }
    if run_strategies:
        for row in strategy_rows:
            item = {
                "strategy_id": int(row.get("id") or 0),
                "strategy_code": row.get("code") or "",
                "strategy_name": row.get("name") or "",
            }
            try:
                result = strategy_service.run_deployed_strategy(tenant_id, int(row.get("id") or 0), strategy_params)
                summary = _strategy_run_summary(result)
                item.update({"status": "completed", "summary": summary, "warnings": result.get("warnings") or []})
                totals["executed"] += 1
                for key in ("matched_count", "buy_orders", "buy_skipped", "buy_blocked", "pre_buy_exit_orders"):
                    totals[key] += int(summary.get(key) or 0)
            except Exception as exc:
                item.update({"status": "failed", "error": str(exc)[:300], "summary": {}})
                totals["failed"] += 1
            strategy_runs.append(item)
    else:
        strategy_runs = [
            {
                "strategy_id": int(row.get("id") or 0),
                "strategy_code": row.get("code") or "",
                "strategy_name": row.get("name") or "",
                "status": "skipped",
                "summary": {},
            }
            for row in strategy_rows
        ]

    monitor_payload = {
        **payload,
        "account_id": account_id,
        "sync_snapshots": sync_snapshots,
        "evaluate_exits": evaluate_exits,
        "source": source,
    }
    monitor_result = SyncApiService().monitor_paper_positions(tenant_id, monitor_payload)
    status = "completed_with_errors" if totals["failed"] else "completed"
    return {
        "schema_version": "paper-complete-loop/v1",
        "status": status,
        "tenant_id": int(tenant_id or 0),
        "account_id": account_id,
        "source": source,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "run_strategies": run_strategies,
        "sync_snapshots": sync_snapshots,
        "evaluate_exits": evaluate_exits,
        "strategy_summary": totals,
        "strategy_runs": strategy_runs,
        "position_monitor": monitor_result,
        "progress": {"current": 3, "total": 3, "percent": 100},
    }


def _parse_dt(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None)


def _position_snapshot_fields(symbol: str) -> dict:
    snapshot = market_data_repo.get_latest_snapshot(symbol)
    if not snapshot:
        return {
            "latest_snapshot_time": "",
            "snapshot_trade_time": "",
            "snapshot_status": "missing",
            "snapshot_age_seconds": None,
            "snapshot_stale_seconds": int(os.getenv("PAPER_POSITION_SNAPSHOT_STALE_SECONDS", "30") or 30),
            "snapshot_source": "",
            "snapshot_last_price": None,
            "data_freshness": {"snapshot": {"status": "missing"}},
        }
    snapshot_time = snapshot.get("trade_time") or snapshot.get("updated_at") or ""
    snapshot_dt = _parse_dt(snapshot_time)
    age_seconds = int((datetime.now() - snapshot_dt).total_seconds()) if snapshot_dt else None
    if age_seconds is not None and age_seconds < 0:
        age_seconds = 0
    stale_seconds = int(os.getenv("PAPER_POSITION_SNAPSHOT_STALE_SECONDS", os.getenv("STRATEGY_SNAPSHOT_MAX_AGE_SECONDS", "30")) or 30)
    status = "realtime" if age_seconds is not None and age_seconds <= stale_seconds else "delayed"
    return {
        "latest_snapshot_time": snapshot_time,
        "snapshot_trade_time": snapshot_time,
        "snapshot_status": status,
        "snapshot_age_seconds": age_seconds,
        "snapshot_stale_seconds": stale_seconds,
        "snapshot_source": snapshot.get("source") or "",
        "snapshot_last_price": snapshot.get("last_price"),
        "data_freshness": {
            "snapshot": {
                "status": status,
                "latest_trade_time": snapshot_time,
                "age_seconds": age_seconds,
                "max_age_seconds": stale_seconds,
                "source": snapshot.get("source") or "",
            }
        },
    }


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
    enriched_items = []
    for item in items:
        enriched = {**item, **_position_snapshot_fields(str(item.get("symbol") or ""))}
        position_account_id = int(enriched.get("account_id") or account_id or 0)
        if position_account_id:
            try:
                exit_plan = service.exit_plan_for_position(context.tenant_id, position_account_id, enriched)
                enriched["exit_plan"] = exit_plan
                enriched["exit_rule"] = exit_plan
            except Exception:
                enriched["exit_plan"] = None
        enriched_items.append(enriched)
    items = enriched_items
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


@bp.get("/trading/signal-review-links")
def signal_review_links():
    context = get_authenticated_tenant_context()
    limit = int(request.args.get("limit") or 100)
    items = paper_trading_repo.list_signal_review_links(context.tenant_id, limit=limit)
    return success({"items": items, "total": len(items), "tenant_id": context.tenant_id, "health": paper_trading_repo.signal_review_health(context.tenant_id)})


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


@bp.post("/trading/paper/mark-to-market")
def mark_paper_to_market():
    context = get_authenticated_tenant_context()
    require_role(context, "admin", "editor")
    payload = request.get_json(silent=True) or {}
    account = service.ensure_default_account(context.tenant_id, payload)
    account_id = int(payload.get("account_id") or account["id"])
    result = service.mark_to_market(context.tenant_id, account_id, payload)
    audit_log_service.record(
        context=context,
        action="paper_trading.mark_to_market",
        resource_type="paper_account",
        resource_id=str(account_id),
        detail={"updated": result.get("updated"), "missing": result.get("missing") or [], "stale": result.get("stale") or []},
    )
    return success(result)


@bp.post("/trading/paper/monitor-positions")
def monitor_paper_positions():
    context = get_authenticated_tenant_context()
    require_role(context, "admin", "editor")
    payload = request.get_json(silent=True) or {}
    account = service.ensure_default_account(context.tenant_id, payload)
    payload = {**payload, "account_id": int(payload.get("account_id") or account["id"])}
    result = SyncApiService().monitor_paper_positions(context.tenant_id, payload)
    audit_log_service.record(
        context=context,
        action="paper_trading.monitor_positions",
        resource_type="paper_account",
        resource_id=str(payload["account_id"]),
        detail={
            "symbol_count": result.get("symbol_count"),
            "exit_summary": result.get("exit_summary") or {},
            "snapshot_sync": result.get("snapshot_sync") or {},
        },
    )
    return success(result)


@bp.post("/trading/paper/complete-loop")
def complete_paper_loop():
    context = get_authenticated_tenant_context()
    require_role(context, "admin", "editor")
    payload = request.get_json(silent=True) or {}
    account = service.ensure_default_account(context.tenant_id, payload)
    account_id = int(payload.get("account_id") or account["id"])
    result = _run_complete_paper_loop(context.tenant_id, account_id, payload)
    monitor_result = result.get("position_monitor") or {}
    audit_log_service.record(
        context=context,
        action="paper_trading.complete_loop",
        resource_type="paper_account",
        resource_id=str(account_id),
        detail={
            "strategy_summary": result.get("strategy_summary") or {},
            "symbol_count": monitor_result.get("symbol_count"),
            "exit_summary": monitor_result.get("exit_summary") or {},
            "snapshot_sync": monitor_result.get("snapshot_sync") or {},
        },
    )
    return success(result)


@bp.post("/trading/paper/apply-signal")
def apply_paper_signal():
    context = get_authenticated_tenant_context()
    require_role(context, "admin", "editor")
    payload = request.get_json(silent=True) or {}
    candidate = payload.get("candidate") or {}
    strategy_code = str(payload.get("strategy_code") or candidate.get("strategy_code") or "").strip()
    if not strategy_code:
        raise NotFoundError("strategy_code is required")
    strategy = strategy_repo.get_strategy_by_code(strategy_code)
    if not strategy:
        raise NotFoundError("strategy not found")
    params = dict(payload.get("params") or {})
    if payload.get("account_id"):
        params["paper_account_id"] = payload.get("account_id")
    if payload.get("cash_per_trade"):
        params["cash_per_trade"] = payload.get("cash_per_trade")
    if payload.get("max_paper_positions"):
        params["max_paper_positions"] = payload.get("max_paper_positions")
    if payload.get("min_signal_score") is not None:
        params["min_signal_score"] = payload.get("min_signal_score")
    if candidate.get("security_type") and not params.get("security_type"):
        params["security_type"] = candidate.get("security_type")
    if (candidate.get("bar_interval") or candidate.get("interval")) and not params.get("bar_interval"):
        params["bar_interval"] = candidate.get("bar_interval") or candidate.get("interval")
    scan = {"items": [candidate], "market_data": payload.get("market_data") or {}}
    source_context = payload.get("source_context") if isinstance(payload.get("source_context"), dict) else {}
    candidate["source_context"] = {
        **source_context,
        "scan_id": source_context.get("scan_id") or payload.get("scan_id"),
        "scan_task_id": source_context.get("scan_task_id") or payload.get("scan_task_id"),
        "scan_result_index": source_context.get("scan_result_index") if source_context.get("scan_result_index") is not None else payload.get("scan_result_index"),
        "scan_params": source_context.get("scan_params") or payload.get("scan_params") or {},
        "explanation": source_context.get("explanation") or payload.get("explanation") or {},
    }
    result = service.apply_strategy_scan(context.tenant_id, strategy, scan, params)
    account = result.get("account") or {}
    audit_log_service.record(
        context=context,
        action="paper_trading.apply_signal",
        resource_type="paper_account",
        resource_id=str(account.get("id") or params.get("paper_account_id") or ""),
        detail={
            "strategy_code": strategy_code,
            "symbol": candidate.get("symbol") or candidate.get("code"),
            "orders": len(result.get("orders") or []),
            "skipped": result.get("skipped") or [],
            "blocked": result.get("blocked") or [],
        },
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
