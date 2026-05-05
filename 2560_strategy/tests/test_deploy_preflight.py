from __future__ import annotations

from scripts.deploy_preflight import _actual_env_checks, run_preflight


def test_deploy_preflight_reports_required_production_baseline():
    result = run_preflight()

    assert result["ok"] is True
    assert result["failed"] == 0
    names = {item["name"] for item in result["checks"]}
    for expected in {
        "compose:frontend-only-port",
        "dockerfile:gunicorn",
        "dockerfile:app-env-production",
        "dockerfile:healthcheck",
        "dockerignore:vendor-excluded",
        "nginx:api-proxy",
        "nginx:legacy-api-frozen",
        "nginx:security-headers",
        "requirements:mysql8-auth",
        "env:redis-cache-and-queue",
        "env:repository-backends-mysql",
        "compose:repository-backends-mysql",
        "compose:worker-service",
        "compose:worker-alert-scheduler",
        "compose:redis-task-queue",
        "env-file:init-sqlite-disabled",
        "env-file:database-url-not-sqlite",
        "env-file:cache-backend-redis",
        "env-file:task-queue-backend-redis",
        "env-file:task-execution-worker",
        "file:docs/refactor/BACKUP_RESTORE_RUNBOOK.md",
        "file:scripts/maintenance/mysql_restore_check.sh",
        "file:scripts/staging_mysql_migration.py",
        "file:scripts/production_evidence.py",
        "file:backend/infrastructure/tasks/handlers.py",
        "file:backend/infrastructure/tasks/worker.py",
        "file:docs/product/PRODUCTION_EVIDENCE.md",
        "file:docs/product/PRODUCTION_EVIDENCE.example.json",
        "git:critical-files-tracked",
    }:
        assert expected in names


def test_deploy_preflight_rejects_actual_env_sqlite_cutover_regression(tmp_path):
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "APP_ENV=production",
                "DATABASE_URL=sqlite:///data/picks.db",
                "INIT_SQLITE_SCHEMA=1",
                "MARKET_DATA_PROVIDER=mock",
                "MARKET_DATA_FALLBACKS=akshare,mock",
                "PICKS_REPOSITORY_BACKEND=sqlite",
            ]
        ),
        encoding="utf-8",
    )

    checks = _actual_env_checks(tmp_path)
    failed = {item["name"] for item in checks if not item["ok"]}

    assert "env-file:init-sqlite-disabled" in failed
    assert "env-file:database-url-not-sqlite" in failed
    assert "env-file:market-data-provider-not-mock" in failed
    assert "env-file:market-data-fallbacks-not-mock" in failed
    assert "env-file:repository-backends-not-sqlite" in failed


def test_deploy_preflight_reports_untracked_critical_runtime_files(tmp_path):
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (tmp_path / "app.py").write_text("", encoding="utf-8")

    result = run_preflight(tmp_path)
    failed = {item["name"]: item for item in result["checks"] if not item["ok"]}

    assert "git:critical-files-tracked" in failed
    assert "untracked critical files:" in failed["git:critical-files-tracked"]["detail"]


def test_production_deploy_runbook_documents_release_rollback_and_troubleshooting():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    runbook = (root / "docs" / "refactor" / "PRODUCTION_DEPLOY_RUNBOOK.md").read_text(encoding="utf-8")

    assert "发布前检查" in runbook
    assert "标准发布流程" in runbook
    assert "回滚流程" in runbook
    assert "故障排查顺序" in runbook
    assert "python scripts/deploy_preflight.py" in runbook
