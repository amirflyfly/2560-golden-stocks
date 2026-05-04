"""Market data synchronization API routes."""

from __future__ import annotations

from flask import Blueprint, request

from backend.application.audit_log_service import audit_log_service
from backend.application.sync_api_service import SyncApiService
from backend.core.responses import success
from backend.core.tenant_context import get_authenticated_tenant_context, require_role

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
