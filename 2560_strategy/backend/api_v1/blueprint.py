"""Flask blueprint for the v1 API."""

from __future__ import annotations

from flask import Blueprint

from backend.core.config import effective_repository_backends, get_settings
from backend.application.monitoring_service import MonitoringService
from backend.core.responses import error, success
from backend.core.tenant_context import get_authenticated_tenant_context
from backend.infrastructure.market_data.factory import create_fallback_market_data_provider

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")
monitoring_service = MonitoringService()

from backend.api_v1.routers.admin import bp as admin_bp
from backend.api_v1.routers.market import bp as market_bp
from backend.api_v1.routers.monitoring import bp as monitoring_bp
from backend.api_v1.routers.picks import bp as picks_bp
from backend.api_v1.routers.reports import bp as reports_bp
from backend.api_v1.routers.scans import bp as scans_bp
from backend.api_v1.routers.strategies import bp as strategies_bp
from backend.api_v1.routers.sync import bp as sync_bp
from backend.api_v1.routers.tasks import bp as tasks_bp

api_v1_bp.register_blueprint(strategies_bp)
api_v1_bp.register_blueprint(scans_bp)
api_v1_bp.register_blueprint(picks_bp)
api_v1_bp.register_blueprint(reports_bp)
api_v1_bp.register_blueprint(market_bp)
api_v1_bp.register_blueprint(tasks_bp)
api_v1_bp.register_blueprint(sync_bp)
api_v1_bp.register_blueprint(monitoring_bp)
api_v1_bp.register_blueprint(admin_bp)


@api_v1_bp.get("/health")
def health_check():
    settings = get_settings()
    return success(
        {
            "status": "ok",
            "app": settings.app_name,
            "environment": settings.environment,
            "market_data_provider": settings.market_data_provider,
            "database_dialect": settings.database_url.split(":", 1)[0],
            "repository_backends": effective_repository_backends(settings.environment),
        }
    )


@api_v1_bp.get("/readiness")
def readiness_check():
    data = monitoring_service.readiness()
    if data["ready"]:
        return success(data)
    return error("not ready", code=503, status_code=503, data=data)


@api_v1_bp.get("/market-data/health")
def market_data_health_check():
    provider = create_fallback_market_data_provider()
    result = provider.health_check()
    return success(result.to_dict())


@api_v1_bp.get("/me")
def current_user_profile():
    context = get_authenticated_tenant_context()
    return success(
        {
            "tenant_id": context.tenant_id,
            "user_id": context.user_id,
            "role": context.role or "viewer",
            "permissions": {
                "can_read": True,
                "can_write": context.role in {"admin", "editor"},
                "can_admin": context.role == "admin",
            },
        }
    )
