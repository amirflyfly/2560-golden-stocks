"""Validate production release evidence for P0 launch and P6 SQLite retirement.

The script is intentionally evidence-driven. It does not connect to production
or mutate any database; operators export a JSON evidence bundle from the target
environment, then this checker decides whether the production launch gates are
satisfied. SQLite retirement checks remain advisory and are not required for the
v1.0 launch core evidence gate.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_PATH = PROJECT_ROOT / "docs" / "product" / "PRODUCTION_EVIDENCE.example.json"
EXPECTED_ALEMBIC_REVISION = "0022_stock_daily_bar_timestamps"
MIN_SOAK_MINUTES = 120
REPOSITORY_BACKEND_KEYS = (
    "PICKS_REPOSITORY_BACKEND",
    "AUTH_REPOSITORY_BACKEND",
    "AUDIT_REPOSITORY_BACKEND",
    "SETTINGS_REPOSITORY_BACKEND",
    "LOGS_REPOSITORY_BACKEND",
    "STRATEGY_POOL_REPOSITORY_BACKEND",
    "STRATEGY_REPOSITORY_BACKEND",
    "TRADING_REPOSITORY_BACKEND",
)


def _check(name: str, ok: bool, detail: str = "", *, advisory: bool = False) -> dict[str, Any]:
    item = {"name": name, "ok": bool(ok), "detail": detail}
    if advisory:
        item["advisory"] = True
    return item


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_minutes(start: str | None, end: str | None) -> float:
    start_at = _parse_time(start)
    end_at = _parse_time(end)
    if not start_at or not end_at:
        return 0.0
    return max(0.0, (end_at - start_at).total_seconds() / 60)


def evidence_template() -> dict[str, Any]:
    return {
        "schema_version": "production-evidence/v1",
        "environment": "production",
        "backup": {
            "artifact": "mysql-dump-YYYYMMDDHHMM.sql.gz",
            "created_at": "2026-05-04T00:00:00Z",
            "sha256": "",
            "size_bytes": 0,
            "restore_verified": False,
            "restore_target": "restore_check_prod_YYYYMMDD",
            "restore_checked_at": "",
        },
        "migration": {
            "alembic_revision": EXPECTED_ALEMBIC_REVISION,
            "schema_validation_ok": False,
            "reconciliation_ok": False,
            "idempotent_rerun_ok": False,
            "rollback_drill_ok": False,
        },
        "release": {
            "deploy_preflight_ok": False,
            "repo_hygiene_ok": False,
            "rollback_plan_reviewed": False,
            "release_notes_reviewed": False,
        },
        "security": {
            "secrets_rotated": False,
            "admin_password_rotated": False,
            "public_ports_reviewed": False,
            "csrf_headers_verified": False,
            "live_broker_policy_disabled": False,
        },
        "regression": {
            "backend_tests_passed": False,
            "frontend_build_passed": False,
            "smoke_tests_passed": False,
            "tested_at": "",
            "commands": [],
        },
        "soak": {
            "started_at": "2026-05-04T00:00:00Z",
            "ended_at": "2026-05-04T02:00:00Z",
            "readiness_samples": [
                {
                    "at": "2026-05-04T00:00:00Z",
                    "ready": True,
                    "database_dialect": "mysql",
                    "cache_backend": "redis",
                    "task_queue_backend": "redis",
                    "task_execution_mode": "worker",
                    "repository_backends": {key: "mysql" for key in REPOSITORY_BACKEND_KEYS},
                    "tasks_stale": 0,
                }
            ],
            "errors": [],
        },
        "sqlite_retirement": {
            "delete_sqlite_write_path": False,
            "delete_legacy_repo_branches": False,
            "delete_legacy_payload_json_queries": False,
        },
    }


def _backup_checks(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    backup = evidence.get("backup") or {}
    return [
        _check("backup:section-present", isinstance(evidence.get("backup"), dict), "backup evidence section is present"),
        _check("backup:artifact-present", bool(backup.get("artifact")), "backup artifact name is recorded"),
        _check("backup:sha256-present", bool(backup.get("sha256")), "backup sha256 is recorded"),
        _check("backup:size-positive", int(backup.get("size_bytes") or 0) > 0, "backup size is positive"),
        _check("restore:verified", bool(backup.get("restore_verified")), "backup restore was verified"),
        _check("restore:target-present", bool(backup.get("restore_target")), "restore target is recorded"),
        _check("restore:checked-at-present", bool(backup.get("restore_checked_at")), "restore check time is recorded"),
    ]


def _migration_checks(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    migration = evidence.get("migration") or {}
    return [
        _check("migration:schema-validation", bool(migration.get("schema_validation_ok")), "schema validator passed"),
        _check("migration:reconciliation", bool(migration.get("reconciliation_ok")), "source and target reconciliation passed"),
        _check("migration:idempotent-rerun", bool(migration.get("idempotent_rerun_ok")), "migration rerun was idempotent"),
        _check("migration:rollback-drill", bool(migration.get("rollback_drill_ok")), "rollback drill passed"),
        _check(
            "migration:expected-revision",
            migration.get("alembic_revision") == EXPECTED_ALEMBIC_REVISION,
            f"alembic revision is {EXPECTED_ALEMBIC_REVISION}",
        ),
    ]


def _release_checks(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    release = evidence.get("release") or {}
    return [
        _check("release:section-present", isinstance(evidence.get("release"), dict), "release evidence section is present"),
        _check("release:deploy-preflight", bool(release.get("deploy_preflight_ok")), "deploy preflight passed"),
        _check("release:repo-hygiene", bool(release.get("repo_hygiene_ok")), "repository hygiene check passed"),
        _check("release:rollback-plan", bool(release.get("rollback_plan_reviewed")), "rollback plan was reviewed"),
        _check("release:notes-reviewed", bool(release.get("release_notes_reviewed")), "release notes were reviewed"),
    ]


def _security_checks(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    security = evidence.get("security") or {}
    return [
        _check("security:section-present", isinstance(evidence.get("security"), dict), "security evidence section is present"),
        _check("security:secrets-rotated", bool(security.get("secrets_rotated")), "production secrets were rotated"),
        _check("security:admin-password-rotated", bool(security.get("admin_password_rotated")), "admin bootstrap password was rotated"),
        _check("security:public-ports-reviewed", bool(security.get("public_ports_reviewed")), "public port exposure was reviewed"),
        _check("security:csrf-headers-verified", bool(security.get("csrf_headers_verified")), "CSRF and security headers were verified"),
        _check("security:live-broker-policy-disabled", bool(security.get("live_broker_policy_disabled")), "live broker launch policy is disabled for v1.0"),
    ]


def _regression_checks(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    regression = evidence.get("regression") or {}
    commands = regression.get("commands") or []
    return [
        _check("regression:section-present", isinstance(evidence.get("regression"), dict), "regression evidence section is present"),
        _check("regression:backend-tests", bool(regression.get("backend_tests_passed")), "backend regression tests passed"),
        _check("regression:frontend-build", bool(regression.get("frontend_build_passed")), "frontend production build passed"),
        _check("regression:smoke-tests", bool(regression.get("smoke_tests_passed")), "post-deploy smoke tests passed"),
        _check("regression:tested-at", bool(regression.get("tested_at")), "regression test time is recorded"),
        _check("regression:commands-recorded", bool(commands), "regression commands are recorded"),
    ]


def _sample_ok(sample: dict[str, Any]) -> bool:
    backends = sample.get("repository_backends") or {}
    return (
        bool(sample.get("ready"))
        and sample.get("database_dialect") in {"mysql", "mysql+pymysql"}
        and sample.get("cache_backend") == "redis"
        and sample.get("task_queue_backend") == "redis"
        and sample.get("task_execution_mode") == "worker"
        and all(backends.get(key) == "mysql" for key in REPOSITORY_BACKEND_KEYS)
        and int(sample.get("tasks_stale") or 0) == 0
    )


def _soak_checks(evidence: dict[str, Any], min_minutes: int) -> list[dict[str, Any]]:
    soak = evidence.get("soak") or {}
    samples = [sample for sample in soak.get("readiness_samples") or [] if isinstance(sample, dict)]
    duration = _duration_minutes(soak.get("started_at"), soak.get("ended_at"))
    return [
        _check("soak:section-present", isinstance(evidence.get("soak"), dict), "soak evidence section is present"),
        _check("soak:duration", duration >= min_minutes, f"duration {duration:.1f} minutes; required {min_minutes}"),
        _check("soak:readiness-samples-present", len(samples) >= 2, f"{len(samples)} readiness samples recorded"),
        _check("soak:readiness-all-ok", bool(samples) and all(_sample_ok(sample) for sample in samples), "all readiness samples are clean"),
        _check("soak:no-errors", not soak.get("errors"), "no soak errors recorded"),
    ]


def validate_evidence(evidence: dict[str, Any], *, min_soak_minutes: int = MIN_SOAK_MINUTES) -> dict[str, Any]:
    core_checks = [
        _check("schema-version", evidence.get("schema_version") == "production-evidence/v1", "schema_version is production-evidence/v1"),
        _check("environment", evidence.get("environment") == "production", "environment is production"),
        *_backup_checks(evidence),
        *_migration_checks(evidence),
        *_release_checks(evidence),
        *_security_checks(evidence),
        *_regression_checks(evidence),
        *_soak_checks(evidence, min_soak_minutes),
    ]
    core_ok = all(item["ok"] for item in core_checks)
    retirement = evidence.get("sqlite_retirement") or {}
    retirement_checks = [
        _check(
            "sqlite-retirement:delete-write-path-approved",
            core_ok and bool(retirement.get("delete_sqlite_write_path")),
            "SQLite write path deletion requires all production evidence gates",
            advisory=True,
        ),
        _check(
            "sqlite-retirement:delete-legacy-branches-approved",
            core_ok and bool(retirement.get("delete_legacy_repo_branches")),
            "legacy repo branch deletion requires all production evidence gates",
            advisory=True,
        ),
        _check(
            "sqlite-retirement:delete-legacy-payload-queries-approved",
            core_ok and bool(retirement.get("delete_legacy_payload_json_queries")),
            "legacy_payload_json query deletion requires all production evidence gates",
            advisory=True,
        ),
    ]
    failed_core = [item for item in core_checks if not item["ok"]]
    failed_retirement = [item for item in retirement_checks if not item["ok"]]
    return {
        "ok": core_ok,
        "core_evidence_ok": core_ok,
        "sqlite_retirement_ok": all(item["ok"] for item in retirement_checks),
        "total": len(core_checks),
        "failed": len(failed_core),
        "sqlite_retirement_failed": len(failed_retirement),
        "checks": [*core_checks, *retirement_checks],
        "summary": "production evidence passed" if core_ok else f"production evidence failed: {len(failed_core)} checks",
    }


def load_evidence(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate production release evidence.")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE_PATH, help="Path to production evidence JSON.")
    parser.add_argument("--min-soak-minutes", type=int, default=MIN_SOAK_MINUTES)
    parser.add_argument("--write-template", type=Path, help="Write an evidence JSON template and exit.")
    args = parser.parse_args()

    if args.write_template:
        args.write_template.parent.mkdir(parents=True, exist_ok=True)
        args.write_template.write_text(json.dumps(evidence_template(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "written": str(args.write_template)}, ensure_ascii=False))
        return 0

    result = validate_evidence(load_evidence(args.evidence), min_soak_minutes=args.min_soak_minutes)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
