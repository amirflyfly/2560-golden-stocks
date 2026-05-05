"""Structured audit logging service for high-risk API operations."""

from __future__ import annotations

from typing import Any

from flask import request

from backend.core.tenant_context import TenantContext, get_authenticated_user
from backend.repositories import audit_logs_repo

SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "token",
    "auth_token",
    "csrf_token",
    "cookie",
    "cookies",
    "secret",
    "api_key",
}


class AuditLogService:
    def record(
        self,
        *,
        context: TenantContext | None,
        action: str,
        resource_type: str,
        resource_id: str | int | None = None,
        result: str = "success",
        detail: dict[str, Any] | None = None,
        username: str | None = None,
    ) -> None:
        user = get_authenticated_user(required=False) or {}
        safe_detail = self._sanitize(detail or {})
        audit_logs_repo.insert_audit_log(
            user_id=context.user_id if context else user.get("user_id"),
            username=username or user.get("username") or "",
            tenant_id=context.tenant_id if context else None,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id or ""),
            result=result,
            ip=self._client_ip(),
            user_agent=(request.headers.get("User-Agent") or "")[:300],
            detail=safe_detail,
        )

    def list_logs(
        self,
        *,
        tenant_id: int | None,
        limit: int = 50,
        action: str | None = None,
        result: str | None = None,
    ) -> dict:
        items = audit_logs_repo.list_audit_logs(
            tenant_id=tenant_id,
            limit=limit,
            action=(action or "").strip() or None,
            result=(result or "").strip() or None,
        )
        return {"items": items, "total": len(items), "filters": {"action": action or "", "result": result or ""}}

    def _client_ip(self) -> str:
        forwarded = request.headers.get("X-Forwarded-For") or ""
        if forwarded:
            return forwarded.split(",")[0].strip()[:80]
        return (request.remote_addr or "")[:80]

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, dict):
            safe = {}
            for key, item in value.items():
                if str(key).lower() in SENSITIVE_KEYS:
                    safe[key] = "***REDACTED***"
                else:
                    safe[key] = self._sanitize(item)
            return safe
        if isinstance(value, list):
            return [self._sanitize(item) for item in value]
        if isinstance(value, tuple):
            return [self._sanitize(item) for item in value]
        return value


audit_log_service = AuditLogService()
