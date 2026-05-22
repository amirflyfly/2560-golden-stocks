"""Production monitoring application service."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.core.config import effective_repository_backends, get_settings
from backend.db.session import get_engine, session_scope
from backend.application.live_broker_service import LiveBrokerService
from backend.application.task_api_service import task_lifecycle_status
from backend.infrastructure.cache.redis_client import cache_health
from backend.infrastructure.market_data.factory import create_fallback_market_data_provider
from backend.infrastructure.tasks.queue import list_tasks, mark_stale_tasks
from backend.repositories import paper_trading_repo

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
EXPECTED_ALEMBIC_REVISION = "0023_signal_review_links"


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

    def signal_review_health(self, tenant_id: int) -> dict:
        try:
            return paper_trading_repo.signal_review_health(tenant_id)
        except Exception as exc:
            return {
                "schema_version": "signal-review-health/v1",
                "tenant_id": int(tenant_id or 0),
                "status": "unavailable",
                "complete_rate": 0,
                "message": _safe_message(exc),
            }

    def live_broker_gate_health(self) -> dict:
        try:
            status = LiveBrokerService().broker_status()
            config = status.get("config") or {}
            validation = status.get("validation") or {}
            safe = config.get("launch_policy") == "disabled" and not validation.get("ready_for_live_orders")
            return {
                "ok": safe,
                "launch_policy": config.get("launch_policy"),
                "live_orders_open": bool(config.get("live_orders_open")),
                "summary": "live broker launch policy disabled" if safe else "live broker is not production safe",
            }
        except Exception as exc:
            return {"ok": False, "summary": _safe_message(exc)}

    def market_data_provider_gate_health(self) -> dict:
        settings = get_settings()
        provider = (settings.market_data_provider or "").strip().lower()
        raw_fallbacks = settings.market_data_fallbacks or ""
        if isinstance(raw_fallbacks, (list, tuple, set)):
            fallback_values = raw_fallbacks
        else:
            fallback_values = str(raw_fallbacks).split(",")
        fallbacks = [str(item).strip().lower() for item in fallback_values if str(item).strip()]
        health = self.market_data_health()
        ok = provider != "mock" and "mock" not in fallbacks and bool(health.get("ok"))
        return {
            "ok": ok,
            "provider": provider,
            "fallbacks": fallbacks,
            "health_ok": bool(health.get("ok")),
            "summary": "market data provider is production safe" if ok else "market data provider is not production safe",
        }

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
            "signal_review": self.signal_review_health(tenant_id),
        }

    def readiness(self) -> dict:
        settings = get_settings()
        tenant_id = int(os.getenv("WORKER_TENANT_ID", "1") or 1)
        database = self.database_health()
        cache = cache_health().to_dict()
        schema_revision = self.schema_revision_health()
        tasks = self.all_task_summary()
        live_broker_gate = self.live_broker_gate_health()
        market_data_provider = self.market_data_provider_gate_health()
        signal_review = self.signal_review_health(tenant_id)
        repository_backends = effective_repository_backends(settings.environment)
        production = (settings.environment or "").strip().lower() in {"prod", "production"}
        repositories_ok = not production or all(value == "mysql" for value in repository_backends.values())
        cache_ok = bool(cache.get("ok")) and (not production or cache.get("backend") == "redis")
        schema_ok = (not production) or bool(schema_revision.get("ok"))
        stale_tasks = tasks["by_lifecycle_status"].get("stale", 0)
        running_tasks = tasks["by_lifecycle_status"].get("running", 0) + tasks["by_lifecycle_status"].get("queued", 0)
        fail_on_stale_tasks = str(os.getenv("READINESS_FAIL_ON_STALE_TASKS", "0")).strip().lower() in {"1", "true", "yes"}
        task_health_ok = not production or not fail_on_stale_tasks or stale_tasks == 0
        task_queue_ok = not production or (settings.task_queue_backend == "redis" and settings.task_execution_mode == "worker")
        live_broker_ok = (not production) or bool(live_broker_gate.get("ok"))
        market_data_provider_ok = (not production) or bool(market_data_provider.get("ok"))
        signal_review_ok = (not production) or (signal_review.get("status") == "ok" and int(signal_review.get("incomplete") or 0) == 0)
        ready = bool(database.get("ok")) and cache_ok and repositories_ok and schema_ok and task_health_ok
        ready = ready and task_queue_ok and live_broker_ok and market_data_provider_ok and signal_review_ok
        return {
            "ready": ready,
            "environment": settings.environment,
            "tenant_id": tenant_id,
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
            "live_broker_gate": live_broker_gate,
            "market_data_provider": market_data_provider,
            "signal_review": signal_review,
            "checks": {
                "database": bool(database.get("ok")),
                "schema_revision": schema_ok,
                "cache": cache_ok,
                "task_queue": task_queue_ok,
                "tasks": task_health_ok,
                "repository_backends": repositories_ok,
                "live_broker_gate": live_broker_ok,
                "market_data_provider": market_data_provider_ok,
                "signal_review": signal_review_ok,
            },
        }

    def public_readiness(self) -> dict:
        detail = self.readiness()
        checks = detail.get("checks") or {}
        tasks = detail.get("tasks") or {}
        return {
            "ready": bool(detail.get("ready")),
            "environment": detail.get("environment"),
            "checks": {
                "database": bool(checks.get("database")),
                "cache": bool(checks.get("cache")),
                "task_queue": bool(checks.get("task_queue")),
                "tasks": bool(checks.get("tasks")),
                "schema_revision": bool(checks.get("schema_revision")),
            },
            "tasks": {
                "running_or_queued": int(tasks.get("running_or_queued") or 0),
                "failed": int(tasks.get("failed") or 0),
                "stale": int(tasks.get("stale") or 0),
            },
            "detail": "internal readiness details require admin access",
        }

    def metrics(self, tenant_id: int) -> dict:
        tasks = self.task_summary(tenant_id)
        status = tasks["by_status"]
        signal_review = self.signal_review_health(tenant_id)
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
            "signal_review_complete_rate": signal_review.get("complete_rate", 0),
            "signal_review_incomplete": signal_review.get("incomplete", 0),
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
