"""Validate production release evidence for P6 SQLite retirement.

The script is intentionally evidence-driven. It does not connect to production
or mutate any database; operators export a JSON evidence bundle from the target
environment, then this checker decides whether the remaining production gates
are satisfied.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_PATH = PROJECT_ROOT / "docs" / "product" / "PRODUCTION_EVIDENCE.example.json"
MIN_SOAK_MINUTES = 120
REPOSITORY_BACKEND_KEYS = (
    "PICKS_REPOSITORY_BACKEND",
    "AUTH_REPOSITORY_BACKEND",
    "AUDIT_REPOSITORY_BACKEND",
    "SETTINGS_REPOSITORY_BACKEND",
    "LOGS_REPOSITORY_BACKEND",
    "STRATEGY_POOL_REPOSITORY_BACKEND",
    "STRATEGY_REPOSITORY_BACKEND",
)


def _check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


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
            "alembic_revision": "0011_user_engagement_fields",
            "schema_validation_ok": False,
            "reconciliation_ok": False,
            "idempotent_rerun_ok": False,
            "rollback_drill_ok": False,
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
        _check("backup:artifact-present", bool(backup.get("artifact")), "backup artifact name is recorded"),
        _check("backup:sha256-present", bool(backup.get("sha256")), "backup sha256 is recorded"),
        _check("backup:size-positive", int(backup.get("size_bytes") or 0) > 0, "backup size is positive"),
        _check("backup:restore-verified", bool(backup.get("restore_verified")), "backup restore was verified"),
        _check("backup:restore-target-present", bool(backup.get("restore_target")), "restore target is recorded"),
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
            migration.get("alembic_revision") == "0011_user_engagement_fields",
            "alembic revision is 0011_user_engagement_fields",
        ),
    ]


def _sample_ok(sample: dict[str, Any]) -> bool:
    backends = sample.get("repository_backends") or {}
    return (
        bool(sample.get("ready"))
        and sample.get("database_dialect") in {"mysql", "mysql+pymysql"}
        and sample.get("cache_backend") == "redis"
        and all(backends.get(key) == "mysql" for key in REPOSITORY_BACKEND_KEYS)
        and int(sample.get("tasks_stale") or 0) == 0
    )


def _soak_checks(evidence: dict[str, Any], min_minutes: int) -> list[dict[str, Any]]:
    soak = evidence.get("soak") or {}
    samples = [sample for sample in soak.get("readiness_samples") or [] if isinstance(sample, dict)]
    duration = _duration_minutes(soak.get("started_at"), soak.get("ended_at"))
    return [
        _check("soak:duration", duration >= min_minutes, f"duration {duration:.1f} minutes; required {min_minutes}"),
        _check("soak:readiness-samples-present", len(samples) >= 2, f"{len(samples)} readiness samples recorded"),
        _check("soak:readiness-all-ok", bool(samples) and all(_sample_ok(sample) for sample in samples), "all readiness samples are clean"),
        _check("soak:no-errors", not soak.get("errors"), "no soak errors recorded"),
    ]


def validate_evidence(evidence: dict[str, Any], *, min_soak_minutes: int = MIN_SOAK_MINUTES) -> dict[str, Any]:
    checks = [
        _check("schema-version", evidence.get("schema_version") == "production-evidence/v1", "schema_version is production-evidence/v1"),
        _check("environment", evidence.get("environment") == "production", "environment is production"),
        *_backup_checks(evidence),
        *_migration_checks(evidence),
        *_soak_checks(evidence, min_soak_minutes),
    ]
    core_ok = all(item["ok"] for item in checks)
    retirement = evidence.get("sqlite_retirement") or {}
    retirement_checks = [
        _check(
            "sqlite-retirement:delete-write-path-approved",
            core_ok and bool(retirement.get("delete_sqlite_write_path")),
            "SQLite write path deletion requires all production evidence gates",
        ),
        _check(
            "sqlite-retirement:delete-legacy-branches-approved",
            core_ok and bool(retirement.get("delete_legacy_repo_branches")),
            "legacy repo branch deletion requires all production evidence gates",
        ),
        _check(
            "sqlite-retirement:delete-legacy-payload-queries-approved",
            core_ok and bool(retirement.get("delete_legacy_payload_json_queries")),
            "legacy_payload_json query deletion requires all production evidence gates",
        ),
    ]
    checks.extend(retirement_checks)
    failed = [item for item in checks if not item["ok"]]
    return {
        "ok": not failed,
        "core_evidence_ok": core_ok,
        "sqlite_retirement_ok": all(item["ok"] for item in retirement_checks),
        "total": len(checks),
        "failed": len(failed),
        "checks": checks,
        "summary": "production evidence passed" if not failed else f"production evidence failed: {len(failed)} checks",
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
