"""Shared market data quality gate decisions for user-facing workflows."""

from __future__ import annotations

from typing import Any

from backend.core.errors import AppError


class DataQualityGateService:
    """Normalizes market data quality and returns consistent gate metadata."""

    DEGRADED_QUALITIES = {"fallback", "unknown", ""}

    def _bool_value(self, value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    def normalize_context(self, payload: dict | None = None) -> dict:
        payload = payload or {}
        source = str(payload.get("market_data_source") or payload.get("actual_provider") or payload.get("provider") or payload.get("source") or "").strip().lower()
        quality = str(payload.get("data_quality") or "").strip().lower()
        fallback_used = self._bool_value(payload.get("fallback_used"))
        if not quality:
            quality = "mock" if source == "mock" else ("fallback" if fallback_used else "unknown")
        return {
            "data_quality": quality,
            "market_data_source": source,
            "fallback_used": fallback_used,
            "provider_chain": list(payload.get("provider_chain") or []),
            "errors": list(payload.get("errors") or []),
        }

    def reject_mock(self, payload: dict | None = None, *, context: str = "market data") -> None:
        normalized = self.normalize_context(payload)
        source_parts = {
            part.strip()
            for part in normalized["market_data_source"].replace(";", ",").replace("|", ",").split(",")
            if part.strip()
        }
        if normalized["data_quality"] == "mock" or "mock" in source_parts:
            raise AppError(f"{context} uses mock market data; mock data is disabled")

    def decision(
        self,
        action: str,
        payload: dict | None = None,
        *,
        enforce: bool = False,
        allow_degraded: bool = False,
    ) -> dict:
        context = self.normalize_context(payload)
        quality = context["data_quality"]
        fallback_used = context["fallback_used"]
        warnings: list[str] = []
        reason = ""
        severity = "ok"
        requires_confirmation = False

        if quality == "mock" or context["market_data_source"] == "mock":
            reason = "mock_market_data"
            severity = "block" if enforce else "warn"
            requires_confirmation = True
            warnings.append("mock_market_data")
        elif quality in self.DEGRADED_QUALITIES or fallback_used:
            reason = "degraded_market_data"
            severity = "warn"
            requires_confirmation = True
            warnings.append("degraded_market_data")

        blocked = bool(enforce and reason and (reason == "mock_market_data" or not allow_degraded))
        status = "blocked" if blocked else ("warning" if warnings else "allowed")
        if reason == "mock_market_data":
            next_action = "禁止在生产主流程使用 mock 行情；请切换真实行情源并重新执行。" if blocked else "当前为 mock 行情，仅可用于开发链路验证，禁止作为正式投研结论。"
            display_message = "检测到 mock 模拟行情，生产扫描、回测、入池和模拟验证必须阻断。"
        elif reason == "degraded_market_data":
            next_action = "已允许降级数据继续展示；请人工复核行情源、覆盖率和时效后再使用。" if allow_degraded else "行情已降级或质量未知；请人工确认或同步主数据源后继续。"
            display_message = "检测到 fallback/unknown 行情，结论需谨慎使用并保留确认记录。"
        else:
            next_action = "数据质量门禁通过，可继续执行当前研究动作。"
            display_message = "数据质量门禁通过。"
        mock_or_fallback = quality == "mock" or fallback_used or quality in {"fallback", "unknown", ""}
        return {
            "schema_version": "data-quality-gate/v1",
            "action": action,
            "status": status,
            "blocked": blocked,
            "reason": reason if blocked else "",
            "quality_reason": reason,
            "grade": quality,
            "source": context["market_data_source"],
            "mock_or_fallback": mock_or_fallback,
            "execution_allowed": not blocked,
            "severity": severity,
            "requires_confirmation": requires_confirmation and not allow_degraded,
            "allow_degraded": bool(allow_degraded),
            "enforced": bool(enforce),
            "data_quality": quality,
            "market_data_source": context["market_data_source"],
            "fallback_used": fallback_used,
            "warnings": warnings,
            "next_action": next_action,
            "display_message": display_message,
        }

    def paper_trade_block_reason(self, candidate: dict, params: dict | None = None) -> str:
        params = params or {}
        if not self._bool_value(params.get("enforce_market_data_quality_gate")):
            return ""
        decision = self.decision(
            "paper_trade",
            candidate,
            enforce=True,
            allow_degraded=self._bool_value(params.get("allow_degraded_market_data")),
        )
        return str(decision.get("reason") or "")
