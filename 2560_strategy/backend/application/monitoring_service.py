"""Production monitoring application service."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.core.config import effective_repository_backends, get_settings
from backend.db.session import get_engine, session_scope
from backend.application.task_api_service import task_lifecycle_status
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
EXPECTED_ALEMBIC_REVISION = "0022_stock_daily_bar_timestamps"


def _safe_message(value: Any) -> str:
    text_value = str(value or "")
    if SENSITIVE_PATTERN.search(text_value):
        return "[redacted]"
    return text_value[:500]


def _uses_sqlite_repositories(environment: str) -> bool:
    repository_backends = effective_repository_backends(environment)
    return bool(repository_backends) and all(backend == "sqlite" for backend in repository_backends.values())


class MonitoringService:
    def database_health(self) -> dict:
        settings = get_settings()
        repository_backends = effective_repository_backends(settings.environment)
        production = (settings.environment or "").strip().lower() in {"prod", "production"}
        if not production and _uses_sqlite_repositories(settings.environment):
            return self._sqlite_database_health(repository_backends)

        engine = get_engine()
        dialect = engine.dialect.name
        try:
            with session_scope() as session:
                session.execute(text("SELECT 1"))
            return {
                "backend": dialect,
                "dialect": dialect,
                "repository_backends": repository_backends,
                "ok": True,
                "message": "ok",
            }
        except Exception as exc:
            return {
                "backend": dialect,
                "dialect": dialect,
                "repository_backends": repository_backends,
                "ok": False,
                "message": _safe_message(exc),
            }

    def _sqlite_database_health(self, repository_backends: dict[str, str]) -> dict:
        from backend.repositories import db as sqlite_db

        try:
            conn = sqlite_db.db_conn()
            try:
                conn.execute("SELECT 1").fetchone()
            finally:
                conn.close()
            db_path = Path(sqlite_db.DB_PATH)
            return {
                "backend": "sqlite",
                "dialect": "sqlite",
                "repository_backends": repository_backends,
                "ok": True,
                "message": "ok",
                "path": db_path.relative_to(BASE_DIR).as_posix() if db_path.is_relative_to(BASE_DIR) else str(db_path),
            }
        except Exception as exc:
            return {
                "backend": "sqlite",
                "dialect": "sqlite",
                "repository_backends": repository_backends,
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
        return self._summarize_tasks(tasks)

    def all_task_summary(self) -> dict:
        mark_stale_tasks()
        return self._summarize_tasks(list_tasks(limit=200))

    def _summarize_tasks(self, tasks: list[dict]) -> dict:
        by_status: dict[str, int] = {}
        by_lifecycle_status: dict[str, int] = {}
        by_name: dict[str, int] = {}
        by_failure_category: dict[str, int] = {}
        for task in tasks:
            status = task.get("status") or "unknown"
            lifecycle_status = task_lifecycle_status(status)
            name = task.get("name") or "unknown"
            by_status[status] = by_status.get(status, 0) + 1
            by_lifecycle_status[lifecycle_status] = by_lifecycle_status.get(lifecycle_status, 0) + 1
            by_name[name] = by_name.get(name, 0) + 1
            category = task.get("failure_category")
            if category:
                by_failure_category[category] = by_failure_category.get(category, 0) + 1
        return {
            "total": len(tasks),
            "by_status": by_status,
            "by_lifecycle_status": by_lifecycle_status,
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
            "task_queue": {
                "backend": settings.task_queue_backend,
                "execution_mode": settings.task_execution_mode,
            },
            "market_data": self.market_data_health(),
            "tasks": self.task_summary(tenant_id),
        }

    def readiness(self) -> dict:
        settings = get_settings()
        database = self.database_health()
        cache = cache_health().to_dict()
        schema_revision = self.schema_revision_health()
        tasks = self.all_task_summary()
        repository_backends = effective_repository_backends(settings.environment)
        production = (settings.environment or "").strip().lower() in {"prod", "production"}
        repositories_ok = not production or all(value == "mysql" for value in repository_backends.values())
        cache_ok = bool(cache.get("ok")) and (not production or cache.get("backend") == "redis")
        schema_ok = (not production) or bool(schema_revision.get("ok"))
        stale_tasks = tasks["by_lifecycle_status"].get("stale", 0)
        running_tasks = tasks["by_lifecycle_status"].get("running", 0) + tasks["by_lifecycle_status"].get("queued", 0)
        task_health_ok = not production or stale_tasks == 0
        task_queue_ok = not production or (settings.task_queue_backend == "redis" and settings.task_execution_mode == "worker")
        ready = bool(database.get("ok")) and cache_ok and repositories_ok and schema_ok and task_health_ok
        ready = ready and task_queue_ok
        return {
            "ready": ready,
            "environment": settings.environment,
            "database": database,
            "schema_revision": schema_revision,
            "cache": cache,
            "task_queue": {
                "backend": settings.task_queue_backend,
                "execution_mode": settings.task_execution_mode,
            },
            "tasks": {
                "total": tasks["total"],
                "running_or_queued": running_tasks,
                "failed": tasks["by_lifecycle_status"].get("failed", 0),
                "stale": stale_tasks,
                "by_lifecycle_status": tasks["by_lifecycle_status"],
                "by_failure_category": tasks["by_failure_category"],
            },
            "repository_backends": repository_backends,
            "checks": {
                "database": bool(database.get("ok")),
                "schema_revision": schema_ok,
                "cache": cache_ok,
                "task_queue": task_queue_ok,
                "tasks": task_health_ok,
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
            "tasks_stale": status.get("stale", 0),
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
