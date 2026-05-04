"""Production monitoring application service."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.core.config import effective_repository_backends, get_settings
from backend.db.session import get_engine, session_scope
from backend.infrastructure.cache.redis_client import cache_health
from backend.infrastructure.market_data.factory import create_fallback_market_data_provider
from backend.infrastructure.tasks.queue import list_tasks, mark_stale_tasks

SENSITIVE_PATTERN = re.compile(
    r"(secret|password|token|authorization|cookie|database_url|redis_url|session)",
    re.IGNORECASE,
)
BASE_DIR = Path(__file__).resolve().parents[2]
LOG_CANDIDATES = [
    Path(os.getenv("APP_LOG_FILE")) if os.getenv("APP_LOG_FILE") else None,
    BASE_DIR / "logs" / "app.log",
    BASE_DIR / "data" / "app.log",
]
EXPECTED_ALEMBIC_REVISION = "0011_user_engagement_fields"


def _safe_message(value: Any) -> str:
    text_value = str(value or "")
    if SENSITIVE_PATTERN.search(text_value):
        return "[redacted]"
    return text_value[:500]


class MonitoringService:
    def database_health(self) -> dict:
        engine = get_engine()
        dialect = engine.dialect.name
        try:
            with session_scope() as session:
                session.execute(text("SELECT 1"))
            return {
                "backend": dialect,
                "dialect": dialect,
                "repository_backends": effective_repository_backends(get_settings().environment),
                "ok": True,
                "message": "ok",
            }
        except Exception as exc:
            return {
                "backend": dialect,
                "dialect": dialect,
                "repository_backends": effective_repository_backends(get_settings().environment),
                "ok": False,
                "message": _safe_message(exc),
            }

    def schema_revision_health(self) -> dict:
        try:
            with session_scope() as session:
                revision = session.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one()
            ok = revision == EXPECTED_ALEMBIC_REVISION
            return {
                "ok": ok,
                "revision": revision,
                "expected_revision": EXPECTED_ALEMBIC_REVISION,
                "message": "ok" if ok else "unexpected alembic revision",
            }
        except Exception as exc:
            return {
                "ok": False,
                "revision": None,
                "expected_revision": EXPECTED_ALEMBIC_REVISION,
                "message": _safe_message(exc),
            }

    def task_summary(self, tenant_id: int) -> dict:
        mark_stale_tasks()
        tasks = [task for task in list_tasks(limit=200) if task.get("tenant_id") == tenant_id]
        by_status: dict[str, int] = {}
        by_name: dict[str, int] = {}
        by_failure_category: dict[str, int] = {}
        for task in tasks:
            status = task.get("status") or "unknown"
            name = task.get("name") or "unknown"
            by_status[status] = by_status.get(status, 0) + 1
            by_name[name] = by_name.get(name, 0) + 1
            category = task.get("failure_category")
            if category:
                by_failure_category[category] = by_failure_category.get(category, 0) + 1
        return {
            "total": len(tasks),
            "by_status": by_status,
            "by_name": by_name,
            "by_failure_category": by_failure_category,
            "recent": tasks[:5],
        }

    def market_data_health(self) -> dict:
        try:
            return create_fallback_market_data_provider().health_check().to_dict()
        except Exception as exc:
            return {"provider": get_settings().market_data_provider, "ok": False, "message": _safe_message(exc)}

    def overview(self, tenant_id: int) -> dict:
        settings = get_settings()
        return {
            "app": settings.app_name,
            "environment": settings.environment,
            "log_level": settings.log_level,
            "tenant_id": tenant_id,
            "database": self.database_health(),
            "cache": cache_health().to_dict(),
            "market_data": self.market_data_health(),
            "tasks": self.task_summary(tenant_id),
        }

    def readiness(self) -> dict:
        settings = get_settings()
        database = self.database_health()
        cache = cache_health().to_dict()
        schema_revision = self.schema_revision_health()
        repository_backends = effective_repository_backends(settings.environment)
        production = (settings.environment or "").strip().lower() in {"prod", "production"}
        repositories_ok = not production or all(value == "mysql" for value in repository_backends.values())
        cache_ok = bool(cache.get("ok")) and (not production or cache.get("backend") == "redis")
        schema_ok = (not production) or bool(schema_revision.get("ok"))
        ready = bool(database.get("ok")) and cache_ok and repositories_ok and schema_ok
        return {
            "ready": ready,
            "environment": settings.environment,
            "database": database,
            "schema_revision": schema_revision,
            "cache": cache,
            "repository_backends": repository_backends,
            "checks": {
                "database": bool(database.get("ok")),
                "schema_revision": schema_ok,
                "cache": cache_ok,
                "repository_backends": repositories_ok,
            },
        }

    def metrics(self, tenant_id: int) -> dict:
        tasks = self.task_summary(tenant_id)
        status = tasks["by_status"]
        return {
            "tenant_id": tenant_id,
            "tasks_total": tasks["total"],
            "tasks_running": status.get("running", 0),
            "tasks_pending": status.get("pending", 0),
            "tasks_completed": status.get("completed", 0),
            "tasks_failed": status.get("failed", 0),
            "cache_ok": cache_health().ok,
            "database_ok": self.database_health()["ok"],
            "market_data_ok": bool(self.market_data_health().get("ok")),
        }

    def logs(self, limit: int = 50) -> dict:
        normalized_limit = max(1, min(int(limit or 50), 200))
        for candidate in LOG_CANDIDATES:
            if candidate and candidate.exists() and candidate.is_file():
                lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()[-normalized_limit:]
                return {
                    "source": candidate.relative_to(BASE_DIR).as_posix() if candidate.is_relative_to(BASE_DIR) else str(candidate),
                    "items": [_safe_message(line) for line in lines],
                    "total": len(lines),
                }
        return {
            "source": "unavailable",
            "items": [],
            "total": 0,
            "message": "no application log file configured",
        }
