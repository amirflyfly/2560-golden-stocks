from __future__ import annotations

from pathlib import Path

from scripts.clean_repo_index import build_cleanup_plan
from scripts.check_repo_hygiene import find_hygiene_violations, is_forbidden_path


def test_repo_hygiene_flags_generated_paths():
    assert is_forbidden_path(".env")
    assert is_forbidden_path("./.env")
    assert is_forbidden_path(".pytest_cache/v/cache/nodeids")
    assert is_forbidden_path("node_modules/vite/package.json")
    assert is_forbidden_path("backend/__pycache__/app.cpython-312.pyc")
    assert is_forbidden_path("data/cache/stock_list_akshare.pkl")
    assert is_forbidden_path("data/picks.db")
    assert is_forbidden_path("logs/app.log")
    assert not is_forbidden_path("backend/application/pick_api_service.py")
    assert not is_forbidden_path("frontend/src/pages/ScansPage.jsx")


def test_repo_hygiene_report_is_read_only_and_structured():
    result = find_hygiene_violations(
        paths=[
            "2560_strategy/backend/application/pick_api_service.py",
            "2560_strategy/node_modules/vite/package.json",
            "2560_strategy/data/cache/example.pkl",
        ]
    )

    assert result["ok"] is False
    assert result["violation_count"] == 2
    assert "node_modules/vite/package.json" in result["violations"]
    assert "data/cache/example.pkl" in result["violations"]


def test_repo_index_cleanup_plan_keeps_git_paths_and_project_paths():
    result = build_cleanup_plan(
        paths=[
            "2560_strategy/backend/application/pick_api_service.py",
            "2560_strategy/node_modules/vite/package.json",
            "2560_strategy/data/cache/example.pkl",
        ]
    )

    assert result["candidate_count"] == 2
    assert result["candidates"] == [
        {
            "git_path": "2560_strategy/data/cache/example.pkl",
            "project_path": "data/cache/example.pkl",
        },
        {
            "git_path": "2560_strategy/node_modules/vite/package.json",
            "project_path": "node_modules/vite/package.json",
        },
    ]


def test_non_repository_runtime_code_does_not_import_sqlite_helper_directly():
    project_root = Path(__file__).resolve().parents[1]
    allowed = {
        project_root / "backend" / "__init__.py",
        project_root / "backend" / "repositories" / "audit_logs_repo.py",
        project_root / "backend" / "repositories" / "logs_repo.py",
        project_root / "backend" / "repositories" / "market_data_repo.py",
        project_root / "backend" / "repositories" / "paper_trading_repo.py",
        project_root / "backend" / "repositories" / "picks_repo.py",
        project_root / "backend" / "repositories" / "sessions_repo.py",
        project_root / "backend" / "repositories" / "settings_repo.py",
        project_root / "backend" / "repositories" / "strategy_pool_repo.py",
        project_root / "backend" / "repositories" / "strategy_repo.py",
        project_root / "backend" / "repositories" / "users_repo.py",
    }
    offenders = []
    for path in (project_root / "backend").rglob("*.py"):
        if "__pycache__" in path.parts or path in allowed:
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        if "backend.repositories.db" in source:
            offenders.append(str(path.relative_to(project_root)))

    assert offenders == []


def test_non_repository_runtime_code_does_not_import_sqlite3_directly():
    project_root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in (project_root / "backend").rglob("*.py"):
        if "__pycache__" in path.parts or "repositories" in path.parts:
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        if "import sqlite3" in source or "sqlite3." in source:
            offenders.append(str(path.relative_to(project_root)))

    assert offenders == []


def test_legacy_sqlite_helper_refuses_production(monkeypatch):
    from backend.repositories import db

    monkeypatch.setenv("APP_ENV", "production")

    import pytest

    with pytest.raises(RuntimeError, match="disabled in production"):
        db.db_conn()


def test_default_admin_bootstrap_does_not_swallow_production_create_failures(monkeypatch):
    from backend.services import multiuser_auth_service

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_INIT_USERNAME", "bootstrap-admin")
    monkeypatch.setenv("ADMIN_INIT_PASSWORD", "strong-bootstrap-password")
    monkeypatch.setattr(multiuser_auth_service.users_repo, "has_any_users", lambda: False)

    def broken_create_user(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(multiuser_auth_service.users_repo, "create_user", broken_create_user)

    import pytest

    with pytest.raises(RuntimeError, match="database unavailable"):
        multiuser_auth_service.ensure_default_admin()
