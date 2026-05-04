"""Pick API routes."""

from __future__ import annotations

from flask import Blueprint, request

from backend.application.audit_log_service import audit_log_service
from backend.application.pagination import normalize_pagination
from backend.application.pick_api_service import PickApiService
from backend.core.errors import NotFoundError
from backend.core.responses import success
from backend.core.tenant_context import get_authenticated_tenant_context, require_role

bp = Blueprint("api_v1_picks", __name__)
service = PickApiService()


@bp.get("/picks")
def list_picks():
    context = get_authenticated_tenant_context()
    pagination = normalize_pagination(request.args.get("page"), request.args.get("page_size"))
    filters = {
        "status": request.args.get("status") or "",
        "strategy_code": request.args.get("strategy_code") or request.args.get("strategy") or "",
        "risk_level": request.args.get("risk_level") or request.args.get("risk") or "",
        "source": request.args.get("source") or "",
        "symbol": request.args.get("symbol") or request.args.get("code") or "",
        "from_date": request.args.get("from_date") or "",
        "to_date": request.args.get("to_date") or "",
    }
    return success(service.list_picks(context.tenant_id, pagination, filters))


@bp.post("/picks")
def create_pick():
    context = get_authenticated_tenant_context()
    require_role(context, "admin", "editor")
    payload = request.get_json(silent=True) or {}
    item = service.create_pick(context.tenant_id, payload)
    audit_log_service.record(
        context=context,
        action="pick.create",
        resource_type="pick",
        resource_id=item.get("id"),
        detail={
            "symbol": item.get("symbol"),
            "trade_date": item.get("trade_date"),
            "source": item.get("source"),
            "strategy_code": item.get("strategy_code"),
            "status": item.get("status"),
        },
    )
    return success(item, status_code=201)


@bp.get("/picks/<int:pick_id>")
def get_pick(pick_id: int):
    context = get_authenticated_tenant_context()
    item = service.get_pick(context.tenant_id, pick_id)
    if item is None:
        raise NotFoundError("pick not found")
    return success(item)


@bp.patch("/picks/<int:pick_id>/review")
def update_pick_review(pick_id: int):
    context = get_authenticated_tenant_context()
    require_role(context, "admin", "editor")
    payload = request.get_json(silent=True) or {}
    item = service.update_review(context.tenant_id, pick_id, payload)
    if item is None:
        raise NotFoundError("pick not found")
    audit_log_service.record(
        context=context,
        action="pick.review.update",
        resource_type="pick",
        resource_id=pick_id,
        detail={
            "symbol": item.get("symbol"),
            "status": item.get("status"),
            "deal_status": item.get("deal_status"),
            "risk_level": item.get("risk_level"),
            "return_pct": item.get("return_pct"),
            "max_return_pct": item.get("max_return_pct"),
            "drawdown_pct": item.get("drawdown_pct"),
            "holding_days": item.get("holding_days"),
        },
    )
    return success(item)


@bp.get("/picks/<int:pick_id>/timeline")
def get_pick_timeline(pick_id: int):
    context = get_authenticated_tenant_context()
    timeline = service.get_timeline(context.tenant_id, pick_id)
    if timeline is None:
        raise NotFoundError("pick not found")
    return success(timeline)
