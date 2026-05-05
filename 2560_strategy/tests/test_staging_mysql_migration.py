import json
import subprocess

from scripts.migrate_sqlite_to_mysql import APPLY_CONFIRMATION
from scripts.staging_mysql_migration import run_pipeline


def _completed(command, stdout=None, returncode=0):
    return subprocess.CompletedProcess(command, returncode, stdout=stdout or "{}", stderr="")


def _is_migration_command(command):
    return any(str(part).endswith("migrate_sqlite_to_mysql.py") for part in command)


def test_staging_pipeline_default_sequence_stops_before_apply():
    commands = []

    def runner(command):
        commands.append(command)
        if _is_migration_command(command):
            return _completed(
                command,
                json.dumps(
                    {
                        "summary": {"unresolved_strategy_rows": 0},
                        "target_preconditions": {"ok": True},
                        "auxiliary_plan": {"summary": {"ui_settings": 1, "operation_logs": 2}},
                    }
                ),
            )
        return _completed(command)

    result = run_pipeline(runner=runner)

    assert result["ok"] is True
    assert [step["name"] for step in result["steps"]] == [
        "alembic-upgrade",
        "bootstrap-seed",
        "validate-schema",
        "resolve-dry-run",
    ]
    assert not any("--apply" in command for command in commands)
    assert result["steps"][-1]["detail"] == "auxiliary_plan: operation_logs=2, ui_settings=1"


def test_staging_pipeline_blocks_unresolved_strategy_rows():
    def runner(command):
        if _is_migration_command(command):
            return _completed(
                command,
                json.dumps(
                    {
                        "summary": {"unresolved_strategy_rows": 2},
                        "target_preconditions": {"ok": True},
                    }
                ),
            )
        return _completed(command)

    result = run_pipeline(runner=runner)

    assert result["ok"] is False
    assert result["steps"][-1]["name"] == "resolve-dry-run"
    assert result["steps"][-1]["detail"] == "unresolved_strategy_rows=2"


def test_staging_pipeline_apply_requires_confirmation():
    result = run_pipeline(apply=True, confirm_apply="wrong")

    assert result["ok"] is False
    assert result["failed"] == 1
    assert APPLY_CONFIRMATION in result["summary"]


def test_staging_pipeline_apply_runs_verify_and_blocks_reconciliation_failure():
    migrate_calls = []

    def runner(command):
        if not _is_migration_command(command):
            return _completed(command)
        migrate_calls.append(command)
        if "--verify" in command:
            return _completed(
                command,
                json.dumps(
                    {
                        "summary": {"unresolved_strategy_rows": 0},
                        "target_preconditions": {"ok": True},
                        "reconciliation": {"ok": False},
                    }
                ),
            )
        return _completed(
            command,
            json.dumps(
                {
                        "summary": {"unresolved_strategy_rows": 0},
                        "target_preconditions": {"ok": True},
                        "reconciliation": {"ok": True},
                        "auxiliary_apply_result": {"ui_settings": {"inserted": 1}, "operation_logs": {"inserted": 2}},
                    }
                ),
            )

    result = run_pipeline(apply=True, confirm_apply=APPLY_CONFIRMATION, runner=runner)

    assert result["ok"] is False
    assert result["steps"][-1]["name"] == "verify"
    assert result["steps"][-1]["detail"] == "reconciliation failed"
    assert any("--apply" in command for command in migrate_calls)
    assert any("--verify" in command for command in migrate_calls)
