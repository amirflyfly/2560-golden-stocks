"""Authentication API routes for the React frontend."""

from __future__ import annotations

import os

from flask import Blueprint, request, session

from backend.core.errors import AppError, UnauthorizedError
from backend.core.responses import success
from backend.repositories import users_repo
from backend.services.multiuser_auth_service import DEFAULT_ADMIN_USERNAME
from backend.services.multiuser_auth_service import DEFAULT_ADMIN_PASSWORD
from backend.services.multiuser_auth_service import login as do_login
from backend.services.multiuser_auth_service import logout as do_logout
from backend.services.password_service import verify_password

bp = Blueprint("api_v1_auth", __name__)


def _is_production() -> bool:
    return any((os.getenv(name) or "").strip().lower() in {"prod", "production"} for name in ("APP_ENV", "FLASK_ENV"))


@bp.get("/auth/bootstrap")
def bootstrap_status():
    production = _is_production()
    has_users = bool(users_repo.has_any_users())
    init_username = os.getenv("ADMIN_INIT_USERNAME", "").strip()
    init_password = os.getenv("ADMIN_INIT_PASSWORD", "")
    init_configured = bool(init_username and init_password and init_password != DEFAULT_ADMIN_PASSWORD and len(init_password) >= 12)
    default_admin = users_repo.get_user_by_username(DEFAULT_ADMIN_USERNAME) if has_users else None
    dev_default_admin_available = (
        (not production)
        and bool(default_admin)
        and verify_password(DEFAULT_ADMIN_PASSWORD, default_admin.get("password_hash") or "")
    )
    return success(
        {
            "has_users": has_users,
            "production": production,
            "admin_initialized": has_users,
            "admin_init_required": not has_users,
            "admin_init_configured": init_configured if production else True,
            "dev_default_admin_available": dev_default_admin_available,
            "message": "admin user exists" if has_users else "admin initialization is required",
        }
    )


@bp.post("/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        raise AppError("json object payload is required")
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    auth_session = do_login(username, password)
    if not auth_session:
        raise UnauthorizedError("invalid username or password")

    session["auth_token"] = auth_session["session_token"]
    session.permanent = True
    tenants = users_repo.list_user_tenants(auth_session["user_id"])
    default_tenant = next((item for item in tenants if int(item.get("is_default") or 0) == 1), None)
    if default_tenant is None and tenants:
        default_tenant = tenants[0]
    tenant_id = int(default_tenant.get("tenant_id") or 1) if default_tenant else 1
    return success(
        {
            "user_id": auth_session["user_id"],
            "username": auth_session["username"],
            "role": auth_session["role"],
            "tenant_id": tenant_id,
            "tenants": tenants,
            "expires_at": auth_session["expires_at"],
        }
    )


@bp.post("/auth/logout")
def logout():
    token = session.get("auth_token")
    if token:
        do_logout(token)
    session.clear()
    return success({"logged_out": True})
