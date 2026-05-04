"""Run the staging SQLite-to-MySQL migration sequence.

Default mode is safe: it upgrades schema, seeds required data, validates schema,
and runs a resolve-only migration dry run. It does not write picks unless
``--apply`` is passed with the migration confirmation token.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.migrate_sqlite_to_mysql import APPLY_CONFIRMATION


CommandRunner = Callable[[list[str]], subprocess.CompletedProcess]


@dataclass(frozen=True)
class StageResult:
    name: str
    command: list[str]
    returncode: int
    ok: bool
    stdout: str
    stderr: str
    parsed_json: dict | None = None
    detail: str = ""


def _run_command(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _python_command(*args: str) -> list[str]:
    return [sys.executable, *args]


def _parse_json_output(stdout: str) -> dict | None:
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def _stage(name: str, command: list[str], runner: CommandRunner) -> StageResult:
    completed = runner(command)
    parsed = _parse_json_output(completed.stdout)
    return StageResult(
        name=name,
        command=command,
        returncode=completed.returncode,
        ok=completed.returncode == 0,
        stdout=completed.stdout,
        stderr=completed.stderr,
        parsed_json=parsed,
    )


def _migration_json_ok(stage: StageResult) -> StageResult:
    data = stage.parsed_json
    if not stage.ok or data is None:
        return stage
    summary = data.get("summary", {})
    target = data.get("target_preconditions", {})
    unresolved = int(summary.get("unresolved_strategy_rows", 0) or 0)
    if target and not target.get("ok", False):
        return StageResult(**{**asdict(stage), "ok": False, "detail": "target preconditions failed"})
    if unresolved:
        return StageResult(**{**asdict(stage), "ok": False, "detail": f"unresolved_strategy_rows={unresolved}"})
    auxiliary = data.get("auxiliary_plan", {}).get("summary", {})
    if auxiliary:
        migrated_tables = ", ".join(f"{table}={count}" for table, count in sorted(auxiliary.items()))
        return StageResult(**{**asdict(stage), "detail": f"auxiliary_plan: {migrated_tables}"})
    return stage


def _reconciliation_ok(stage: StageResult) -> StageResult:
    data = stage.parsed_json
    if not stage.ok or data is None:
        return stage
    reconciliation = data.get("reconciliation")
    if reconciliation and not reconciliation.get("ok", False):
        return StageResult(**{**asdict(stage), "ok": False, "detail": "reconciliation failed"})
    auxiliary_apply = data.get("auxiliary_apply_result", {})
    if auxiliary_apply:
        migrated_tables = ", ".join(sorted(auxiliary_apply))
        return StageResult(**{**asdict(stage), "detail": f"auxiliary_apply: {migrated_tables}"})
    return stage


def run_pipeline(
    *,
    apply: bool = False,
    confirm_apply: str = "",
    sqlite_db: str | None = None,
    tenant_id: int = 1,
    runner: CommandRunner = _run_command,
) -> dict:
    if apply and confirm_apply != APPLY_CONFIRMATION:
        return {
            "ok": False,
            "failed": 1,
            "steps": [],
            "summary": f"--apply requires --confirm-apply {APPLY_CONFIRMATION}",
        }

    migration_base = [_python_command("scripts/migrate_sqlite_to_mysql.py", "--tenant-id", str(tenant_id))]
    if sqlite_db:
        migration_base[0].extend(["--sqlite-db", sqlite_db])

    commands = [
        ("alembic-upgrade", _python_command("-m", "alembic", "upgrade", "head")),
        ("bootstrap-seed", _python_command("scripts/bootstrap_mysql_seed.py")),
        ("validate-schema", _python_command("scripts/validate_mysql_schema.py")),
        ("resolve-dry-run", [*migration_base[0], "--resolve-strategies", "--json"]),
    ]
    if apply:
        commands.extend(
            [
                (
                    "apply",
                    [
                        *migration_base[0],
                        "--apply",
                        "--confirm-apply",
                        confirm_apply,
                        "--json",
                    ],
                ),
                ("verify", [*migration_base[0], "--verify", "--json"]),
            ]
        )

    results: list[StageResult] = []
    for name, command in commands:
        result = _stage(name, command, runner)
        if name == "resolve-dry-run":
            result = _migration_json_ok(result)
        elif name in {"apply", "verify"}:
            result = _migration_json_ok(_reconciliation_ok(result))
        results.append(result)
        if not result.ok:
            break

    failed = [item for item in results if not item.ok]
    return {
        "ok": not failed and len(results) == len(commands),
        "failed": len(failed),
        "steps": [_json_ready(asdict(item)) for item in results],
        "summary": "staging migration pipeline passed" if not failed else f"staging migration pipeline failed at {failed[0].name}",
    }


def _json_ready(value):
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-db", default=None, help="legacy SQLite database path")
    parser.add_argument("--tenant-id", type=int, default=1, help="target tenant id")
    parser.add_argument("--apply", action="store_true", help="write picks after preflight passes")
    parser.add_argument("--confirm-apply", default="", help=f"required token for --apply: {APPLY_CONFIRMATION}")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_pipeline(
        apply=args.apply,
        confirm_apply=args.confirm_apply,
        sqlite_db=args.sqlite_db,
        tenant_id=args.tenant_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
