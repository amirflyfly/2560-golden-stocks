from __future__ import annotations

from pathlib import Path
import importlib
import sys

import pytest

from backend.core.config import REPOSITORY_BACKEND_ENV_VARS, Settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_wsgi_application_entrypoint_imports(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("INIT_SQLITE_SCHEMA", "0")
    monkeypatch.setenv("ALLOW_MOCK_MARKET_DATA", "1")
    sys.modules.pop("app", None)

    module = importlib.import_module("app")

    assert hasattr(module, "app")
    assert "/api/v1/readiness" in {rule.rule for rule in module.app.url_map.iter_rules()}


def test_backend_dockerfile_uses_gunicorn_instead_of_flask_dev_server():
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "gunicorn" in dockerfile
    assert "app:app" in dockerfile
    assert "--bind 0.0.0.0:8765" in dockerfile
    assert "--workers ${WEB_WORKERS:-2}" in dockerfile
    assert "--threads ${WEB_THREADS:-4}" in dockerfile
    assert "--timeout ${WEB_TIMEOUT:-120}" in dockerfile
    assert "--access-logfile -" in dockerfile
    assert "--error-logfile -" in dockerfile
    assert "/api/v1/readiness" in dockerfile
    assert "ENV APP_ENV=production" in dockerfile
    assert 'CMD ["python", "app.py"]' not in dockerfile


def test_readiness_checks_alembic_schema_revision():
    monitoring_source = (PROJECT_ROOT / "backend" / "application" / "monitoring_service.py").read_text(encoding="utf-8")

    assert 'EXPECTED_ALEMBIC_REVISION = "0011_user_engagement_fields"' in monitoring_source
    assert "SELECT version_num FROM alembic_version LIMIT 1" in monitoring_source
    assert '"schema_revision": schema_ok' in monitoring_source


def test_backend_wsgi_tuning_is_exposed_in_compose_and_env_template():
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env_template = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    for key in ("WEB_WORKERS", "WEB_THREADS", "WEB_TIMEOUT", "WEB_GRACEFUL_TIMEOUT"):
        assert key in compose
        assert key in env_template

    assert "Docker uses gunicorn instead of Flask dev server" in env_template


def test_production_repository_backends_are_exposed_in_compose_and_env_template():
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env_template = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    for key in REPOSITORY_BACKEND_ENV_VARS:
        assert f"{key}=mysql" in env_template
        assert f"{key}: ${{{key}:-mysql}}" in compose


def test_production_rejects_sqlite_repository_backend(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_DEBUG", "0")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://strategy:strong-password@mysql:3306/strategy_2560")
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "mootdx")
    monkeypatch.setenv("MARKET_DATA_FALLBACKS", "akshare")
    monkeypatch.setenv("PICKS_REPOSITORY_BACKEND", "sqlite")

    with pytest.raises(RuntimeError, match="Production repository backends"):
        Settings.from_env()


def test_production_rejects_init_sqlite_schema(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_DEBUG", "0")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://strategy:strong-password@mysql:3306/strategy_2560")
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "mootdx")
    monkeypatch.setenv("MARKET_DATA_FALLBACKS", "akshare")
    monkeypatch.setenv("INIT_SQLITE_SCHEMA", "1")

    with pytest.raises(RuntimeError, match="INIT_SQLITE_SCHEMA"):
        Settings.from_env()


def test_production_health_contract_exposes_repository_backends(monkeypatch):
    from backend.core.config import effective_repository_backends

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PICKS_REPOSITORY_BACKEND", "auto")
    monkeypatch.setenv("AUTH_REPOSITORY_BACKEND", "mysql")

    backends = effective_repository_backends("production")

    assert backends["PICKS_REPOSITORY_BACKEND"] == "mysql"
    assert backends["AUTH_REPOSITORY_BACKEND"] == "mysql"


def test_production_compose_only_publishes_frontend_gateway_port():
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert '      - "5174:5174"' in compose
    assert '      - "3306:3306"' not in compose
    assert '      - "6379:6379"' not in compose
    assert '      - "8765:8765"' not in compose
    assert '      - "3306"' in compose
    assert '      - "6379"' in compose
    assert '      - "8765"' in compose


def test_legacy_start_scripts_refuse_production_mode():
    start_flask = (PROJECT_ROOT / "start_flask.sh").read_text(encoding="utf-8", errors="ignore")
    start_docker = (PROJECT_ROOT / "start.sh").read_text(encoding="utf-8", errors="ignore")

    assert "legacy SQLite/dev entrypoint" in start_flask
    assert "Use docker compose for production" in start_flask
    assert "legacy docker-run helper without MySQL wiring" in start_docker
    assert "Use docker compose for production" in start_docker


