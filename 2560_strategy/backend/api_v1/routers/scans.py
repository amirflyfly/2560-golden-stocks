"""Scan API routes."""

from __future__ import annotations

from flask import Blueprint, request

from backend.application.audit_log_service import audit_log_service
from backend.application.pagination import normalize_pagination
from backend.application.scan_api_service import ScanApiService
from backend.core.errors import NotFoundError
from backend.core.responses import success
from backend.core.tenant_context import get_authenticated_tenant_context, require_role

bp = Blueprint("api_v1_scans", __name__)
service = ScanApiService()


@bp.post("/scans")
def create_scan():
    context = get_authenticated_tenant_context()
    require_role(context, "admin", "editor")
    payload = request.get_json(silent=True) or {}
    params = dict(payload.get("params") or {})
    for key in ("security_type", "target_security_type", "bar_interval", "interval", "adjust", "allow_t0"):
        if key in payload and key not in params:
            params[key] = payload.get(key)
    item = service.create_scan(
        tenant_id=context.tenant_id,
        strategy_code=payload.get("strategy_code"),
        params=params,
    )
    audit_log_service.record(
        context=context,
        action="scan.create",
        resource_type="scan_task",
        resource_id=item.get("task_id") or item.get("id"),
        detail={"strategy_code": item.get("strategy_code"), "params": item.get("params"), "market_data": item.get("market_data")},
    )
    return success(item, status_code=202)


@bp.get("/scans")
def list_scans():
    context = get_authenticated_tenant_context()
    pagination = normalize_pagination(request.args.get("page"), request.args.get("page_size"))
    return success(service.list_scans(context.tenant_id, pagination))


@bp.get("/scans/<scan_id>/results")
def get_scan_results(scan_id: str):
    context = get_authenticated_tenant_context()
    pagination = normalize_pagination(request.args.get("page"), request.args.get("page_size"))
    results = service.get_scan_results(context.tenant_id, scan_id, pagination)
    if results is None:
        raise NotFoundError("扫描任务不存在")
    return success(results)
