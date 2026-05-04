"""Application service for scan API endpoints."""

from __future__ import annotations

from typing import Any

from backend.application.pagination import PaginationParams
from backend.infrastructure.market_data.factory import create_fallback_market_data_provider
from backend.infrastructure.market_data.provider import MarketDataProvider
from backend.infrastructure.tasks.queue import enqueue_task, get_task, list_tasks


class ScanApiService:
    """Creates scan tasks and normalizes explainable scan result payloads."""

    def __init__(self, market_data_provider: MarketDataProvider | None = None):
        self.market_data_provider = market_data_provider or create_fallback_market_data_provider()

    def _market_data_usage(self, provider_name: str) -> dict:
        if hasattr(self.market_data_provider, "usage_metadata"):
            return self.market_data_provider.usage_metadata()
        return {
            "primary_provider": provider_name,
            "actual_provider": provider_name,
            "provider_chain": [provider_name],
            "fallback_used": False,
            "data_quality": "mock" if provider_name == "mock" else "primary",
            "errors": [],
        }

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _confidence(self, item: dict, usage: dict) -> float:
        indicator_count = sum(1 for key in ("signal", "risk_score", "total_score", "vol_ratio", "ma25") if item.get(key) is not None)
        base = 0.35 + min(0.45, indicator_count * 0.09)
        quality_bonus = 0.2 if usage.get("data_quality") != "mock" else 0.05
        fallback_penalty = 0.1 if usage.get("fallback_used") else 0
        return round(max(0.05, min(1.0, base + quality_bonus - fallback_penalty)), 2)

    def _risk_level(self, risk_score: Any, fallback_used: bool, data_quality: str) -> str:
        numeric_risk = self._safe_float(risk_score)
        if numeric_risk >= 75 or data_quality == "mock":
            return "high"
        if numeric_risk >= 50 or fallback_used:
            return "medium"
        return "low"

    def _build_action_suggestion(self, *, risk_level: str, data_quality: str, fallback_used: bool, signal: str | None) -> str:
        if data_quality == "mock":
            return "仅用于链路验证；请切换真实行情源后再做策略判断。"
        if fallback_used:
            return "行情源发生降级；建议复核主行情源恢复后的结果一致性。"
        if risk_level == "high":
            return "风险偏高，建议降低仓位或等待二次确认信号。"
        if signal:
            return "可加入观察池，结合成交量、均线和次日竞价继续验证。"
        return "解释信息不足，建议补充策略信号和关键指标后再决策。"

    def _build_explanation(self, item: dict, usage: dict, strategy_code: str) -> dict:
        score = 70
        reasons = ["进入统一行情样本池", "行情数据通过 provider 健康检查"]
        risk_tags = []
        signal = item.get("signal") or item.get("reason_tag")
        note = item.get("note")
        risk_score = item.get("risk_score")
        total_score = item.get("total_score") or item.get("limit_up_score")
        vol_ratio = item.get("vol_ratio")
        ma25 = item.get("ma25")
        signal_strength = item.get("signal_strength")
        price_to_ma25 = item.get("price_to_ma25")
        risk_level = self._risk_level(risk_score, bool(usage.get("fallback_used")), usage.get("data_quality"))

        if signal:
            reasons.append(f"策略信号：{signal}")
        if note:
            reasons.append(f"策略备注：{note}")
        if total_score is not None:
            score = max(score, min(95, int(float(total_score))))
        if risk_score is not None and float(risk_score) >= 70:
            risk_tags.append("策略风险偏高")
            score -= 10
        if usage.get("fallback_used"):
            score -= 15
            risk_tags.append("行情源降级")
            reasons.append("主行情源不可用，已使用 fallback 数据")
        if usage.get("data_quality") == "mock":
            score -= 20
            risk_tags.append("mock 数据")
            reasons.append("当前结果仅用于链路验证，不应直接用于实盘决策")
        indicators = {
            "sample_rank": item.get("rank") or item.get("index") or None,
            "last_price": item.get("last_price") or item.get("price") or item.get("pick_price") or None,
            "provider_chain_length": len(usage.get("provider_chain") or []),
            "risk_score": risk_score,
            "total_score": total_score,
            "vol_ratio": vol_ratio,
            "ma25": ma25,
            "signal": signal,
            "signal_strength": signal_strength,
            "price_to_ma25": price_to_ma25,
            "price_change_5d": item.get("price_change_5d"),
            "price_change_20d": item.get("price_change_20d"),
            "turnover": item.get("turnover"),
        }
        return {
            "schema_version": "scan-explanation/v2",
            "score": max(score, 0),
            "confidence": self._confidence(item, usage),
            "strategy_code": strategy_code,
            "reasons": reasons,
            "indicators": indicators,
            "indicator_groups": {
                "signal": {
                    "signal": signal,
                    "signal_strength": signal_strength,
                    "note": note,
                    "reason_tag": item.get("reason_tag"),
                },
                "technical": {
                    "ma25": ma25,
                    "vol_ratio": vol_ratio,
                    "price_to_ma25": price_to_ma25,
                    "price_change_5d": item.get("price_change_5d"),
                    "price_change_20d": item.get("price_change_20d"),
                },
                "risk": {
                    "risk_score": risk_score,
                    "risk_level": risk_level,
                    "data_quality": usage.get("data_quality"),
                    "fallback_used": usage.get("fallback_used"),
                },
            },
            "risk_level": risk_level,
            "risk_tags": risk_tags,
            "warnings": ["mock 数据不可用于实盘决策"] if usage.get("data_quality") == "mock" else [],
            "action_suggestion": self._build_action_suggestion(
                risk_level=risk_level,
                data_quality=usage.get("data_quality"),
                fallback_used=bool(usage.get("fallback_used")),
                signal=signal,
            ),
            "market_data_source": usage["actual_provider"],
            "data_quality": usage["data_quality"],
            "fallback_used": usage["fallback_used"],
        }

    def _build_task_explanation(self, *, strategy_code: str, usage: dict, stock_sample: list | None, status: str) -> dict:
        matched_count = len(stock_sample or [])
        queued = status == "queued"
        score = 50 if queued else (70 if matched_count else 0)
        risk_tags = ["等待执行"] if queued else []
        if usage.get("data_quality") == "mock":
            risk_tags.append("mock 数据")
        return {
            "schema_version": "scan-task-explanation/v2",
            "score": score,
            "confidence": 0.3 if queued else min(0.9, 0.45 + matched_count * 0.05),
            "strategy_code": strategy_code,
            "reasons": ["扫描任务已进入队列", "完成后将生成逐标的解释字段"] if queued else ["扫描任务已完成", f"返回 {matched_count} 条样本结果"],
            "indicators": {"matched_count": matched_count, "sample_size": matched_count, "queued": queued},
            "indicator_groups": {
                "sample": {"matched_count": matched_count, "queued": queued},
                "market_data": {
                    "provider_chain_length": len(usage.get("provider_chain") or []),
                    "data_quality": usage.get("data_quality"),
                    "fallback_used": usage.get("fallback_used"),
                },
            },
            "risk_level": "high" if usage.get("data_quality") == "mock" else ("medium" if usage.get("fallback_used") else "low"),
            "risk_tags": risk_tags,
            "warnings": ["任务尚未执行，解释分数仅代表创建时上下文。"] if queued else [],
            "action_suggestion": "等待任务完成后查看逐标的解释。" if queued else "查看样本标的的 signal、风险分和行情质量后再进入观察池。",
            "market_data_source": usage["actual_provider"],
            "data_quality": usage["data_quality"],
            "fallback_used": usage["fallback_used"],
        }

    def _annotate_market_data_item(self, item: dict, usage: dict, strategy_code: str = "all") -> dict:
        item.update(
            {
                "market_data_source": usage["actual_provider"],
                "data_quality": usage["data_quality"],
                "fallback_used": usage["fallback_used"],
                "explanation": self._build_explanation(item, usage, strategy_code),
            }
        )
        return item

    def _run_scan(self, tenant_id: int, strategy_code: str, params: dict) -> dict:
        provider_health = self.market_data_provider.health_check()
        stock_sample = self.market_data_provider.get_stock_list()[:5] if provider_health.ok else []
        usage = self._market_data_usage(provider_health.provider)
        annotated_sample = [self._annotate_market_data_item(item.to_dict(), usage, strategy_code) for item in stock_sample]
        return {
            "tenant_id": tenant_id,
            "strategy_code": strategy_code,
            "params": params,
            "market_data": {
                "provider": usage["actual_provider"],
                "primary_provider": usage["primary_provider"],
                "actual_provider": usage["actual_provider"],
                "provider_chain": usage["provider_chain"],
                "fallback_used": usage["fallback_used"],
                "data_quality": usage["data_quality"],
                "errors": usage["errors"],
                "healthy": provider_health.ok,
                "sample_symbols": annotated_sample,
            },
            "matched_count": len(stock_sample),
            "explanation": self._build_task_explanation(strategy_code=strategy_code, usage=usage, stock_sample=annotated_sample, status="completed"),
        }

    def create_scan(self, tenant_id: int, strategy_code: str | None = None, params: dict | None = None) -> dict:
        normalized_strategy = strategy_code or "all"
        provider_health = self.market_data_provider.health_check()
        usage = self._market_data_usage(provider_health.provider)
        task_explanation = self._build_task_explanation(strategy_code=normalized_strategy, usage=usage, stock_sample=[], status="queued")
        task = enqueue_task(
            "scan.run",
            self._run_scan,
            tenant_id,
            normalized_strategy,
            params or {},
            tenant_id=tenant_id,
            payload={
                "strategy_code": normalized_strategy,
                "params": params or {},
                "provider": usage["actual_provider"],
                "market_data": usage,
                "explanation": task_explanation,
            },
        )
        return {
            "id": task["id"],
            "task_id": task["id"],
            "tenant_id": tenant_id,
            "strategy_code": normalized_strategy,
            "status": task["status"],
            "params": params or {},
            "market_data": {
                "provider": usage["actual_provider"],
                "primary_provider": usage["primary_provider"],
                "actual_provider": usage["actual_provider"],
                "provider_chain": usage["provider_chain"],
                "fallback_used": usage["fallback_used"],
                "data_quality": usage["data_quality"],
                "errors": usage["errors"],
                "healthy": provider_health.ok,
                "sample_symbols": [],
            },
            "explanation": task_explanation,
            "created_at": task["created_at"],
        }

    def list_scans(self, tenant_id: int, pagination: PaginationParams) -> dict:
        scan_tasks = [
            item
            for item in list_tasks(limit=200, name="scan.run")
            if item.get("tenant_id") == tenant_id
        ]
        start = pagination.offset
        end = start + pagination.page_size
        return {
            "items": scan_tasks[start:end],
            "total": len(scan_tasks),
            "page": pagination.page,
            "page_size": pagination.page_size,
            "tenant_id": tenant_id,
        }

    def get_scan_results(self, tenant_id: int, scan_id: str, pagination: PaginationParams) -> dict | None:
        task = get_task(scan_id) or {}
        if not task or task.get("tenant_id") != tenant_id:
            return None
        result = task.get("result") or {}
        market_data = result.get("market_data") or task.get("payload", {}).get("market_data", {})
        items = market_data.get("sample_symbols", [])
        usage = {
            "primary_provider": market_data.get("primary_provider") or market_data.get("provider") or "unknown",
            "actual_provider": market_data.get("actual_provider") or market_data.get("provider") or "unknown",
            "provider_chain": market_data.get("provider_chain") or [],
            "fallback_used": market_data.get("fallback_used", False),
            "data_quality": market_data.get("data_quality") or "unknown",
            "errors": market_data.get("errors") or [],
        }
        strategy_code = result.get("strategy_code") or task.get("payload", {}).get("strategy_code") or "all"
        annotated_items = [item if item.get("explanation") else self._annotate_market_data_item(dict(item), usage, strategy_code) for item in items]
        explanation = result.get("explanation") or task.get("payload", {}).get("explanation") or self._build_task_explanation(
            strategy_code=strategy_code,
            usage=usage,
            stock_sample=annotated_items,
            status="queued" if task.get("status") in {"pending", "running"} else "completed",
        )
        return {
            "items": annotated_items[pagination.offset : pagination.offset + pagination.page_size],
            "total": len(annotated_items),
            "page": pagination.page,
            "page_size": pagination.page_size,
            "tenant_id": tenant_id,
            "scan_id": scan_id,
            "status": task.get("status", "missing"),
            "market_data": {key: value for key, value in market_data.items() if key != "sample_symbols"},
            "explanation": explanation,
            "task": task,
        }
