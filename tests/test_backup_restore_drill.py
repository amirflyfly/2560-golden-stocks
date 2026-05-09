from __future__ import annotations

import pytest


def test_backup_restore_drill_runs_in_isolated_data_dir():
    from scripts.backup_restore_drill import run_drill

    result = run_drill()

    assert result["ok"] is True
    assert result["backup_bytes"] > 0
    assert result["validation"] == "ok"
    assert result["restored_drill_rows"] == 1
    assert "strategy_backup_drill_" in result["data_dir"]


def test_legacy_sqlite_backup_service_is_disabled_in_production(monkeypatch):
    from types import SimpleNamespace

    from backend.services import backup_service

    monkeypatch.setattr(backup_service, "get_settings", lambda: SimpleNamespace(environment="production"))

    with pytest.raises(RuntimeError, match="disabled in production"):
        backup_service.make_backup_zip_bytes()

    assert backup_service.list_backups() == []
    assert backup_service.cached_validate_backup("anything.zip") == (False, "DISABLED")
    assert backup_service.backup_stats()["disabled"] is True


def test_legacy_backup_pages_render_disabled_state_in_production(monkeypatch):
    from types import SimpleNamespace

    from backend.pages.backups_page import render_backups_page
    from backend.pages.migration_check_page import render_migration_check_page
    from backend.services import backup_service

    monkeypatch.setattr(backup_service, "get_settings", lambda: SimpleNamespace(environment="production"))

    backups_html = render_backups_page()
    migration_html = render_migration_check_page()

    assert "Legacy SQLite backup/restore is disabled in production" in backups_html
    assert "mysql_restore_check.sh" in migration_html
