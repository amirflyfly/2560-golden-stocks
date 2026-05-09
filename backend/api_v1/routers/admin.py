"""Admin management API routes."""

from __future__ import annotations

from flask import Blueprint, request

from backend.application.admin_api_service import AdminApiService
from backend.application.audit_log_service import audit_log_service
from backend.application.launch_check_service import launch_check_service
from backend.core.responses import success
from backend.core.tenant_context import get_authenticated_tenant_context, require_role

bp = Blueprint("api_v1_admin", __name__)
service = AdminApiService()


def _require_admin_context():
    context = get_authenticated_tenant_context()
    require_role(context, "admin")
    return context


@bp.get("/admin/launch-check")
def admin_launch_check():
    _require_admin_context()
    return success(launch_check_service.run())


@bp.get("/admin/users")
def list_admin_users():
    _require_admin_context()
    return success(service.list_users())


@bp.get("/admin/audit-logs")
def list_admin_audit_logs():
    context = _require_admin_context()
    return success(
        audit_log_service.list_logs(
            tenant_id=context.tenant_id,
            limit=int(request.args.get("limit") or 50),
            action=request.args.get("action"),
            result=request.args.get("result"),
        )
    )


@bp.post("/admin/users")
def create_admin_user():
    context = _require_admin_context()
    payload = request.get_json(silent=True) or {}
    created = service.create_user(
        payload.get("username") or "",
        payload.get("password") or "",
        payload.get("role") or "editor",
        payload.get("tenant_id"),
    )
    audit_log_service.record(
        context=context,
        action="admin.user.create",
        resource_type="user",
        resource_id=created.get("id"),
        detail={"username": created.get("username"), "role": created.get("role"), "tenant_id": payload.get("tenant_id"), "password_set": bool(payload.get("password"))},
    )
    return success(created, status_code=201)


@bp.patch("/admin/users/<int:user_id>/password")
def reset_admin_user_password(user_id: int):
    context = _require_admin_context()
    payload = request.get_json(silent=True) or {}
    updated = service.reset_user_password(context.user_id or 0, user_id, payload.get("password") or "")
    audit_log_service.record(
        context=context,
        action="admin.user.password_reset",
        resource_type="user",
        resource_id=user_id,
        detail={"username": updated.get("username"), "password_set": bool(payload.get("password"))},
    )
    return success(updated)


@bp.post("/admin/users/<int:user_id>/tenants")
def bind_admin_user_tenant(user_id: int):
    context = _require_admin_context()
    payload = request.get_json(silent=True) or {}
    updated = service.bind_user_tenant(
        user_id,
        int(payload.get("tenant_id") or 0),
        payload.get("role") or "editor",
        bool(payload.get("is_default")),
    )
    audit_log_service.record(
        context=context,
        action="admin.user.bind_tenant",
        resource_type="user_tenant",
        resource_id=f"{user_id}:{payload.get('tenant_id')}",
        detail={"user_id": user_id, "tenant_id": payload.get("tenant_id"), "role": payload.get("role") or "editor", "is_default": bool(payload.get("is_default"))},
    )
    return success(updated)


@bp.delete("/admin/users/<int:user_id>/tenants/<int:tenant_id>")
def unbind_admin_user_tenant(user_id: int, tenant_id: int):
    context = _require_admin_context()
    updated = service.unbind_user_tenant(user_id, tenant_id)
    audit_log_service.record(
        context=context,
        action="admin.user.unbind_tenant",
        resource_type="user_tenant",
        resource_id=f"{user_id}:{tenant_id}",
        detail={"user_id": user_id, "tenant_id": tenant_id},
    )
    return success(updated)


@bp.patch("/admin/users/<int:user_id>/active")
def set_admin_user_active(user_id: int):
    context = _require_admin_context()
    payload = request.get_json(silent=True) or {}
    updated = service.set_user_active(context.user_id or 0, user_id, bool(payload.get("is_active")))
    audit_log_service.record(
        context=context,
        action="admin.user.set_active",
        resource_type="user",
        resource_id=user_id,
        detail={"username": updated.get("username"), "is_active": bool(payload.get("is_active"))},
    )
    return success(updated)


@bp.patch("/admin/users/<int:user_id>/role")
def set_admin_user_role(user_id: int):
    context = _require_admin_context()
    payload = request.get_json(silent=True) or {}
    updated = service.set_user_role(context.user_id or 0, user_id, payload.get("role") or "")
    audit_log_service.record(
        context=context,
        action="admin.user.set_role",
        resource_type="user",
        resource_id=user_id,
        detail={"username": updated.get("username"), "role": payload.get("role") or ""},
    )
    return success(updated)


@bp.get("/admin/tenants")
def list_admin_tenants():
    context = _require_admin_context()
    return success(service.list_tenants(context.tenant_id))


@bp.post("/admin/tenants")
def create_admin_tenant():
    context = _require_admin_context()
    payload = request.get_json(silent=True) or {}
    created = service.create_tenant(payload.get("code") or "", payload.get("name") or "", payload.get("plan") or "default")
    audit_log_service.record(
        context=context,
        action="admin.tenant.create",
        resource_type="tenant",
        resource_id=created.get("id"),
        detail={"code": created.get("code"), "name": created.get("name"), "plan": created.get("plan")},
    )
    return success(created, status_code=201)


@bp.patch("/admin/tenants/<int:tenant_id>")
def update_admin_tenant(tenant_id: int):
    context = _require_admin_context()
    payload = request.get_json(silent=True) or {}
    updated = service.update_tenant(tenant_id, payload)
    audit_log_service.record(
        context=context,
        action="admin.tenant.update",
        resource_type="tenant",
        resource_id=tenant_id,
        detail={"code": updated.get("code"), "name": updated.get("name"), "plan": updated.get("plan"), "status": updated.get("status")},
    )
    return success(updated)
