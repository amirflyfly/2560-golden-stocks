"""Application service for scan API endpoints."""

from __future__ import annotations

from datetime import date
from contextlib import contextmanager
from typing import Any

from backend.application.pagination import PaginationParams
from backend.infrastructure.market_data.factory import create_fallback_market_data_provider
from backend.infrastructure.market_data.provider import MarketDataProvider
from backend.infrastructure.market_data.utils import infer_security_type, normalize_bar_interval
from backend.infrastructure.tasks.queue import enqueue_task, get_task, list_tasks
from backend.strategies import registry


class ScanApiService:
    """Creates scan tasks and normalizes explainable scan result payloads."""

    def __init__(self, market_data_provider: MarketDataProvider | None = None):
        self.market_data_provider = market_data_provider or create_fallback_market_data_provider()

    def _canonical_strategy_code(self, strategy_code: str | None) -> str:
        aliases = {
            "first_limit_up": "FIRST_LIMIT_UP",
            "first_board": "FIRST_LIMIT_UP",
            "FIRST_LIMIT_UP": "FIRST_LIMIT_UP",
            "limit_up_return": "LIMIT_UP_RETURN",
            "limitup_return": "LIMIT_UP_RETURN",
            "LIMIT_UP_RETURN": "LIMIT_UP_RETURN",
            "convertible_bond": "CONVERTIBLE_BOND_LOW_PREMIUM",
            "convertible_bond_low_premium": "CONVERTIBLE_BOND_LOW_PREMIUM",
            "cb_low_premium": "CONVERTIBLE_BOND_LOW_PREMIUM",
            "CONVERTIBLE_BOND_LOW_PREMIUM": "CONVERTIBLE_BOND_LOW_PREMIUM",
            "涨停回马枪": "LIMIT_UP_RETURN",
            "2560": "2560",
            "all": "all",
        }
        normalized = (strategy_code or "all").strip()
        return aliases.get(normalized, normalized)

    def _public_strategy_code(self, strategy_code: str | None) -> str:
        aliases = {
            "FIRST_LIMIT_UP": "first_limit_up",
            "first_board": "first_limit_up",
            "LIMIT_UP_RETURN": "limit_up_return",
            "CONVERTIBLE_BOND_LOW_PREMIUM": "convertible_bond_low_premium",
        }
        normalized = (strategy_code or "all").strip()
        return aliases.get(normalized, normalized)

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

    def _normalize_security_type(self, value: Any = None) -> str:
        text = str(value or "").strip().lower()
        return "" if text in {"", "all", "*", "any"} else text

    def _normalize_scan_params(self, params: dict | None) -> dict:
        normalized = dict(params or {})
        security_type = self._normalize_security_type(
            normalized.get("security_type") or normalized.get("target_security_type")
        )
        bar_interval = normalize_bar_interval(normalized.get("bar_interval") or normalized.get("interval") or "1d")
        adjust = str(normalized.get("adjust") or ("qfq" if bar_interval == "1d" else "none")).strip().lower()
        if bar_interval != "1d":
            adjust = "none"
        normalized.update(
            {
                "security_type": security_type,
                "target_security_type": security_type,
                "bar_interval": bar_interval,
                "interval": bar_interval,
                "adjust": adjust,
                "allow_t0": self._bool_value(normalized.get("allow_t0"), default=security_type == "convertible_bond"),
            }
        )
        return normalized

    def _bool_value(self, value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    def _candidate_security_type(self, item: dict, fallback: str = "") -> str:
        provided = str(item.get("security_type") or item.get("target_security_type") or "").strip().lower()
        return provided or fallback or infer_security_type(
            item.get("symbol") or item.get("code") or item.get("stock_code") or "",
            item.get("name") or item.get("stock_name") or "",
        )

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _first_present(self, *values: Any) -> Any:
        for value in values:
            if value is not None:
                return value
        return None

    def _dict_value(self, value: Any) -> dict:
        return value if isinstance(value, dict) else {}

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
        reasons = []
        risk_tags = []
        indicators_section = self._dict_value(item.get("indicators"))
        phase_section = self._dict_value(item.get("phase"))
        risk_section = self._dict_value(item.get("risk"))
        data_section = self._dict_value(item.get("data"))
        signal = self._first_present(item.get("signal"), item.get("reason_tag"), data_section.get("signal"))
        signal_subtype = self._first_present(
            item.get("signal_subtype"),
            phase_section.get("signal_subtype"),
            data_section.get("signal_subtype"),
        )
        note = item.get("note")
        risk_score = self._first_present(item.get("risk_score"), risk_section.get("risk_score"))
        strategy_score = self._first_present(item.get("score"), data_section.get("score"))
        total_score = self._first_present(
            item.get("total_score"),
            data_section.get("total_score"),
            item.get("limit_up_score"),
            strategy_score,
        )
        vol_ratio = item.get("vol_ratio")
        ma25 = self._first_present(item.get("ma25"), indicators_section.get("ma25"))
        ma60 = self._first_present(item.get("ma60"), indicators_section.get("ma60"))
        ma25_slope_5 = self._first_present(item.get("ma25_slope_5"), indicators_section.get("ma25_slope_5"))
        ma60_slope_10 = self._first_present(item.get("ma60_slope_10"), indicators_section.get("ma60_slope_10"))
        vr5_60 = self._first_present(item.get("vr5_60"), indicators_section.get("vr5_60"))
        vr1_60 = self._first_present(item.get("vr1_60"), indicators_section.get("vr1_60"))
        volume_phase = self._first_present(item.get("volume_phase"), phase_section.get("volume_phase"))
        signal_strength = self._first_present(item.get("signal_strength"), data_section.get("signal_strength"))
        price_to_ma25 = self._first_present(item.get("price_to_ma25"), indicators_section.get("price_to_ma25"))
        risk_level = self._risk_level(risk_score, bool(usage.get("fallback_used")), usage.get("data_quality"))

        primary_reason = item.get("recommend_reason") or item.get("prediction_reason") or note
        if primary_reason:
            reasons.append(f"策略理由：{primary_reason}")
        reasons.extend(["进入统一行情样本池", "行情数据通过 provider 健康检查"])
        if signal:
            reasons.append(f"策略信号：{signal}")
        if signal_subtype:
            reasons.append(f"信号子类型：{signal_subtype}")
        if volume_phase:
            reasons.append(f"量能阶段：{volume_phase}")
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
            "score": strategy_score,
            "total_score": total_score,
            "vol_ratio": vol_ratio,
            "ma25": ma25,
            "ma60": ma60,
            "ma25_slope_5": ma25_slope_5,
            "ma60_slope_10": ma60_slope_10,
            "vr5_60": vr5_60,
            "vr1_60": vr1_60,
            "volume_phase": volume_phase,
            "signal": signal,
            "signal_subtype": signal_subtype,
            "signal_strength": signal_strength,
            "price_to_ma25": price_to_ma25,
            "price_change_5d": item.get("price_change_5d"),
            "price_change_20d": item.get("price_change_20d"),
            "turnover": item.get("turnover"),
            "preselect_score": item.get("preselect_score"),
            "auction_score": item.get("auction_score"),
            "second_board_score": item.get("second_board_score"),
            "second_board_expectation": item.get("second_board_expectation"),
            "security_type": item.get("security_type"),
            "bar_interval": item.get("bar_interval") or item.get("interval"),
            "adjust": item.get("adjust"),
        }
        return {
            "schema_version": "scan-explanation/v2",
            "score": max(score, 0),
            "confidence": self._confidence(item, usage),
            "strategy_code": self._public_strategy_code(strategy_code),
            "reasons": reasons,
            "indicators": indicators,
            "indicator_groups": {
                "signal": {
                    "signal": signal,
                    "signal_subtype": signal_subtype,
                    "signal_strength": signal_strength,
                    "note": note,
                    "reason_tag": item.get("reason_tag"),
                },
                "technical": {
                    "ma25": ma25,
                    "ma60": ma60,
                    "ma25_slope_5": ma25_slope_5,
                    "ma60_slope_10": ma60_slope_10,
                    "vol_ratio": vol_ratio,
                    "vr5_60": vr5_60,
                    "vr1_60": vr1_60,
                    "volume_phase": volume_phase,
                    "price_to_ma25": price_to_ma25,
                    "price_change_5d": item.get("price_change_5d"),
                    "price_change_20d": item.get("price_change_20d"),
                    "preselect_score": item.get("preselect_score"),
                    "auction_score": item.get("auction_score"),
                    "second_board_score": item.get("second_board_score"),
                },
                "risk": {
                    "risk_score": risk_score,
                    "score": strategy_score,
                    "total_score": total_score,
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

    def _build_task_explanation(self, *, strategy_code: str, usage: dict, stock_sample: list | None, status: str, strategy_runner: str = "market_sample", params: dict | None = None) -> dict:
        params = params or {}
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
            "strategy_code": self._public_strategy_code(strategy_code),
            "reasons": ["扫描任务已进入队列", "完成后将生成逐标的解释字段"] if queued else ["扫描任务已完成", f"返回 {matched_count} 条样本结果"],
            "indicators": {
                "matched_count": matched_count,
                "sample_size": matched_count,
                "queued": queued,
                "strategy_runner": strategy_runner,
                "security_type": params.get("security_type") or "",
                "bar_interval": params.get("bar_interval") or params.get("interval") or "1d",
                "adjust": params.get("adjust") or "",
            },
            "indicator_groups": {
                "sample": {"matched_count": matched_count, "queued": queued},
                "strategy": {"runner": strategy_runner, "code": self._public_strategy_code(strategy_code)},
                "data_contract": {
                    "security_type": params.get("security_type") or "",
                    "bar_interval": params.get("bar_interval") or params.get("interval") or "1d",
                    "adjust": params.get("adjust") or "",
                    "allow_t0": bool(params.get("allow_t0")),
                },
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

    def _annotate_market_data_item(self, item: dict, usage: dict, strategy_code: str = "all", params: dict | None = None) -> dict:
        params = params or {}
        security_type = self._candidate_security_type(item, params.get("security_type") or "")
        bar_interval = params.get("bar_interval") or params.get("interval") or item.get("bar_interval") or item.get("interval") or "1d"
        item.update(
            {
                "security_type": security_type,
                "bar_interval": bar_interval,
                "interval": bar_interval,
                "adjust": params.get("adjust") or item.get("adjust") or ("qfq" if bar_interval == "1d" else "none"),
                "market_data_source": usage["actual_provider"],
                "data_quality": usage["data_quality"],
                "fallback_used": usage["fallback_used"],
            }
        )
        item["explanation"] = self._build_explanation(item, usage, strategy_code)
        return item

    def _normalize_strategy_pick(self, item: dict, usage: dict, strategy_code: str, params: dict | None = None) -> dict:
        params = params or {}
        security_type = self._candidate_security_type(item, params.get("security_type") or "")
        bar_interval = params.get("bar_interval") or params.get("interval") or item.get("bar_interval") or item.get("interval") or "1d"
        indicators_section = self._dict_value(item.get("indicators"))
        phase_section = self._dict_value(item.get("phase"))
        risk_section = self._dict_value(item.get("risk"))
        data_section = self._dict_value(item.get("data"))
        normalized = {
            "symbol": item.get("symbol") or item.get("code") or item.get("stock_code") or "",
            "code": item.get("code") or item.get("symbol") or item.get("stock_code") or "",
            "name": item.get("name") or item.get("stock_name") or "",
            "stock_name": item.get("stock_name") or item.get("name") or "",
            "trade_date": item.get("trade_date") or item.get("date") or date.today().isoformat(),
            "last_price": item.get("last_price") or item.get("price") or item.get("pick_price"),
            "pick_price": item.get("pick_price") or item.get("last_price") or item.get("price"),
            "signal": item.get("signal") or item.get("reason_tag") or "",
            "reason_tag": item.get("reason_tag") or item.get("signal") or "",
            "signal_subtype": self._first_present(item.get("signal_subtype"), phase_section.get("signal_subtype"), data_section.get("signal_subtype")),
            "note": item.get("note") or "",
            "risk_score": self._first_present(item.get("risk_score"), risk_section.get("risk_score")),
            "score": self._first_present(item.get("score"), data_section.get("score")),
            "total_score": self._first_present(item.get("total_score"), data_section.get("total_score"), item.get("limit_up_score")),
            "vol_ratio": item.get("vol_ratio"),
            "ma25": self._first_present(item.get("ma25"), indicators_section.get("ma25")),
            "ma60": self._first_present(item.get("ma60"), indicators_section.get("ma60")),
            "ma25_slope_5": self._first_present(item.get("ma25_slope_5"), indicators_section.get("ma25_slope_5")),
            "ma60_slope_10": self._first_present(item.get("ma60_slope_10"), indicators_section.get("ma60_slope_10")),
            "vr5_60": self._first_present(item.get("vr5_60"), indicators_section.get("vr5_60")),
            "vr1_60": self._first_present(item.get("vr1_60"), indicators_section.get("vr1_60")),
            "volume_phase": self._first_present(item.get("volume_phase"), phase_section.get("volume_phase")),
            "signal_strength": self._first_present(item.get("signal_strength"), data_section.get("signal_strength")),
            "price_to_ma25": self._first_present(item.get("price_to_ma25"), indicators_section.get("price_to_ma25")),
            "price_change_5d": item.get("price_change_5d"),
            "price_change_20d": item.get("price_change_20d"),
            "turnover": item.get("turnover"),
            "preselect_score": item.get("preselect_score"),
            "auction_score": item.get("auction_score"),
            "second_board_score": item.get("second_board_score"),
            "second_board_expectation": item.get("second_board_expectation"),
            "recommend_reason": item.get("recommend_reason"),
            "prediction_reason": item.get("prediction_reason"),
            "indicators": item.get("indicators"),
            "phase": item.get("phase"),
            "risk": item.get("risk"),
            "data": item.get("data"),
            "strategy_runner": "registry",
            "security_type": security_type,
            "bar_interval": bar_interval,
            "interval": bar_interval,
            "adjust": params.get("adjust") or item.get("adjust") or ("qfq" if bar_interval == "1d" else "none"),
        }
        normalized.update(
            {
                "market_data_source": usage["actual_provider"],
                "data_quality": usage["data_quality"],
                "fallback_used": usage["fallback_used"],
                "explanation": self._build_explanation(normalized, usage, strategy_code),
            }
        )
        return normalized

    def _run_registered_strategy(self, strategy_code: str, params: dict, usage: dict) -> list[dict]:
        strategy = registry.get(self._canonical_strategy_code(strategy_code))
        if not strategy:
            return []
        target_date = params.get("trade_date") or params.get("date")
        with self._bounded_strategy_scan(strategy, params):
            picks = strategy.scan(target_date)
        return [self._normalize_strategy_pick(dict(item), usage, strategy_code, params) for item in picks]

    @contextmanager
    def _bounded_strategy_scan(self, strategy, params: dict):
        config = getattr(strategy, "config", None)
        strategy_config = config.get("strategy") if isinstance(config, dict) else None
        if not isinstance(strategy_config, dict) and isinstance(config, dict) and "scan_limit" in config:
            strategy_config = config
        if not isinstance(strategy_config, dict):
            yield
            return

        original_scan_limit = strategy_config.get("scan_limit")
        original_select_count = strategy_config.get("select_count")
        full_universe = bool(params.get("full_universe"))
        if full_universe:
            requested_limit = params.get("scan_limit") or original_scan_limit or 6000
            max_limit = 10000
        else:
            requested_limit = params.get("sample_size") or params.get("scan_limit") or 20
            max_limit = 100
        try:
            bounded_limit = max(1, min(int(requested_limit), max_limit))
        except (TypeError, ValueError):
            bounded_limit = 6000 if full_universe else 20
        try:
            strategy_config["scan_limit"] = bounded_limit
            if "select_count" in params:
                strategy_config["select_count"] = max(1, min(int(params.get("select_count") or 1), bounded_limit))
            elif original_select_count is not None and not full_universe:
                strategy_config["select_count"] = min(int(original_select_count), bounded_limit)
            yield
        finally:
            strategy_config["scan_limit"] = original_scan_limit
            strategy_config["select_count"] = original_select_count

    def _market_sample_results(self, usage: dict, strategy_code: str, sample_size: int = 5, params: dict | None = None) -> list[dict]:
        params = params or {}
        requested_type = self._normalize_security_type(params.get("security_type"))
        target_count = max(1, min(int(sample_size or 5), 20))
        sample = []
        for item in self.market_data_provider.get_stock_list():
            payload = item.to_dict()
            security_type = self._candidate_security_type(payload)
            if requested_type and security_type != requested_type:
                continue
            payload["security_type"] = security_type
            sample.append(payload)
            if len(sample) >= target_count:
                break
        return [self._annotate_market_data_item(item, usage, strategy_code, params) for item in sample]

    def _run_scan(self, tenant_id: int, strategy_code: str, params: dict) -> dict:
        params = self._normalize_scan_params(params)
        provider_health = self.market_data_provider.health_check()
        usage = self._market_data_usage(provider_health.provider)
        strategy_runner = "registry"
        errors = list(usage.get("errors") or [])
        allow_market_sample_fallback = not self._bool_value(params.get("disable_market_sample_fallback"), default=False)
        try:
            annotated_sample = self._run_registered_strategy(strategy_code, params, usage) if provider_health.ok else []
            if not annotated_sample and allow_market_sample_fallback:
                strategy_runner = "market_sample"
                annotated_sample = self._market_sample_results(usage, strategy_code, params.get("sample_size", 5), params) if provider_health.ok else []
        except Exception as exc:
            strategy_runner = "market_sample" if allow_market_sample_fallback else "registry"
            errors.append(f"strategy {strategy_code}: {exc}")
            annotated_sample = self._market_sample_results(usage, strategy_code, params.get("sample_size", 5), params) if provider_health.ok and allow_market_sample_fallback else []
        return {
            "tenant_id": tenant_id,
            "strategy_code": self._public_strategy_code(strategy_code),
            "params": params,
            "strategy_runner": strategy_runner,
            "market_data": {
                "provider": usage["actual_provider"],
                "primary_provider": usage["primary_provider"],
                "actual_provider": usage["actual_provider"],
                "provider_chain": usage["provider_chain"],
                "fallback_used": usage["fallback_used"],
                "data_quality": usage["data_quality"],
                "errors": errors,
                "healthy": provider_health.ok,
                "sample_symbols": annotated_sample,
                "security_type": params.get("security_type") or "",
                "bar_interval": params.get("bar_interval") or params.get("interval") or "1d",
                "adjust": params.get("adjust") or "",
            },
            "matched_count": len(annotated_sample),
            "explanation": self._build_task_explanation(
                strategy_code=strategy_code,
                usage={**usage, "errors": errors},
                stock_sample=annotated_sample,
                status="completed",
                strategy_runner=strategy_runner,
                params=params,
            ),
        }

    def create_scan(self, tenant_id: int, strategy_code: str | None = None, params: dict | None = None) -> dict:
        params = self._normalize_scan_params(params)
        normalized_strategy = self._canonical_strategy_code(strategy_code)
        public_strategy = self._public_strategy_code(normalized_strategy)
        provider_health = self.market_data_provider.health_check()
        usage = self._market_data_usage(provider_health.provider)
        task_explanation = self._build_task_explanation(strategy_code=normalized_strategy, usage=usage, stock_sample=[], status="queued", strategy_runner="registry", params=params)
        task = enqueue_task(
            "scan.run",
            self._run_scan,
            tenant_id,
            normalized_strategy,
            params or {},
            tenant_id=tenant_id,
            payload={
                "strategy_code": public_strategy,
                "strategy_code_internal": normalized_strategy,
                "params": params,
                "provider": usage["actual_provider"],
                "market_data": usage,
                "explanation": task_explanation,
            },
        )
        return {
            "id": task["id"],
            "task_id": task["id"],
            "tenant_id": tenant_id,
            "strategy_code": public_strategy,
            "status": task["status"],
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
                "sample_symbols": [],
                "security_type": params.get("security_type") or "",
                "bar_interval": params.get("bar_interval") or params.get("interval") or "1d",
                "adjust": params.get("adjust") or "",
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
        strategy_code = result.get("strategy_code") or task.get("payload", {}).get("strategy_code_internal") or task.get("payload", {}).get("strategy_code") or "all"
        params = self._normalize_scan_params(result.get("params") or task.get("payload", {}).get("params") or {})
        annotated_items = [item if item.get("explanation") else self._annotate_market_data_item(dict(item), usage, strategy_code, params) for item in items]
        explanation = result.get("explanation") or task.get("payload", {}).get("explanation") or self._build_task_explanation(
            strategy_code=strategy_code,
            usage=usage,
            stock_sample=annotated_items,
            status="queued" if task.get("status") in {"pending", "running"} else "completed",
            strategy_runner=result.get("strategy_runner") or "market_sample",
            params=params,
        )
        return {
            "items": annotated_items[pagination.offset : pagination.offset + pagination.page_size],
            "total": len(annotated_items),
            "page": pagination.page,
            "page_size": pagination.page_size,
            "tenant_id": tenant_id,
            "scan_id": scan_id,
            "status": task.get("status", "missing"),
            "strategy_runner": result.get("strategy_runner") or explanation.get("indicators", {}).get("strategy_runner") or "market_sample",
            "market_data": {key: value for key, value in market_data.items() if key != "sample_symbols"},
            "explanation": explanation,
            "task": task,
        }
