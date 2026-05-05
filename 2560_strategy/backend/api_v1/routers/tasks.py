"""Task status API routes."""

from __future__ import annotations

from flask import Blueprint, request

from backend.application.audit_log_service import audit_log_service
from backend.application.pagination import normalize_pagination
from backend.application.task_api_service import TaskApiService
from backend.core.errors import NotFoundError
from backend.core.responses import success
from backend.core.tenant_context import get_authenticated_tenant_context

bp = Blueprint("api_v1_tasks", __name__)
service = TaskApiService()


@bp.get("/tasks")
def list_background_tasks():
    context = get_authenticated_tenant_context()
    pagination = normalize_pagination(request.args.get("page"), request.args.get("page_size"))
    return success(
        service.list_tasks(
            context.tenant_id,
            pagination,
            name=request.args.get("name"),
            status=request.args.get("status"),
            sort=request.args.get("sort"),
            order=request.args.get("order"),
        )
    )


@bp.get("/tasks/<task_id>")
def get_background_task(task_id: str):
    context = get_authenticated_tenant_context()
    task = service.get_task(context.tenant_id, task_id)
    if not task:
        raise NotFoundError("任务不存在")
    return success(task)


@bp.post("/tasks/<task_id>/cancel")
def cancel_background_task(task_id: str):
    context = get_authenticated_tenant_context()
    task = service.cancel_task(context.tenant_id, task_id)
    if not task:
        raise NotFoundError("任务不存在")
    audit_log_service.record(
        context=context,
        action="task.cancel",
        resource_type="task",
        resource_id=task_id,
        detail={"name": task.get("name"), "status": task.get("status"), "error_summary": task.get("error_summary")},
    )
    return success(task)
