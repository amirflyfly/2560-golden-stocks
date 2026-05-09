"""P0 launch gate aggregation service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.application.live_broker_service import LiveBrokerService
from backend.application.monitoring_service import MonitoringService
from backend.core.config import effective_repository_backends, get_settings
from scripts.check_repo_hygiene import find_hygiene_violations
from scripts.deploy_preflight import run_preflight
from scripts.production_evidence import DEFAULT_EVIDENCE_PATH, load_evidence, validate_evidence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEGACY_POLICY_DOC = PROJECT_ROOT / "docs" / "product" / "LEGACY_ADMIN_POLICY.md"


def _summary(result: dict[str, Any], *, name: str | None = None) -> dict[str, Any]:
    checks = [item for item in result.get("checks") or [] if isinstance(item, dict)]
    failed = [item for item in checks if not item.get("ok")]
    return {
        "ok": bool(result.get("ok") if "ok" in result else result.get("ready")),
        "summary": str(result.get("summary") or ("ok" if not failed else f"{len(failed)} checks failed")),
        "counts": {
            "total": int(result.get("total") or len(checks)),
            "failed": int(result.get("failed") or len(failed)),
        },
        "checks": [str(item.get("name") or item.get("check") or "unknown") for item in checks],
        **({"name": name} if name else {}),
    }


class LaunchCheckService:
    def __init__(self, monitoring_service: MonitoringService | None = None, live_broker_service: LiveBrokerService | None = None):
        self.monitoring_service = monitoring_service or MonitoringService()
        self.live_broker_service = live_broker_service or LiveBrokerService()

    def run(self) -> dict[str, Any]:
        gates = {
            "readiness": self._readiness_gate(),
            "repository_backends": self._repository_backends_gate(),
            "live_broker_safe": self._live_broker_gate(),
            "production_evidence": self._production_evidence_gate(DEFAULT_EVIDENCE_PATH),
            "deploy_preflight": self._deploy_preflight_gate(),
            "repo_hygiene": self._repo_hygiene_gate(),
            "legacy_policy_doc": self._legacy_policy_gate(),
        }
        failed = [name for name, gate in gates.items() if not gate.get("ok")]
        return {
            "ok": not failed,
            "summary": "launch gates passed" if not failed else f"launch blocked: {len(failed)} gates failed",
            "counts": {"total": len(gates), "failed": len(failed)},
            "gates": gates,
            "failed_gates": failed,
        }

    def _readiness_gate(self) -> dict[str, Any]:
        try:
            readiness = self.monitoring_service.readiness()
            checks = [
                {"name": name, "ok": bool(ok)}
                for name, ok in (readiness.get("checks") or {}).items()
            ]
            return {
                "ok": bool(readiness.get("ready")),
                "summary": "ready" if readiness.get("ready") else "readiness failed",
                "counts": {"total": len(checks), "failed": len([item for item in checks if not item["ok"]])},
                "checks": [item["name"] for item in checks],
            }
        except Exception as exc:
            return self._failed_gate("readiness unavailable", exc)

    def _repository_backends_gate(self) -> dict[str, Any]:
        settings = get_settings()
        backends = effective_repository_backends(settings.environment)
        production = (settings.environment or "").strip().lower() in {"prod", "production"}
        failed = [name for name, value in backends.items() if production and value != "mysql"]
        return {
            "ok": not failed,
            "summary": "repository backends are production safe" if not failed else "repository backends are not production safe",
            "counts": {"total": len(backends), "failed": len(failed)},
            "checks": sorted(backends.keys()),
        }

    def _live_broker_gate(self) -> dict[str, Any]:
        try:
            status = self.live_broker_service.broker_status()
            config = status.get("config") or {}
            validation = status.get("validation") or {}
            policy_disabled = config.get("launch_policy") == "disabled"
            ok = policy_disabled and not validation.get("ready_for_live_orders")
            return {
                "ok": ok,
                "summary": "live broker launch policy disabled" if ok else "live broker policy is not v1.0 safe",
                "counts": {"total": 2, "failed": 0 if ok else 1},
                "checks": ["launch_policy_disabled", "live_orders_not_open"],
            }
        except Exception as exc:
            return self._failed_gate("live broker gate unavailable", exc)

    def _production_evidence_gate(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {
                "ok": False,
                "summary": "production evidence file missing",
                "counts": {"total": 1, "failed": 1},
                "checks": ["production_evidence_file_present"],
            }
        try:
            result = validate_evidence(load_evidence(path))
            return _summary(result)
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
            return self._failed_gate("production evidence invalid", exc)

    def _deploy_preflight_gate(self) -> dict[str, Any]:
        try:
            return _summary(run_preflight(PROJECT_ROOT))
        except Exception as exc:
            return self._failed_gate("deploy preflight unavailable", exc)

    def _repo_hygiene_gate(self) -> dict[str, Any]:
        try:
            result = find_hygiene_violations(PROJECT_ROOT)
            return {
                "ok": bool(result.get("ok")),
                "summary": "repo hygiene passed" if result.get("ok") else f"repo hygiene failed: {int(result.get('violation_count') or 0)} violations",
                "counts": {"total": int(result.get("total_paths") or 0), "failed": int(result.get("violation_count") or 0)},
                "checks": ["repo_hygiene_no_generated_files"],
            }
        except Exception as exc:
            return self._failed_gate("repo hygiene unavailable", exc)

    def _legacy_policy_gate(self) -> dict[str, Any]:
        ok = LEGACY_POLICY_DOC.exists()
        return {
            "ok": ok,
            "summary": "legacy admin policy documented" if ok else "legacy admin policy doc missing",
            "counts": {"total": 1, "failed": 0 if ok else 1},
            "checks": ["legacy_policy_doc_present"],
        }

    def _failed_gate(self, summary: str, exc: Exception) -> dict[str, Any]:
        return {
            "ok": False,
            "summary": summary,
            "counts": {"total": 1, "failed": 1},
            "checks": [exc.__class__.__name__],
        }


launch_check_service = LaunchCheckService()
