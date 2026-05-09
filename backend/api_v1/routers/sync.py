"""Market data synchronization API routes."""

from __future__ import annotations

from flask import Blueprint, request

from backend.application.audit_log_service import audit_log_service
from backend.application.pagination import normalize_pagination
from backend.application.sync_api_service import SyncApiService
from backend.core.responses import success
from backend.core.tenant_context import get_authenticated_tenant_context, require_role
from backend.repositories import market_data_repo

bp = Blueprint("api_v1_sync", __name__)
service = SyncApiService()


@bp.post("/market-data/sync")
def enqueue_market_data_sync():
    context = get_authenticated_tenant_context()
    require_role(context, "admin")
    payload = request.get_json(silent=True) or {}
    task = service.enqueue_market_data_sync(context.tenant_id, payload)
    audit_log_service.record(
        context=context,
        action="market.sync.create",
        resource_type="task",
        resource_id=task.get("id"),
        detail={"payload": payload, "task_name": task.get("name")},
    )
    return success(task, status_code=202)


@bp.post("/market-data/bootstrap")
def enqueue_market_data_bootstrap():
    context = get_authenticated_tenant_context()
    require_role(context, "admin")
    payload = request.get_json(silent=True) or {}
    payload = {
        **payload,
        "symbols": payload.get("symbols") or "all",
        "incremental": False,
        "bootstrap_days": int(payload.get("bootstrap_days") or 180),
        "batch_size": int(payload.get("batch_size") or 200),
    }
    task = service.enqueue_market_data_sync(context.tenant_id, payload)
    audit_log_service.record(
        context=context,
        action="market.bootstrap.create",
        resource_type="task",
        resource_id=task.get("id"),
        detail={"payload": payload, "task_name": task.get("name")},
    )
    return success(task, status_code=202)


@bp.get("/market-data/coverage")
def market_data_coverage():
    context = get_authenticated_tenant_context()
    require_role(context, "admin")
    pagination = normalize_pagination(request.args.get("page"), request.args.get("page_size"))
    return success(
        market_data_repo.list_coverage(
            keyword=request.args.get("keyword"),
            source=request.args.get("source"),
            security_type=request.args.get("security_type", "stock"),
            interval=request.args.get("interval"),
            adjust=request.args.get("adjust"),
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )


@bp.get("/market-data/limit-rules")
def market_data_limit_rules():
    context = get_authenticated_tenant_context()
    require_role(context, "admin")
    return success(
        {
            **market_data_repo.list_limit_rules(
                exchange=request.args.get("exchange"),
                board_type=request.args.get("board_type"),
                security_type=request.args.get("security_type"),
                risk_warning=(
                    request.args.get("risk_warning", "").strip().lower() in {"1", "true", "yes", "st"}
                    if request.args.get("risk_warning") is not None
                    else None
                ),
            ),
            "summary": market_data_repo.limit_rule_summary(),
        }
    )


@bp.get("/market-data/sync/state")
def market_data_sync_state():
    context = get_authenticated_tenant_context()
    require_role(context, "admin")
    pagination = normalize_pagination(request.args.get("page"), request.args.get("page_size"))
    return success(
        market_data_repo.list_sync_states(
            context.tenant_id,
            keyword=request.args.get("keyword"),
            source=request.args.get("source"),
            adjust=request.args.get("adjust"),
            interval=request.args.get("interval"),
            status=request.args.get("status"),
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )


@bp.get("/market-data/sync/runs")
def market_data_sync_runs():
    context = get_authenticated_tenant_context()
    require_role(context, "admin")
    pagination = normalize_pagination(request.args.get("page"), request.args.get("page_size"))
    return success(market_data_repo.list_sync_runs(context.tenant_id, page=pagination.page, page_size=pagination.page_size))


@bp.post("/market-data/snapshots/sync")
def enqueue_market_snapshot_sync():
    context = get_authenticated_tenant_context()
    require_role(context, "admin")
    payload = request.get_json(silent=True) or {}
    task = service.enqueue_quote_snapshot_sync(context.tenant_id, payload)
    audit_log_service.record(
        context=context,
        action="market.snapshot.create",
        resource_type="task",
        resource_id=task.get("id"),
        detail={"payload": payload, "task_name": task.get("name")},
    )
    return success(task, status_code=202)


@bp.post("/market-data/auction/sync")
def enqueue_market_auction_sync():
    context = get_authenticated_tenant_context()
    require_role(context, "admin")
    payload = request.get_json(silent=True) or {}
    task = service.enqueue_auction_snapshot_sync(context.tenant_id, payload)
    audit_log_service.record(
        context=context,
        action="market.auction.create",
        resource_type="task",
        resource_id=task.get("id"),
        detail={"payload": payload, "task_name": task.get("name")},
    )
    return success(task, status_code=202)


@bp.post("/market-data/indicators/precompute")
def enqueue_indicator_precompute():
    context = get_authenticated_tenant_context()
    require_role(context, "admin")
    payload = request.get_json(silent=True) or {}
    task = service.enqueue_indicator_precompute(context.tenant_id, payload)
    audit_log_service.record(
        context=context,
        action="market.indicators.precompute",
        resource_type="task",
        resource_id=task.get("id"),
        detail={"payload": payload, "task_name": task.get("name")},
    )
    return success(task, status_code=202)


@bp.post("/market-data/qfq/repair")
def enqueue_qfq_repair():
    context = get_authenticated_tenant_context()
    require_role(context, "admin")
    payload = request.get_json(silent=True) or {}
    task = service.enqueue_qfq_repair(context.tenant_id, payload)
    audit_log_service.record(
        context=context,
        action="market.qfq.repair",
        resource_type="task",
        resource_id=task.get("id"),
        detail={"payload": payload, "task_name": task.get("name")},
    )
    return success(task, status_code=202)


@bp.get("/market-data/snapshots")
def market_data_snapshots():
    context = get_authenticated_tenant_context()
    require_role(context, "admin")
    pagination = normalize_pagination(request.args.get("page"), request.args.get("page_size"))
    return success(
        market_data_repo.list_latest_snapshots(
            keyword=request.args.get("keyword"),
            source=request.args.get("source"),
            security_type=request.args.get("security_type"),
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )
