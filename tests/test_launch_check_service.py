from __future__ import annotations

from pathlib import Path

from backend.application.launch_check_service import LaunchCheckService
from backend.core.config import get_settings


class _MonitoringStub:
    def readiness(self):
        return {
            "ready": True,
            "checks": {
                "database": True,
                "repository_backends": True,
                "live_broker_gate": True,
                "market_data_provider": True,
            },
        }


class _LiveBrokerStub:
    def broker_status(self):
        return {
            "config": {"launch_policy": "disabled", "live_orders_open": False},
            "validation": {"ready_for_live_orders": False},
        }


def test_launch_check_missing_evidence_returns_blocked_gate_without_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    service = LaunchCheckService(monitoring_service=_MonitoringStub(), live_broker_service=_LiveBrokerStub())

    gate = service._production_evidence_gate(tmp_path / "missing.json")

    assert gate["ok"] is False
    assert gate["summary"] == "production evidence file missing"
    assert gate["counts"] == {"total": 1, "failed": 1}
    assert gate["checks"] == ["production_evidence_file_present"]


def test_launch_check_result_structure_contains_gates(monkeypatch, request):
    get_settings.cache_clear()
    request.addfinalizer(get_settings.cache_clear)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "test-production-secret-key-32-chars-minimum")
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://strategy_user:strong-password@localhost:3306/strategy_2560?charset=utf8mb4")
    monkeypatch.setenv("CACHE_BACKEND", "redis")
    monkeypatch.setenv("TASK_QUEUE_BACKEND", "redis")
    monkeypatch.setenv("TASK_EXECUTION_MODE", "worker")
    service = LaunchCheckService(monitoring_service=_MonitoringStub(), live_broker_service=_LiveBrokerStub())
    monkeypatch.setattr(service, "_production_evidence_gate", lambda path: {"ok": False, "summary": "missing", "counts": {"total": 1, "failed": 1}, "checks": ["production_evidence_file_present"]})
    monkeypatch.setattr(service, "_deploy_preflight_gate", lambda: {"ok": True, "summary": "ok", "counts": {"total": 1, "failed": 0}, "checks": ["deploy_preflight"]})
    monkeypatch.setattr(service, "_repo_hygiene_gate", lambda: {"ok": True, "summary": "ok", "counts": {"total": 1, "failed": 0}, "checks": ["repo_hygiene"]})
    monkeypatch.setattr(service, "_legacy_policy_gate", lambda: {"ok": True, "summary": "ok", "counts": {"total": 1, "failed": 0}, "checks": ["legacy_policy_doc_present"]})

    result = service.run()

    assert result["ok"] is False
    assert result["counts"] == {"total": 7, "failed": 1}
    assert set(result["gates"]) == {
        "readiness",
        "repository_backends",
        "live_broker_safe",
        "production_evidence",
        "deploy_preflight",
        "repo_hygiene",
        "legacy_policy_doc",
    }
    for gate in result["gates"].values():
        assert set(gate) >= {"ok", "summary", "counts", "checks"}
