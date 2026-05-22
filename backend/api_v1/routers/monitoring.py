"""Production monitoring API routes."""

from __future__ import annotations

from flask import Blueprint, request

from backend.application.monitoring_service import MonitoringService
from backend.core.responses import success
from backend.core.tenant_context import get_authenticated_tenant_context, require_role

bp = Blueprint("api_v1_monitoring", __name__)
service = MonitoringService()


def _require_admin_context():
    context = get_authenticated_tenant_context()
    require_role(context, "admin")
    return context


@bp.get("/monitoring/overview")
def monitoring_overview():
    context = _require_admin_context()
    return success(service.overview(context.tenant_id))


@bp.get("/monitoring/metrics")
def monitoring_metrics():
    context = _require_admin_context()
    return success(service.metrics(context.tenant_id))


@bp.get("/monitoring/readiness")
def monitoring_readiness():
    _require_admin_context()
    return success(service.readiness())


@bp.get("/monitoring/logs")
def monitoring_logs():
    _require_admin_context()
    return success(service.logs(limit=request.args.get("limit", 50, type=int)))
