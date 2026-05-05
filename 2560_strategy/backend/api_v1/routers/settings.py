"""User UI settings API routes."""

from __future__ import annotations

from flask import Blueprint, request

from backend.application.alert_service import AlertEvaluationService
from backend.core.errors import AppError, NotFoundError
from backend.core.responses import success
from backend.core.tenant_context import get_authenticated_tenant_context, require_role
from backend.repositories import settings_repo

bp = Blueprint("api_v1_settings", __name__)
alert_service = AlertEvaluationService()


@bp.get("/settings/saved-views")
def list_saved_views():
    context = get_authenticated_tenant_context()
    return success(
        {
            "tenant_id": context.tenant_id,
            "user_id": context.user_id,
            "items": settings_repo.list_saved_views(context.tenant_id, context.user_id),
        }
    )


@bp.post("/settings/saved-views")
def create_saved_view():
    context = get_authenticated_tenant_context()
    require_role(context, "admin", "editor")
    payload = _require_payload()
    _require_name(payload)
    item = settings_repo.upsert_saved_view(context.tenant_id, context.user_id, payload)
    return success(item, status_code=201)


@bp.patch("/settings/saved-views/<view_id>")
def update_saved_view(view_id: str):
    context = get_authenticated_tenant_context()
    require_role(context, "admin", "editor")
    payload = _require_payload()
    _require_name(payload)
    payload["id"] = view_id
    item = settings_repo.upsert_saved_view(context.tenant_id, context.user_id, payload)
    return success(item)


@bp.delete("/settings/saved-views/<view_id>")
def delete_saved_view(view_id: str):
    context = get_authenticated_tenant_context()
    require_role(context, "admin", "editor")
    deleted = settings_repo.delete_saved_view(context.tenant_id, context.user_id, view_id)
    if not deleted:
        raise NotFoundError("saved view not found")
    return success({"deleted": deleted, "id": view_id})


@bp.get("/settings/alerts")
def list_alert_rules():
    context = get_authenticated_tenant_context()
    return success(
        {
            "tenant_id": context.tenant_id,
            "user_id": context.user_id,
            "items": settings_repo.list_alert_rules(context.tenant_id, context.user_id),
        }
    )


@bp.post("/settings/alerts")
def create_alert_rule():
    context = get_authenticated_tenant_context()
    require_role(context, "admin", "editor")
    payload = _require_payload()
    _require_name(payload)
    _require_alert_rule(payload)
    item = settings_repo.upsert_alert_rule(context.tenant_id, context.user_id, payload)
    return success(item, status_code=201)


@bp.patch("/settings/alerts/<alert_id>")
def update_alert_rule(alert_id: str):
    context = get_authenticated_tenant_context()
    require_role(context, "admin", "editor")
    payload = _require_payload()
    _require_name(payload)
    _require_alert_rule(payload)
    payload["id"] = alert_id
    item = settings_repo.upsert_alert_rule(context.tenant_id, context.user_id, payload)
    return success(item)


@bp.delete("/settings/alerts/<alert_id>")
def delete_alert_rule(alert_id: str):
    context = get_authenticated_tenant_context()
    require_role(context, "admin", "editor")
    deleted = settings_repo.delete_alert_rule(context.tenant_id, context.user_id, alert_id)
    if not deleted:
        raise NotFoundError("alert rule not found")
    return success({"deleted": deleted, "id": alert_id})


@bp.post("/settings/alerts/evaluate")
@bp.post("/settings/notifications/evaluate")
def evaluate_alert_rules_once():
    context = get_authenticated_tenant_context()
    payload = _require_payload()
    evaluate_all_users = _bool_value(payload.get("all_users"))
    if evaluate_all_users:
        require_role(context, "admin")
        result = alert_service.evaluate_all(
            tenant_id=context.tenant_id,
            limit_per_rule=_limit_per_rule(payload),
        )
    else:
        require_role(context, "admin", "editor")
        result = alert_service.evaluate_for_user(
            context.tenant_id,
            context.user_id,
            limit_per_rule=_limit_per_rule(payload),
        )
    return success(result)


@bp.get("/settings/notifications")
def list_notifications():
    context = get_authenticated_tenant_context()
    unread_only = _bool_value(request.args.get("unread_only"))
    limit = _safe_limit(request.args.get("limit"), default=50, maximum=200)
    items = settings_repo.list_notifications(
        context.tenant_id,
        context.user_id,
        unread_only=unread_only,
        limit=limit,
    )
    return success(
        {
            "tenant_id": context.tenant_id,
            "user_id": context.user_id,
            "items": items,
            "total": len(items),
            "unread_count": settings_repo.count_unread_notifications(context.tenant_id, context.user_id),
        }
    )


@bp.patch("/settings/notifications/<notification_id>")
@bp.patch("/settings/notifications/<notification_id>/read")
def mark_notification_read(notification_id: str):
    context = get_authenticated_tenant_context()
    payload = _require_payload()
    item = settings_repo.mark_notification_read(
        context.tenant_id,
        context.user_id,
        notification_id,
        read=_bool_value(payload.get("read", True)),
    )
    if item is None:
        raise NotFoundError("notification not found")
    return success(item)


def _require_payload() -> dict:
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        raise AppError("json object payload is required")
    return payload


def _require_name(payload: dict) -> None:
    if not str(payload.get("name") or payload.get("title") or "").strip():
        raise AppError("name is required")


def _require_alert_rule(payload: dict) -> None:
    if isinstance(payload.get("rule"), dict) and payload["rule"]:
        return
    if str(payload.get("target") or payload.get("symbol") or "").strip():
        return
    raise AppError("alert rule or target is required")


def _safe_limit(value, *, default: int, maximum: int) -> int:
    try:
        return max(1, min(int(value or default), maximum))
    except (TypeError, ValueError) as exc:
        raise AppError("invalid limit") from exc


def _limit_per_rule(payload: dict) -> int:
    return _safe_limit(payload.get("limit_per_rule"), default=50, maximum=200)


def _bool_value(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}
