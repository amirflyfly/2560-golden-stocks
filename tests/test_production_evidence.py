from __future__ import annotations

import json

from scripts.production_evidence import EXPECTED_ALEMBIC_REVISION, REPOSITORY_BACKEND_KEYS, evidence_template, readiness_sample, runtime_evidence_bundle, validate_evidence


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
    evidence["release"].update(
        {
            "deploy_preflight_ok": True,
            "repo_hygiene_ok": True,
            "rollback_plan_reviewed": True,
            "release_notes_reviewed": True,
        }
    )
    evidence["security"].update(
        {
            "secrets_rotated": True,
            "admin_password_rotated": True,
            "public_ports_reviewed": True,
            "csrf_headers_verified": True,
            "live_broker_policy_disabled": True,
        }
    )
    evidence["regression"].update(
        {
            "backend_tests_passed": True,
            "frontend_build_passed": True,
            "smoke_tests_passed": True,
            "tested_at": "2026-05-04T03:10:00Z",
            "commands": ["pytest", "npm --prefix frontend run build"],
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
        "signal_review_complete_rate": 1,
        "signal_review_incomplete": 0,
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
    assert "restore:verified" in failed
    assert "soak:readiness-samples-present" in failed
    assert "release:deploy-preflight" in failed
    assert "security:live-broker-policy-disabled" in failed
    assert "regression:backend-tests" in failed
    assert "sqlite-retirement:delete-write-path-approved" in failed


def test_production_evidence_accepts_complete_backup_soak_and_rollback_bundle():
    result = validate_evidence(_passing_evidence())

    assert result["ok"] is True
    assert result["core_evidence_ok"] is True
    assert result["sqlite_retirement_ok"] is True
    assert result["failed"] == 0
    assert result["sqlite_retirement_failed"] == 0


def test_production_evidence_rejects_stale_tasks_during_soak():
    evidence = _passing_evidence()
    evidence["soak"]["readiness_samples"][1]["tasks_stale"] = 1

    result = validate_evidence(evidence)
    failed = {item["name"] for item in result["checks"] if not item["ok"]}

    assert result["ok"] is False
    assert "soak:readiness-all-ok" in failed
    assert "sqlite-retirement:delete-write-path-approved" in failed


def test_production_evidence_rejects_incomplete_signal_review_links():
    evidence = _passing_evidence()
    evidence["soak"]["readiness_samples"][1]["signal_review_complete_rate"] = 0.99
    evidence["soak"]["readiness_samples"][1]["signal_review_incomplete"] = 1

    result = validate_evidence(evidence)
    failed = {item["name"] for item in result["checks"] if not item["ok"]}

    assert result["ok"] is False
    assert "soak:readiness-all-ok" in failed


def test_production_evidence_core_gate_does_not_require_sqlite_retirement():
    evidence = _passing_evidence()
    evidence["sqlite_retirement"].update(
        {
            "delete_sqlite_write_path": False,
            "delete_legacy_repo_branches": False,
            "delete_legacy_payload_json_queries": False,
        }
    )

    result = validate_evidence(evidence)

    assert result["ok"] is True
    assert result["core_evidence_ok"] is True
    assert result["sqlite_retirement_ok"] is False
    assert result["failed"] == 0
    assert result["sqlite_retirement_failed"] == 3


def test_production_evidence_rejects_missing_security_and_regression_sections():
    evidence = _passing_evidence()
    evidence.pop("security")
    evidence.pop("regression")

    result = validate_evidence(evidence)
    failed = {item["name"] for item in result["checks"] if not item["ok"]}

    assert result["ok"] is False
    assert "security:section-present" in failed
    assert "regression:section-present" in failed


def test_production_evidence_template_can_be_serialized(tmp_path):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence_template()), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))

    assert loaded["schema_version"] == "production-evidence/v1"
    assert loaded["migration"]["alembic_revision"] == EXPECTED_ALEMBIC_REVISION
    assert "TRADING_REPOSITORY_BACKEND" in loaded["soak"]["readiness_samples"][0]["repository_backends"]
    assert loaded["soak"]["readiness_samples"][0]["signal_review_complete_rate"] == 1
    assert "backup" in loaded
    assert "release" in loaded
    assert "security" in loaded
    assert "regression" in loaded
    assert "soak" in loaded


def test_readiness_sample_maps_runtime_readiness_to_evidence_contract():
    sample = readiness_sample(
        {
            "ready": True,
            "database": {"dialect": "mysql", "repository_backends": {key: "mysql" for key in REPOSITORY_BACKEND_KEYS}},
            "cache": {"backend": "redis"},
            "task_queue": {"backend": "redis", "execution_mode": "worker"},
            "tasks": {"stale": 0},
            "signal_review": {"complete_rate": 1, "incomplete": 0},
        },
        sampled_at="2026-05-12T10:00:00",
    )

    assert sample["at"] == "2026-05-12T10:00:00"
    assert sample["database_dialect"] == "mysql"
    assert sample["task_execution_mode"] == "worker"
    assert sample["signal_review_complete_rate"] == 1
    assert sample["signal_review_incomplete"] == 0
    assert sample["repository_backends"]["TRADING_REPOSITORY_BACKEND"] == "mysql"


def test_runtime_evidence_bundle_embeds_readiness_sample_without_claiming_manual_gates():
    bundle = runtime_evidence_bundle(
        {
            "ready": True,
            "database": {"dialect": "mysql", "repository_backends": {key: "mysql" for key in REPOSITORY_BACKEND_KEYS}},
            "cache": {"backend": "redis"},
            "task_queue": {"backend": "redis", "execution_mode": "worker"},
            "tasks": {"stale": 0},
            "signal_review": {"complete_rate": 1, "incomplete": 0},
        },
        collected_at="2026-05-12T10:30:00",
    )

    assert bundle["schema_version"] == "production-evidence/v1"
    assert bundle["release"]["runtime_readiness_exported"] is True
    assert bundle["release"]["deploy_preflight_ok"] is False
    assert bundle["soak"]["readiness_samples"][0]["at"] == "2026-05-12T10:30:00"
    assert bundle["soak"]["readiness_samples"][0]["ready"] is True
    assert bundle["soak"]["errors"] == []