def test_legacy_sqlite_maintenance_scripts_refuse_production():
    guarded_files = [
        PROJECT_ROOT / "scheduler.py",
        PROJECT_ROOT / "web_panel.py",
        PROJECT_ROOT / "add_pick.py",
        PROJECT_ROOT / "report_2560.py",
        PROJECT_ROOT / "run_2560_backtest.py",
        PROJECT_ROOT / "strategy_2560.py",
        PROJECT_ROOT / "strategy_lite.py",
        PROJECT_ROOT / "ui_demo.py",
        PROJECT_ROOT / "first_limit_replay.py",
        PROJECT_ROOT / "first_limit_validate.py",
        PROJECT_ROOT / "content_analytics.py",
        PROJECT_ROOT / "daily_review_brief.py",
        PROJECT_ROOT / "leaderboards.py",
        PROJECT_ROOT / "master_ledger.py",
        PROJECT_ROOT / "review_metrics.py",
        PROJECT_ROOT / "strategy_digest.py",
        PROJECT_ROOT / "scripts" / "maintenance" / "build_dashboard_html.py",
        PROJECT_ROOT / "scripts" / "maintenance" / "bulk_update_reviews.py",
        PROJECT_ROOT / "scripts" / "maintenance" / "ensure_extended_schema.py",
        PROJECT_ROOT / "scripts" / "maintenance" / "import_picks_csv.py",
        PROJECT_ROOT / "scripts" / "maintenance" / "ingest_daily_picks.py",
        PROJECT_ROOT / "scripts" / "maintenance" / "init_tracker_db.py",
    ]

    for path in guarded_files:
        source = path.read_text(encoding="utf-8", errors="ignore")
        assert "refuse_production" in source


def test_legacy_sqlite_guard_treats_flask_env_production_as_production():
    guard_source = (PROJECT_ROOT / "scripts" / "maintenance" / "legacy_sqlite_guard.py").read_text(encoding="utf-8")

    assert "FLASK_ENV" in guard_source
    assert "APP_ENV" in guard_source


def test_frontend_nginx_proxies_api_to_internal_backend_service():
    nginx_conf = (PROJECT_ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")

    assert "proxy_pass http://backend:8765/api/v1/;" in nginx_conf
    assert "location /api/" in nginx_conf
    assert "return 410" in nginx_conf
    assert "proxy_pass http://backend:8765/dist/;" in nginx_conf


def test_docker_context_excludes_vendor_and_tool_skill_caches():
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "vendor/" in dockerignore
    for path in (".aionrs/", ".claude/", ".gemini/", ".opencode/skills/"):
        assert path in gitignore


def test_ci_workflow_covers_tests_build_compose_and_images():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "python -m pytest" in workflow
    assert "npm ci" in workflow
    assert "npm run build" in workflow
    assert "npx playwright install --with-deps chromium" in workflow
    assert "npm run test:e2e" in workflow
    assert "docker compose config --quiet" in workflow
    assert "docker build -t 2560-strategy-backend:ci ." in workflow
    assert "docker build -t 2560-strategy-frontend:ci ./frontend" in workflow
    assert "http://localhost:5174/api/v1/readiness" in workflow
    assert "-X POST http://localhost:5174/api/picks" in workflow
    assert 'test "$legacy_status" = "410"' in workflow
    assert "ALLOW_MOCK_MARKET_DATA: '1'" in workflow
    assert "MARKET_DATA_FALLBACKS=akshare" in workflow


def test_https_hsts_topology_uses_external_tls_gateway():
    security_plan = (PROJECT_ROOT / "docs" / "refactor" / "SECURITY_PLAN.md").read_text(encoding="utf-8")
    nginx_conf = (PROJECT_ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env_template = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "外部网关终止 TLS" in security_plan
    assert "容器 nginx 终止 TLS" in security_plan
    assert "Strict-Transport-Security" in security_plan
    assert "X-Forwarded-Proto=https" in security_plan
    assert "Strict-Transport-Security" in nginx_conf
    assert "listen 443" not in nginx_conf
    assert "ssl_certificate" not in nginx_conf
    assert '      - "443:443"' not in compose
    assert "HTTPS is terminated by an external gateway" in env_template


def test_production_app_boot_does_not_initialize_sqlite_schema_by_default():
    app_source = (PROJECT_ROOT / "backend" / "__init__.py").read_text(encoding="utf-8")

    assert "def _should_initialize_sqlite_schema(settings)" in app_source
    assert "return False" in app_source
    assert "INIT_SQLITE_SCHEMA" in app_source
