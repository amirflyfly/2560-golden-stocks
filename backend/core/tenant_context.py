"""Tenant context helpers for multi-tenant API requests."""

from __future__ import annotations

from dataclasses import dataclass

from flask import request, session

from backend.repositories import users_repo
from backend.services.multiuser_auth_service import get_session

from .errors import ForbiddenError, TenantRequiredError, UnauthorizedError


TENANT_HEADER = "X-Tenant-ID"


@dataclass(frozen=True)
class TenantContext:
    tenant_id: int
    user_id: int | None = None
    role: str | None = None


def get_tenant_id(required: bool = True) -> int | None:
    raw_value = request.headers.get(TENANT_HEADER)
    if not raw_value:
        if required:
            raise TenantRequiredError(f"missing {TENANT_HEADER}")
        return None
    try:
        tenant_id = int(raw_value)
    except ValueError as exc:
        raise TenantRequiredError(f"invalid {TENANT_HEADER}") from exc
    if tenant_id <= 0:
        raise TenantRequiredError(f"invalid {TENANT_HEADER}")
    return tenant_id


def get_request_user_id() -> int | None:
    raw_value = request.headers.get("X-User-ID")
    if raw_value is None or raw_value == "":
        return None
    try:
        user_id = int(raw_value)
    except ValueError as exc:
        raise TenantRequiredError("invalid X-User-ID") from exc
    if user_id <= 0:
        raise TenantRequiredError("invalid X-User-ID")
    return user_id


def get_authenticated_user(required: bool = True) -> dict | None:
    token = session.get("auth_token")
    auth_session = get_session(token) if token else None
    if auth_session:
        return {
            "user_id": int(auth_session["user_id"]),
            "username": auth_session.get("username"),
            "role": auth_session.get("role") or "editor",
        }
    if token:
        session.pop("auth_token", None)
    if required:
        raise UnauthorizedError("未登录")
    return None


def get_tenant_context(required: bool = True) -> TenantContext | None:
    tenant_id = get_tenant_id(required=required)
    if tenant_id is None:
        return None
    user_id = get_request_user_id()
    return TenantContext(tenant_id=tenant_id, user_id=user_id)


def get_authenticated_tenant_context(require_user: bool = True) -> TenantContext:
    context = get_tenant_context(required=True)
    auth_user = get_authenticated_user(required=require_user)
    if auth_user is None:
        return context
    if context.user_id is not None and context.user_id != auth_user["user_id"]:
        raise UnauthorizedError("X-User-ID does not match authenticated user")

    binding = users_repo.get_user_tenant_binding(auth_user["user_id"], context.tenant_id)
    if not binding:
        raise ForbiddenError("用户未绑定该租户")
    if binding.get("status") != "active":
        raise ForbiddenError("租户已停用")
    return TenantContext(
        tenant_id=context.tenant_id,
        user_id=auth_user["user_id"],
        role=binding.get("role") or auth_user["role"],
    )


def require_role(context: TenantContext, *roles: str) -> TenantContext:
    if not roles:
        return context
    if context.role not in roles:
        raise ForbiddenError("权限不足")
    return context
