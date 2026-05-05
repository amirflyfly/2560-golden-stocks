from __future__ import annotations

import json

from scripts.production_evidence import REPOSITORY_BACKEND_KEYS, evidence_template, validate_evidence


def _passing_evidence() -> dict:
    evidence = evidence_template()
    evidence["backup"].update(
        {
            "sha256": "a" * 64,
            "size_bytes": 1024,
            "restore_verified": True,
            "restore_checked_at": "2026-05-04T01:00:00Z",
        }
    )
    evidence["migration"].update(
        {
            "schema_validation_ok": True,
            "reconciliation_ok": True,
            "idempotent_rerun_ok": True,
            "rollback_drill_ok": True,
        }
    )
    sample = {
        "ready": True,
        "database_dialect": "mysql",
        "cache_backend": "redis",
        "task_queue_backend": "redis",
        "task_execution_mode": "worker",
        "repository_backends": {key: "mysql" for key in REPOSITORY_BACKEND_KEYS},
        "tasks_stale": 0,
    }
    evidence["soak"].update(
        {
            "started_at": "2026-05-04T00:00:00Z",
            "ended_at": "2026-05-04T03:00:00Z",
            "readiness_samples": [
                {"at": "2026-05-04T00:00:00Z", **sample},
                {"at": "2026-05-04T03:00:00Z", **sample},
            ],
            "errors": [],
        }
    )
    evidence["sqlite_retirement"].update(
        {
            "delete_sqlite_write_path": True,
            "delete_legacy_repo_branches": True,
            "delete_legacy_payload_json_queries": True,
        }
    )
    return evidence


def test_production_evidence_template_is_not_enough_to_retire_sqlite():
    result = validate_evidence(evidence_template())
    failed = {item["name"] for item in result["checks"] if not item["ok"]}

    assert result["ok"] is False
    assert result["core_evidence_ok"] is False
    assert "backup:sha256-present" in failed
    assert "backup:restore-verified" in failed
    assert "soak:readiness-samples-present" in failed
    assert "sqlite-retirement:delete-write-path-approved" in failed


def test_production_evidence_accepts_complete_backup_soak_and_rollback_bundle():
    result = validate_evidence(_passing_evidence())

    assert result["ok"] is True
    assert result["core_evidence_ok"] is True
    assert result["sqlite_retirement_ok"] is True
    assert result["failed"] == 0


def test_production_evidence_rejects_stale_tasks_during_soak():
    evidence = _passing_evidence()
    evidence["soak"]["readiness_samples"][1]["tasks_stale"] = 1

    result = validate_evidence(evidence)
    failed = {item["name"] for item in result["checks"] if not item["ok"]}

    assert result["ok"] is False
    assert "soak:readiness-all-ok" in failed
    assert "sqlite-retirement:delete-write-path-approved" in failed


def test_production_evidence_template_can_be_serialized(tmp_path):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence_template()), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))

    assert loaded["schema_version"] == "production-evidence/v1"
    assert "backup" in loaded
    assert "soak" in loaded
