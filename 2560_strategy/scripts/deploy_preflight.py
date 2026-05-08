"""Read-only production deployment preflight checks.

This script does not start, stop, move, rename, or delete anything. It only reads
project files and reports whether the production deployment baseline is present.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    ".env.example",
    "docker-compose.yml",
    "Dockerfile",
    "frontend/Dockerfile",
    "frontend/nginx.conf",
    "scripts/backup_restore_drill.py",
    "scripts/maintenance/mysql_restore_check.sh",
    "scripts/bootstrap_mysql_seed.py",
    "scripts/staging_mysql_migration.py",
    "scripts/production_evidence.py",
    "backend/infrastructure/tasks/handlers.py",
    "backend/infrastructure/tasks/worker.py",
    "scripts/validate_mysql_schema.py",
    "docs/refactor/BACKUP_RESTORE_RUNBOOK.md",
    "docs/product/PRODUCTION_EVIDENCE.md",
    "docs/product/PRODUCTION_EVIDENCE.example.json",
]

CRITICAL_TRACKED_FILES = [
    ".github/workflows/ci.yml",
    ".dockerignore",
    ".gitignore",
    ".env.example",
    "alembic.ini",
    "alembic/env.py",
    "alembic/versions/0001_initial_mysql_schema.py",
    "alembic/versions/0011_user_engagement_fields.py",
    "docker-compose.yml",
    "frontend/Dockerfile",
    "frontend/nginx.conf",
    "frontend/package.json",
    "frontend/src/main.jsx",
    "frontend/src/app/App.jsx",
    "backend/api_v1/blueprint.py",
    "backend/api_v1/register.py",
    "backend/api_v1/routers/picks.py",
    "backend/api_v1/routers/scans.py",
    "backend/api_v1/routers/reports.py",
    "backend/api_v1/routers/monitoring.py",
    "backend/application/pick_api_service.py",
    "backend/application/scan_api_service.py",
    "backend/application/report_api_service.py",
    "backend/application/monitoring_service.py",
    "backend/core/config.py",
    "backend/core/responses.py",
    "backend/core/errors.py",
    "backend/db/session.py",
    "backend/db/tenant_repository.py",
    "backend/db/models/tenant.py",
    "backend/db/models/strategy.py",
    "backend/infrastructure/cache/redis_client.py",
    "backend/infrastructure/market_data/factory.py",
    "backend/infrastructure/market_data/provider.py",
    "backend/infrastructure/tasks/queue.py",
    "backend/repositories/audit_logs_repo.py",
    "backend/services/research_service.py",
    "scripts/deploy_preflight.py",
    "scripts/production_evidence.py",
    "scripts/check_repo_hygiene.py",
    "scripts/clean_repo_index.py",
    "scripts/validate_mysql_schema.py",
    "scripts/maintenance/legacy_sqlite_guard.py",
    "tests/test_api_v1.py",
    "tests/test_deployment_config.py",
    "tests/test_deploy_preflight.py",
    "tests/test_repo_hygiene.py",
    "tests/test_schema_alignment.py",
    "tests/test_tenant_repository.py",
    "docs/refactor/BACKUP_RESTORE_RUNBOOK.md",
    "docs/refactor/PRODUCTION_DEPLOY_RUNBOOK.md",
    "docs/product/P6_READ_WRITE_CUTOVER.md",
    "docs/product/PRODUCTION_EVIDENCE.md",
    "docs/product/PRODUCTION_EVIDENCE.example.json",
]

REPOSITORY_BACKEND_ENV_VARS = [
    "PICKS_REPOSITORY_BACKEND",
    "AUTH_REPOSITORY_BACKEND",
    "AUDIT_REPOSITORY_BACKEND",
    "SETTINGS_REPOSITORY_BACKEND",
    "LOGS_REPOSITORY_BACKEND",
    "STRATEGY_POOL_REPOSITORY_BACKEND",
    "STRATEGY_REPOSITORY_BACKEND",
]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _run_git(args: list[str], cwd: Path) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()]


def _critical_tracked_checks(root: Path) -> list[dict[str, Any]]:
    git_root_lines = _run_git(["rev-parse", "--show-toplevel"], root)
    if not git_root_lines:
        return [_check("git:critical-files-tracked", True, "not a git checkout; skipping index audit")]

    git_root = Path(git_root_lines[0]).resolve()
    tracked = set(_run_git(["ls-files", "--", str(root)], git_root))
    missing = []
    for relative_path in CRITICAL_TRACKED_FILES:
        absolute = (root / relative_path).resolve()
        try:
            git_path = absolute.relative_to(git_root).as_posix()
        except ValueError:
            git_path = relative_path
        if git_path not in tracked:
            missing.append(relative_path)

    detail = "all critical runtime files are tracked"
    if missing:
        detail = "untracked critical files: " + ", ".join(missing[:10])
        if len(missing) > 10:
            detail += f", ... {len(missing) - 10} more"
    return [_check("git:critical-files-tracked", not missing, detail)]


def _repository_backends_are_mysql(text: str, *, compose: bool = False) -> bool:
    if compose:
        return all(f"{name}: ${{{name}:-mysql}}" in text for name in REPOSITORY_BACKEND_ENV_VARS)
    return all(f"{name}=mysql" in text for name in REPOSITORY_BACKEND_ENV_VARS)


def _parse_env_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _actual_env_checks(root: Path) -> list[dict[str, Any]]:
    env_path = root / ".env"
    if not env_path.exists():
        return [_check("env-file:optional", True, ".env not present; template checks apply")]
    env = _parse_env_text(_read_text(env_path))
    database_url = env.get("DATABASE_URL", "")
    parsed = urlparse(database_url)
    market_data_provider = env.get("MARKET_DATA_PROVIDER", "").strip().lower()
    market_data_fallbacks = {
        item.strip().lower()
        for item in env.get("MARKET_DATA_FALLBACKS", "").split(",")
        if item.strip()
    }
    cache_backend = env.get("CACHE_BACKEND", "redis").strip().lower()
    task_queue_backend = env.get("TASK_QUEUE_BACKEND", "redis").strip().lower()
    task_execution_mode = env.get("TASK_EXECUTION_MODE", "worker").strip().lower()
    backend_values = {
        name: env.get(name, "mysql").strip().lower()
        for name in REPOSITORY_BACKEND_ENV_VARS
    }
    return [
        _check("env-file:app-env-production", env.get("APP_ENV", "").strip().lower() in {"prod", "production"}, ".env APP_ENV is production"),
        _check("env-file:init-sqlite-disabled", env.get("INIT_SQLITE_SCHEMA", "").strip().lower() not in {"1", "true", "yes"}, "INIT_SQLITE_SCHEMA is not enabled"),
        _check("env-file:database-url-not-sqlite", not database_url or not parsed.scheme.startswith("sqlite"), "DATABASE_URL is not sqlite"),
        _check("env-file:market-data-provider-not-mock", market_data_provider != "mock", "MARKET_DATA_PROVIDER is not mock"),
        _check("env-file:market-data-fallbacks-not-mock", "mock" not in market_data_fallbacks, "MARKET_DATA_FALLBACKS does not include mock"),
        _check("env-file:cache-backend-redis", cache_backend == "redis", "CACHE_BACKEND is redis"),
        _check("env-file:task-queue-backend-redis", task_queue_backend == "redis", "TASK_QUEUE_BACKEND is redis"),
        _check("env-file:task-execution-worker", task_execution_mode == "worker", "TASK_EXECUTION_MODE is worker"),
        _check(
            "env-file:repository-backends-not-sqlite",
            all(value in {"", "auto", "mysql"} for value in backend_values.values()),
            "actual .env repository backends are mysql/auto",
        ),
    ]


def run_preflight(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or PROJECT_ROOT
    compose = _read_text(root / "docker-compose.yml")
    dockerfile = _read_text(root / "Dockerfile")
    nginx = _read_text(root / "frontend" / "nginx.conf")
    dockerignore = _read_text(root / ".dockerignore")
    env_template = _read_text(root / ".env.example")
    requirements = _read_text(root / "requirements.txt")

    file_checks = [_check(f"file:{name}", (root / name).exists(), name) for name in REQUIRED_FILES]
    checks = [
        *file_checks,
        _check("env:secret-key-required", "SECRET_KEY" in env_template and "Do not use admin/admin123 in production" in env_template, "production secret template"),
        _check("compose:frontend-only-port", '"5174:5174"' in compose and '"8765:8765"' not in compose and '"3306:3306"' not in compose and '"6379:6379"' not in compose, "only frontend gateway is published"),
        _check("compose:health-dependencies", "condition: service_healthy" in compose, "backend/frontend wait for healthy dependencies"),
        _check("dockerfile:gunicorn", "gunicorn" in dockerfile and "app:app" in dockerfile and "--bind 0.0.0.0:8765" in dockerfile, "backend uses production WSGI"),
        _check("dockerfile:app-env-production", "ENV APP_ENV=production" in dockerfile, "backend image defaults to production app environment"),
        _check("dockerfile:healthcheck", "/api/v1/readiness" in dockerfile and "HEALTHCHECK" in dockerfile, "backend readiness healthcheck is configured"),
        _check("dockerignore:vendor-excluded", "vendor/" in dockerignore, "vendor directory is excluded from production image context"),
        _check("requirements:mysql8-auth", "PyMySQL" in requirements and "cryptography" in requirements, "PyMySQL can authenticate against MySQL 8 caching_sha2_password"),
        _check("env:redis-cache-and-queue", all(item in env_template for item in ["CACHE_BACKEND=redis", "TASK_QUEUE_BACKEND=redis", "TASK_EXECUTION_MODE=worker", "ALERT_EVALUATION_INTERVAL_SECONDS=300"]), "production template pins Redis queue, worker mode, and alert cadence"),
        _check("env:repository-backends-mysql", _repository_backends_are_mysql(env_template), "production template pins repositories to MySQL"),
        _check("compose:repository-backends-mysql", _repository_backends_are_mysql(compose, compose=True), "production compose defaults repositories to MySQL"),
        _check("compose:worker-service", "\n  worker:" in compose and "python -m backend.infrastructure.tasks.worker" in compose, "standalone worker service is configured"),
        _check("compose:worker-alert-scheduler", "--alert-interval-seconds ${ALERT_EVALUATION_INTERVAL_SECONDS:-300}" in compose, "worker schedules background alert evaluation"),
        _check("compose:redis-task-queue", all(item in compose for item in ["CACHE_BACKEND: ${CACHE_BACKEND:-redis}", "TASK_QUEUE_BACKEND: ${TASK_QUEUE_BACKEND:-redis}", "TASK_EXECUTION_MODE: ${TASK_EXECUTION_MODE:-worker}"]), "compose pins Redis task queue and worker mode"),
        _check("nginx:api-proxy", "proxy_pass http://backend:8765/api/v1/;" in nginx, "frontend proxies v1 API internally"),
        _check("nginx:legacy-api-frozen", "location /api/" in nginx and "return 410" in nginx, "frontend freezes legacy API prefix"),
        _check("nginx:security-headers", all(header in nginx for header in ["Content-Security-Policy", "X-Frame-Options", "X-Content-Type-Options", "Strict-Transport-Security"]), "security headers are present"),
        _check("data:directory", (root / "data").exists(), "data directory exists"),
        _check("backups:directory", (root / "backups").exists(), "backup directory exists"),
        *_critical_tracked_checks(root),
        *_actual_env_checks(root),
    ]
    failed = [item for item in checks if not item["ok"]]
    return {
        "ok": not failed,
        "total": len(checks),
        "failed": len(failed),
        "checks": checks,
        "summary": "preflight passed" if not failed else f"preflight failed: {len(failed)} checks",
    }


def main() -> int:
    result = run_preflight()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
