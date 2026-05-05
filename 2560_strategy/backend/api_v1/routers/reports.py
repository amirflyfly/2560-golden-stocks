"""Research report API routes."""

from __future__ import annotations

from flask import Blueprint, Response, request

from backend.application.pagination import normalize_pagination
from backend.application.report_api_service import ReportApiService
from backend.core.responses import success
from backend.core.tenant_context import get_authenticated_tenant_context, require_role

bp = Blueprint("api_v1_reports", __name__)
service = ReportApiService()


@bp.get("/reports")
def list_reports():
    context = get_authenticated_tenant_context()
    pagination = normalize_pagination(request.args.get("page"), request.args.get("page_size"))
    return success(service.list_reports(context.tenant_id, pagination, symbol=request.args.get("symbol")))


@bp.post("/reports")
def create_report():
    context = get_authenticated_tenant_context()
    require_role(context, "admin", "editor")
    payload = request.get_json(silent=True) or {}
    return success(service.create_report(context.tenant_id, payload), status_code=201)


@bp.get("/reports/summary")
def get_report_summary():
    context = get_authenticated_tenant_context()
    return success(service.summary(context.tenant_id, period=request.args.get("period") or "week"))


@bp.get("/reports/summary/export")
def export_report_summary():
    context = get_authenticated_tenant_context()
    exported = service.export_summary(
        context.tenant_id,
        period=request.args.get("period") or "week",
        export_format=request.args.get("format") or "csv",
    )
    response = Response(exported["body"], mimetype=exported["content_type"])
    response.headers["Content-Disposition"] = f"attachment; filename={exported['filename']}"
    return response


@bp.get("/reports/<report_id>")
def get_report(report_id: str):
    context = get_authenticated_tenant_context()
    return success(service.get_report(context.tenant_id, report_id))
