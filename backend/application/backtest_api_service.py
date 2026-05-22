"""Application service for strategy backtest API endpoints."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.application.audit_log_service import audit_log_service
from backend.application.data_quality_gate_service import DataQualityGateService
from backend.core.errors import AppError, NotFoundError
from backend.services.strategy_pool_service import get_strategy_backtest, run_backtest
from backend.repositories import market_data_repo
from backend.strategies import registry

SECURITY_TYPES = {"stock", "etf", "index", "convertible_bond", "bond", "fund", "b_share"}
BAR_INTERVALS = {"1d", "15m", "30m", "5m", "1h", "1m"}


class BacktestApiService:
    """Builds validated, API-friendly strategy backtest responses."""

    def __init__(self) -> None:
        self.quality_gate = DataQualityGateService()

    @contextmanager
    def _local_market_data_only(self):
        original = os.environ.get("MARKET_DATA_LOCAL_ONLY")
        os.environ["MARKET_DATA_LOCAL_ONLY"] = "1"
        try:
            yield
        finally:
            if original is None:
                os.environ.pop("MARKET_DATA_LOCAL_ONLY", None)
            else:
                os.environ["MARKET_DATA_LOCAL_ONLY"] = original

    def _validate_date(self, value: str | None, field: str) -> str:
        if not value:
            raise AppError(f"missing {field}")
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise AppError(f"invalid {field}, expected YYYY-MM-DD") from exc
        return value

    def _validate_int(self, value: Any, field: str, *, default: int, minimum: int, maximum: int) -> int:
        if value in (None, ""):
            return default
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise AppError(f"invalid {field}, expected integer") from exc
        if normalized < minimum or normalized > maximum:
            raise AppError(f"invalid {field}, expected {minimum}-{maximum}")
        return normalized

    def _validate_bool(self, value: Any, *, default: bool = True) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(value)

    def _validate_float(self, value: Any, field: str, *, default: float, minimum: float, maximum: float) -> float:
        if value in (None, ""):
            return default
        try:
            normalized = float(value)
        except (TypeError, ValueError) as exc:
            raise AppError(f"invalid {field}, expected number") from exc
        if normalized < minimum or normalized > maximum:
            raise AppError(f"invalid {field}, expected {minimum}-{maximum}")
        return normalized

    def _validate_choice(self, value: Any, field: str, *, default: str, allowed: set[str], aliases: dict[str, str] | None = None) -> str:
        text = str(value or default).strip().lower()
        text = (aliases or {}).get(text, text)
        if text not in allowed:
            raise AppError(f"invalid {field}, expected one of {sorted(allowed)}")
        return text

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            if value is None:
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    def _safe_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on", "limit", "limited", "suspended"}
        return bool(value)

    def _metadata_sources(self, trade: dict[str, Any]) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        for key in ("metadata", "metadata_json", "phase", "indicators", "risk", "data"):
            value = trade.get(key)
            if isinstance(value, dict):
                sources.append(value)
        sources.append(trade)
        return sources

    def _metadata_value(self, trade: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for source in self._metadata_sources(trade):
            for key in keys:
                if key in source and source.get(key) not in (None, ""):
                    return source.get(key)
        return None

    def _extract_trade_metadata(self, trade: dict[str, Any]) -> dict[str, Any]:
        fields = {
            "pullback_days": (
                "pullback_days",
                "retracement_days",
                "callback_days",
                "backtest_pullback_days",
                "days_since_pullback",
            ),
            "volume_shrink_ratio": (
                "volume_shrink_ratio",
                "shrink_ratio",
                "vol_shrink_ratio",
                "volume_ratio",
                "vol_ratio",
                "vr1_60",
                "vr5_60",
            ),
            "drawdown_depth": (
                "drawdown_depth",
                "pullback_depth",
                "retracement_depth",
                "drawdown_pct",
                "max_drawdown",
                "dist25",
            ),
            "market_sentiment": (
                "market_sentiment",
                "sentiment",
                "market_emotion",
                "emotion",
                "market_mood",
                "risk_level",
            ),
            "premium_rate": (
                "premium_rate",
                "conversion_premium_rate",
                "premium_pct",
            ),
            "double_low": (
                "double_low",
                "double_low_score",
            ),
            "remaining_size_yi": (
                "remaining_size_yi",
                "remaining_size",
                "outstanding_yi",
            ),
            "exit_reason": (
                "exit_reason",
                "sell_reason",
            ),
            "allow_t0": (
                "allow_t0",
                "t0_enabled",
            ),
        }
        extracted = {}
        for field, keys in fields.items():
            value = self._metadata_value(trade, keys)
            if value not in (None, ""):
                extracted[field] = value
        return extracted

    def _risk_level(self, *, max_drawdown: float, win_rate: float, total_trades: int) -> str:
        if total_trades < 3 or max_drawdown >= 0.25 or win_rate < 0.35:
            return "high"
        if max_drawdown >= 0.12 or win_rate < 0.5:
            return "medium"
        return "low"

    def _confidence(self, *, total_trades: int, data_quality: str = "primary") -> float:
        sample_score = min(1.0, total_trades / 20) * 0.75
        quality_score = 0.25 if data_quality != "mock" else 0.1
        return round(min(1.0, sample_score + quality_score), 2)

    def _normalize_trade(self, trade: dict[str, Any], index: int) -> dict[str, Any]:
        phase = trade.get("phase") if isinstance(trade.get("phase"), dict) else {}
        signal_subtype = trade.get("signal_subtype") or phase.get("signal_subtype")
        volume_phase = trade.get("volume_phase") or phase.get("volume_phase")
        metadata = self._extract_trade_metadata(trade)
        return {
            "index": index + 1,
            "strategy_code": trade.get("strategy_code"),
            "strategy_name": trade.get("strategy_name"),
            "code": trade.get("code"),
            "name": trade.get("name"),
            "signal": trade.get("signal") or trade.get("reason_tag"),
            "signal_subtype": signal_subtype,
            "volume_phase": volume_phase,
            "signal_date": trade.get("signal_date"),
            "entry_date": trade.get("entry_date"),
            "exit_date": trade.get("exit_date"),
            "holding_days": self._safe_int(trade.get("holding_days")),
            "entry_price": self._safe_float(trade.get("entry_price")),
            "exit_price": self._safe_float(trade.get("exit_price")),
            "return_pct": self._safe_float(trade.get("return_pct")),
            "risk_score": self._safe_float(trade.get("risk_score")),
            "score": self._safe_float(trade.get("score")),
            "execution_flags": {
                "suspended": self._has_flag(trade, ("suspended", "is_suspended", "halted", "is_halted")),
                "limit_up": self._has_flag(trade, ("limit_up", "is_limit_up", "entry_limit_up", "is_entry_limit_up", "limit_up_buy")),
                "limit_down": self._has_flag(trade, ("limit_down", "is_limit_down", "exit_limit_down", "is_exit_limit_down", "limit_down_sell")),
                "t_plus_one": self._has_flag(trade, ("t_plus_one", "t_plus_1", "t1_execution", "next_day_entry")),
            },
            "metadata": metadata,
            "pullback_days": metadata.get("pullback_days"),
            "volume_shrink_ratio": metadata.get("volume_shrink_ratio"),
            "drawdown_depth": metadata.get("drawdown_depth"),
            "market_sentiment": metadata.get("market_sentiment"),
            "note": trade.get("note") or "",
        }

    def _has_flag(self, trade: dict[str, Any], keys: tuple[str, ...]) -> bool:
        flags = trade.get("execution_flags") if isinstance(trade.get("execution_flags"), dict) else {}
        return any(self._safe_bool(trade.get(key)) or self._safe_bool(flags.get(key)) for key in keys)

    def _has_invalid_price(self, raw_trade: dict[str, Any]) -> bool:
        price_keys = ("entry_price", "exit_price")
        present_keys = [key for key in price_keys if key in raw_trade]
        if not present_keys:
            return False
        for key in present_keys:
            value = raw_trade.get(key)
            if value in (None, ""):
                return True
            if self._safe_float(value, default=-1.0) <= 0:
                return True
        return False

    def _constraint_reason(self, raw_trade: dict[str, Any], normalized_trade: dict[str, Any], *, enabled: bool) -> tuple[str, str] | None:
        flags = normalized_trade.get("execution_flags") or {}
        if self._has_invalid_price(raw_trade):
            return ("invalid_price", "invalid_price")
        if enabled and flags.get("suspended"):
            return ("suspended", "suspended_trade")
        if enabled and flags.get("limit_up"):
            return ("limit_up", "limit_up_buy")
        if enabled and flags.get("limit_down"):
            return ("limit_down", "limit_down_sell")
        return None

    def _normalize_skipped_trade(self, raw_trade: dict[str, Any], index: int) -> dict[str, Any]:
        metadata = self._extract_trade_metadata(raw_trade)
        return {
            "index": index + 1,
            "code": raw_trade.get("code"),
            "name": raw_trade.get("name"),
            "signal_date": raw_trade.get("signal_date"),
            "entry_date": raw_trade.get("entry_date") or raw_trade.get("intended_entry_date"),
            "exit_date": raw_trade.get("exit_date") or raw_trade.get("intended_exit_date"),
            "reason": raw_trade.get("reason") or raw_trade.get("skip_reason") or "skipped",
            "action": raw_trade.get("action") or raw_trade.get("blocked_action"),
            "metadata": metadata,
        }

    def _skipped_reason(self, skipped_trade: dict[str, Any]) -> tuple[str, str]:
        reason = str(skipped_trade.get("reason") or "").strip().lower()
        action = str(skipped_trade.get("action") or "").strip().lower()
        text = f"{reason} {action}"
        if "invalid" in text or "price" in text:
            return ("invalid_price", "invalid_price")
        if "suspend" in text or "halt" in text:
            return ("suspended", "suspended_trade")
        if "limit_up" in text or "up_buy" in text:
            return ("limit_up", "limit_up_buy")
        if "limit_down" in text or "down_sell" in text:
            return ("limit_down", "limit_down_sell")
        return ("invalid_price", "invalid_price")

    def _t_plus_one_stats(self, raw_trades: list[dict[str, Any]], skipped_trades: list[dict[str, Any]]) -> dict[str, Any]:
        candidates = raw_trades + skipped_trades
        executed_count = 0
        same_day_count = 0
        unknown_count = 0
        samples = []
        for raw_trade in candidates:
            signal_date = raw_trade.get("signal_date")
            entry_date = raw_trade.get("entry_date") or raw_trade.get("intended_entry_date")
            t1_flag = self._has_flag(raw_trade, ("t_plus_one", "t_plus_1", "t1_execution", "next_day_entry"))
            if t1_flag or (signal_date and entry_date and str(entry_date) > str(signal_date)):
                executed_count += 1
                if len(samples) < 20:
                    samples.append(
                        {
                            "code": raw_trade.get("code"),
                            "signal_date": signal_date,
                            "entry_date": entry_date,
                        }
                    )
            elif signal_date and entry_date and str(entry_date) == str(signal_date):
                same_day_count += 1
            else:
                unknown_count += 1
        return {
            "enabled": True,
            "mode": "next_trading_day_entry",
            "candidate_count": len(candidates),
            "executed_count": executed_count,
            "same_day_count": same_day_count,
            "unknown_count": unknown_count,
            "samples": samples,
        }

    def _apply_trade_constraints(
        self,
        raw_trades: list[dict[str, Any]],
        trades: list[dict[str, Any]],
        *,
        enabled: bool,
        skipped_trades: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        skipped_trades = skipped_trades or []
        reasons = {"invalid_price": 0, "suspended": 0, "limit_up": 0, "limit_down": 0}
        blocked_actions = {"invalid_price": 0, "suspended_trade": 0, "limit_up_buy": 0, "limit_down_sell": 0}
        filtered: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []

        for raw_trade, trade in zip(raw_trades, trades):
            constraint = self._constraint_reason(raw_trade, trade, enabled=enabled)
            if constraint:
                reason, action = constraint
                reasons[reason] += 1
                blocked_actions[action] += 1
                excluded.append(
                    {
                        "index": trade.get("index"),
                        "code": trade.get("code"),
                        "name": trade.get("name"),
                        "reason": reason,
                        "action": action,
                    }
                )
                continue
            filtered.append(trade)

        normalized_skipped = [self._normalize_skipped_trade(trade, index + len(raw_trades)) for index, trade in enumerate(skipped_trades)]
        for skipped in normalized_skipped:
            reason, action = self._skipped_reason(skipped)
            reasons[reason] += 1
            blocked_actions[action] += 1
            excluded.append({**skipped, "reason": reason, "action": action})

        excluded_count = len(excluded)
        candidate_count = len(raw_trades) + len(skipped_trades)
        excluded_ratio = round(excluded_count / candidate_count, 6) if candidate_count else 0.0
        return filtered, {
            "enabled": enabled,
            "included_count": len(filtered),
            "excluded_count": excluded_count,
            "candidate_count": candidate_count,
            "skipped_count": excluded_count,
            "excluded_ratio": excluded_ratio,
            "skipped_ratio": excluded_ratio,
            "reasons": reasons,
            "blocked_actions": blocked_actions,
            "t_plus_one": self._t_plus_one_stats(raw_trades, skipped_trades),
            "excluded_samples": excluded[:20],
        }

    def _summarize_returns(self, returns: list[float]) -> dict[str, Any]:
        if not returns:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "total_return": 0.0,
                "avg_return": 0.0,
                "max_return": 0.0,
                "max_loss": 0.0,
                "max_drawdown": 0.0,
                "profit_factor": 0.0,
            }
        equity_curve = self._build_equity_curve(returns)
        drawdowns = []
        peak = 1.0
        for point in equity_curve:
            equity = self._safe_float(point.get("equity"), 1.0)
            peak = max(peak, equity)
            drawdowns.append((peak - equity) / peak if peak else 0.0)
        winning_returns = [value for value in returns if value > 0]
        losing_returns = [value for value in returns if value <= 0]
        gross_profit = sum(winning_returns)
        gross_loss = abs(sum(losing_returns))
        return {
            "total_trades": len(returns),
            "win_rate": round(len(winning_returns) / len(returns), 6),
            "total_return": round(equity_curve[-1]["return_pct"], 6),
            "avg_return": round(sum(returns) / len(returns), 6),
            "max_return": round(max(returns), 6),
            "max_loss": round(min(returns), 6),
            "max_drawdown": round(max(drawdowns), 6),
            "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0),
        }

    def _signal_attribution(self, trades: list[dict[str, Any]]) -> dict[str, Any]:
        groups: dict[str, dict[str, Any]] = {}
        for trade in trades:
            subtype = str(trade.get("signal_subtype") or trade.get("signal") or "unknown")
            bucket = groups.setdefault(
                subtype,
                {
                    "signal_subtype": subtype,
                    "trade_count": 0,
                    "win_count": 0,
                    "loss_count": 0,
                    "return_sum": 0.0,
                    "avg_return": 0.0,
                    "max_drawdown": 0.0,
                    "volume_phases": {},
                },
            )
            return_pct = self._safe_float(trade.get("return_pct"))
            bucket["trade_count"] += 1
            bucket["win_count"] += 1 if return_pct > 0 else 0
            bucket["loss_count"] += 1 if return_pct <= 0 else 0
            bucket["return_sum"] = round(bucket["return_sum"] + return_pct, 6)
            phase = str(trade.get("volume_phase") or "unknown")
            bucket["volume_phases"][phase] = bucket["volume_phases"].get(phase, 0) + 1

        for bucket in groups.values():
            count = bucket["trade_count"]
            returns = [self._safe_float(item.get("return_pct")) for item in trades if str(item.get("signal_subtype") or item.get("signal") or "unknown") == bucket["signal_subtype"]]
            bucket["win_rate"] = round(bucket["win_count"] / count, 6) if count else 0.0
            bucket["avg_return"] = round(bucket["return_sum"] / count, 6) if count else 0.0
            bucket["max_drawdown"] = self._summarize_returns(returns).get("max_drawdown", 0.0)
        items = sorted(groups.values(), key=lambda item: (-item["trade_count"], item["signal_subtype"]))
        return {"schema_version": "signal-attribution/v1", "items": items}

    def _holding_day_distribution(self, trades: list[dict[str, Any]]) -> dict[str, Any]:
        groups: dict[int, dict[str, Any]] = {}
        for trade in trades:
            holding_days = max(0, self._safe_int(trade.get("holding_days")))
            bucket = groups.setdefault(
                holding_days,
                {
                    "holding_days": holding_days,
                    "trade_count": 0,
                    "win_count": 0,
                    "return_sum": 0.0,
                    "avg_return": 0.0,
                    "win_rate": 0.0,
                },
            )
            return_pct = self._safe_float(trade.get("return_pct"))
            bucket["trade_count"] += 1
            bucket["win_count"] += 1 if return_pct > 0 else 0
            bucket["return_sum"] = round(bucket["return_sum"] + return_pct, 6)

        for bucket in groups.values():
            count = bucket["trade_count"]
            bucket["win_rate"] = round(bucket["win_count"] / count, 6) if count else 0.0
            bucket["avg_return"] = round(bucket["return_sum"] / count, 6) if count else 0.0

        return {
            "schema_version": "holding-day-distribution/v1",
            "items": [groups[key] for key in sorted(groups)],
        }

    def _numeric_bucket(self, value: Any, buckets: tuple[tuple[float, str], ...], default: str = "unknown") -> str:
        try:
            number = abs(float(value))
        except (TypeError, ValueError):
            return default
        for upper_bound, label in buckets:
            if number <= upper_bound:
                return label
        return buckets[-1][1] if buckets else default

    def _attribution_bucket(self, field: str, value: Any) -> str:
        if value in (None, ""):
            return "unknown"
        if field == "pullback_days":
            return str(max(0, self._safe_int(value)))
        if field == "volume_shrink_ratio":
            return self._numeric_bucket(
                value,
                (
                    (0.5, "<=0.50"),
                    (0.8, "0.50-0.80"),
                    (1.0, "0.80-1.00"),
                    (float("inf"), ">1.00"),
                ),
            )
        if field == "drawdown_depth":
            return self._numeric_bucket(
                value,
                (
                    (0.03, "<=3%"),
                    (0.08, "3%-8%"),
                    (0.15, "8%-15%"),
                    (float("inf"), ">15%"),
                ),
            )
        return str(value).strip().lower() or "unknown"

    def _aggregate_dimension(self, trades: list[dict[str, Any]], field: str) -> dict[str, Any]:
        groups: dict[str, dict[str, Any]] = {}
        for trade in trades:
            value = trade.get(field)
            bucket_name = self._attribution_bucket(field, value)
            bucket = groups.setdefault(
                bucket_name,
                {
                    "bucket": bucket_name,
                    "trade_count": 0,
                    "win_count": 0,
                    "loss_count": 0,
                    "return_sum": 0.0,
                    "avg_return": 0.0,
                    "win_rate": 0.0,
                },
            )
            return_pct = self._safe_float(trade.get("return_pct"))
            bucket["trade_count"] += 1
            bucket["win_count"] += 1 if return_pct > 0 else 0
            bucket["loss_count"] += 1 if return_pct <= 0 else 0
            bucket["return_sum"] = round(bucket["return_sum"] + return_pct, 6)

        for bucket in groups.values():
            count = bucket["trade_count"]
            bucket["win_rate"] = round(bucket["win_count"] / count, 6) if count else 0.0
            bucket["avg_return"] = round(bucket["return_sum"] / count, 6) if count else 0.0

        items = sorted(groups.values(), key=lambda item: (-item["trade_count"], item["bucket"]))
        return {"field": field, "items": items}

    def _factor_attribution(self, trades: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "schema_version": "backtest-attribution/v1",
            "pullback_days": self._aggregate_dimension(trades, "pullback_days"),
            "volume_shrink_ratio": self._aggregate_dimension(trades, "volume_shrink_ratio"),
            "drawdown_depth": self._aggregate_dimension(trades, "drawdown_depth"),
            "market_sentiment": self._aggregate_dimension(trades, "market_sentiment"),
        }

    def _normalize_summary(self, result: dict[str, Any], *, include_trades: bool, trade_limit: int, request_options: dict[str, Any] | None = None) -> dict[str, Any]:
        request_options = request_options or {}
        raw_summary = result.get("results") or {}
        raw_trades = [trade for trade in (raw_summary.get("trades") or []) if isinstance(trade, dict)]
        raw_skipped_trades = [trade for trade in (raw_summary.get("skipped_trades") or []) if isinstance(trade, dict)]
        trades = [self._normalize_trade(trade, index) for index, trade in enumerate(raw_trades)]
        trades, execution_constraints = self._apply_trade_constraints(
            raw_trades,
            trades,
            enabled=bool(request_options.get("limit_up_down_guard", True)),
            skipped_trades=raw_skipped_trades,
        )
        returns = [self._safe_float(trade.get("return_pct")) for trade in trades]
        winning_returns = [value for value in returns if value > 0]
        losing_returns = [value for value in returns if value <= 0]
        recomputed_summary = self._summarize_returns(returns) if execution_constraints["excluded_count"] else {}
        total_trades = recomputed_summary.get("total_trades", self._safe_int(raw_summary.get("total_trades"), len(trades)))
        win_rate = recomputed_summary.get("win_rate", self._safe_float(raw_summary.get("win_rate")))
        total_return = recomputed_summary.get("total_return", self._safe_float(raw_summary.get("total_return")))
        estimated_cost = (total_trades * (self._safe_float(request_options.get("fee_bps")) + self._safe_float(request_options.get("slippage_bps"))) * 2) / 10000
        net_total_return = total_return - estimated_cost
        max_drawdown = recomputed_summary.get("max_drawdown", self._safe_float(raw_summary.get("max_drawdown")))
        risk_level = self._risk_level(max_drawdown=max_drawdown, win_rate=win_rate, total_trades=total_trades)
        equity_curve = self._build_equity_curve(returns) if execution_constraints["excluded_count"] else (raw_summary.get("equity_curve") or self._build_equity_curve(returns))
        benchmark_code = request_options.get("benchmark_code") or raw_summary.get("benchmark_code") or "000300"
        benchmark = self._resolve_benchmark(
            code=benchmark_code,
            start_date=request_options.get("start_date"),
            end_date=request_options.get("end_date"),
            fallback_total_return=self._safe_float(
                raw_summary.get("benchmark_total_return"),
                self._safe_float(request_options.get("benchmark_return_pct")),
            ),
            fallback_curve=raw_summary.get("benchmark_curve"),
            points=len(equity_curve),
            prefer_market_data=raw_summary.get("benchmark_curve") is None and "benchmark_return_pct" not in request_options.get("_provided_fields", []),
        )
        benchmark_total_return = benchmark["total_return"]
        benchmark_curve = benchmark["curve"]
        excess_return = net_total_return - benchmark_total_return
        portfolio_curve = self._portfolio_curve(equity_curve, benchmark_curve)
        risk_attribution = self._risk_attribution(
            returns=returns,
            execution_constraints=execution_constraints,
            estimated_cost=estimated_cost,
            max_drawdown=max_drawdown,
            benchmark_total_return=benchmark_total_return,
            net_total_return=net_total_return,
        )
        signal_attribution = self._signal_attribution(trades)
        factor_attribution = self._factor_attribution(trades)

        normalized = {
            **raw_summary,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "total_return": total_return,
            "estimated_cost_return": round(estimated_cost, 6),
            "net_total_return": round(net_total_return, 6),
            "max_drawdown": max_drawdown,
            "avg_return": recomputed_summary.get("avg_return", self._safe_float(raw_summary.get("avg_return"))),
            "max_return": recomputed_summary.get("max_return", self._safe_float(raw_summary.get("max_return"))),
            "max_loss": recomputed_summary.get("max_loss", self._safe_float(raw_summary.get("max_loss"))),
            "sharpe_ratio": self._safe_float(raw_summary.get("sharpe_ratio")),
            "profit_factor": recomputed_summary.get("profit_factor", self._safe_float(raw_summary.get("profit_factor"))),
            "avg_holding_days": self._safe_float(raw_summary.get("avg_holding_days")),
            "avg_win_return": self._safe_float(raw_summary.get("avg_win_return")),
            "avg_loss_return": self._safe_float(raw_summary.get("avg_loss_return")),
            "risk_level": risk_level,
            "raw_trade_count": len(raw_trades),
            "skipped_trade_count": len(raw_skipped_trades),
            "execution_constraints": execution_constraints,
            "return_distribution": {
                "win_count": len(winning_returns),
                "loss_count": len(losing_returns),
                "flat_or_loss_count": len(losing_returns),
                "positive_return_sum": round(sum(winning_returns), 6),
                "negative_return_sum": round(sum(losing_returns), 6),
            },
            "holding_day_distribution": self._holding_day_distribution(trades),
            "equity_curve": equity_curve,
            "benchmark": {
                "code": benchmark_code,
                "total_return": round(benchmark_total_return, 6),
                "excess_return": round(excess_return, 6),
                "curve": benchmark_curve,
                "source": benchmark["source"],
                "data_quality": benchmark["data_quality"],
                "fallback_used": benchmark["fallback_used"],
                "message": benchmark["message"],
                "bars_total": benchmark.get("bars_total"),
                "usable_bars": benchmark.get("usable_bars"),
                "missing_bar_ratio": benchmark.get("missing_bar_ratio"),
            },
            "data_contract": {
                "benchmark_code": benchmark_code,
                "benchmark_source": benchmark["source"],
                "benchmark_data_quality": benchmark["data_quality"],
                "benchmark_fallback_used": benchmark["fallback_used"],
                "backtest_data_policy": "local_only_no_external_provider",
                "external_provider_disabled": True,
                "adjust": request_options.get("adjust") or "qfq",
                "security_type": request_options.get("security_type") or "stock",
                "bar_interval": request_options.get("bar_interval") or "1d",
                "trading_calendar_source": benchmark["source"] if benchmark["source"] != "synthetic" else "strategy_sample",
                "missing_bar_ratio": benchmark.get("missing_bar_ratio"),
                "mock_or_fallback": benchmark["fallback_used"] or benchmark["data_quality"] == "mock",
                "quality_gate": self.quality_gate.decision(
                    "backtest",
                    {
                        "data_quality": benchmark["data_quality"],
                        "market_data_source": benchmark["source"],
                        "fallback_used": benchmark["fallback_used"],
                    },
                    enforce=False,
                    allow_degraded=True,
                ),
            },
            "portfolio_curve": portfolio_curve,
            "risk_attribution": risk_attribution,
            "signal_attribution": signal_attribution,
            "factor_attribution": factor_attribution,
            "experiment": {
                "label": request_options.get("experiment_label") or "current",
                "params": {
                    "holding_days": request_options.get("holding_days"),
                    "max_positions_per_day": request_options.get("max_positions_per_day"),
                    "fee_bps": request_options.get("fee_bps"),
                    "slippage_bps": request_options.get("slippage_bps"),
                    "limit_up_down_guard": request_options.get("limit_up_down_guard"),
                    "benchmark_code": benchmark_code,
                    "security_type": request_options.get("security_type"),
                    "bar_interval": request_options.get("bar_interval"),
                    "adjust": request_options.get("adjust"),
                },
            },
            "trade_page": {
                "items": trades[:trade_limit] if include_trades else [],
                "total": len(trades),
                "limit": trade_limit,
                "has_more": len(trades) > trade_limit,
            },
        }
        return normalized

    def _resolve_benchmark(
        self,
        *,
        code: str,
        start_date: str | None,
        end_date: str | None,
        fallback_total_return: float,
        fallback_curve: list[dict[str, Any]] | None,
        points: int,
        prefer_market_data: bool = True,
    ) -> dict[str, Any]:
        fallback = {
            "curve": fallback_curve or self._build_benchmark_curve(fallback_total_return, points),
            "total_return": fallback_total_return,
            "source": "synthetic",
            "data_quality": "derived",
            "fallback_used": True,
            "message": "synthetic benchmark curve used",
            "bars_total": None,
            "usable_bars": None,
            "missing_bar_ratio": None,
        }
        if not prefer_market_data:
            return fallback
        if not start_date or not end_date:
            return fallback
        local_bars = market_data_repo.get_daily_bars(code, start_date, end_date, adjust="qfq")
        local_closes = [self._decimal_from_bar(item.get("close")) for item in local_bars]
        local_closes = [value for value in local_closes if value is not None and value > 0]
        if len(local_closes) >= 2:
            curve = self._curve_from_closes(local_closes, points)
            sources = sorted({item.get("source") or "local" for item in local_bars})
            return {
                "curve": curve,
                "total_return": curve[-1]["return_pct"],
                "source": "local:" + ",".join(sources),
                "data_quality": "primary",
                "fallback_used": False,
                "message": "benchmark curve built from local data center",
                "bars_total": len(local_bars),
                "usable_bars": len(local_closes),
                "missing_bar_ratio": self._missing_bar_ratio(len(local_bars), len(local_closes)),
            }
        return {
            **fallback,
            "message": "local benchmark data unavailable; external provider disabled for backtest",
            "bars_total": len(local_bars),
            "usable_bars": len(local_closes),
            "missing_bar_ratio": self._missing_bar_ratio(len(local_bars), len(local_closes)),
        }

    def _decimal_from_bar(self, value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None

    def _curve_from_closes(self, closes: list[Decimal], points: int) -> list[dict[str, Any]]:
        first_close = Decimal(closes[0])
        curve = []
        target_points = max(2, points or len(closes))
        for index in range(target_points):
            source_index = min(len(closes) - 1, round(index * (len(closes) - 1) / (target_points - 1)))
            close = Decimal(closes[source_index])
            return_pct = float((close / first_close) - Decimal("1"))
            curve.append({"step": index, "equity": round(1 + return_pct, 6), "return_pct": round(return_pct, 6)})
        return curve

    def _missing_bar_ratio(self, total_bars: int, usable_bars: int) -> float | None:
        if total_bars <= 0:
            return None
        missing = max(0, total_bars - usable_bars)
        return round(missing / total_bars, 6)

    def _build_equity_curve(self, returns: list[float]) -> list[dict[str, Any]]:
        curve = [{"step": 0, "equity": 1.0, "return_pct": 0.0}]
        current = 1.0
        for index, value in enumerate(returns, start=1):
            current *= 1 + value
            curve.append({"step": index, "equity": round(current, 6), "return_pct": round(current - 1, 6)})
        return curve

    def _build_benchmark_curve(self, total_return: float, points: int) -> list[dict[str, Any]]:
        point_count = max(2, points or 2)
        curve = []
        for index in range(point_count):
            progress = index / (point_count - 1)
            return_pct = total_return * progress
            curve.append({"step": index, "equity": round(1 + return_pct, 6), "return_pct": round(return_pct, 6)})
        return curve

    def _portfolio_curve(self, equity_curve: list[dict[str, Any]], benchmark_curve: list[dict[str, Any]]) -> list[dict[str, Any]]:
        points = []
        for index, point in enumerate(equity_curve):
            benchmark = benchmark_curve[min(index, len(benchmark_curve) - 1)] if benchmark_curve else {}
            equity_return = self._safe_float(point.get("return_pct"))
            benchmark_return = self._safe_float(benchmark.get("return_pct"))
            points.append(
                {
                    "step": point.get("step", index),
                    "equity": point.get("equity"),
                    "return_pct": equity_return,
                    "benchmark_equity": benchmark.get("equity"),
                    "benchmark_return_pct": benchmark_return,
                    "excess_return_pct": round(equity_return - benchmark_return, 6),
                }
            )
        return points

    def _risk_attribution(
        self,
        *,
        returns: list[float],
        execution_constraints: dict[str, Any],
        estimated_cost: float,
        max_drawdown: float,
        benchmark_total_return: float,
        net_total_return: float,
    ) -> dict[str, Any]:
        total_count = len(returns)
        loss_count = len([value for value in returns if value <= 0])
        factors = [
            {
                "name": "sample_size",
                "level": "high" if total_count < 3 else "medium" if total_count < 10 else "low",
                "value": total_count,
                "message": "too few trades" if total_count < 3 else "sample size acceptable",
            },
            {
                "name": "drawdown",
                "level": "high" if max_drawdown >= 0.25 else "medium" if max_drawdown >= 0.12 else "low",
                "value": round(max_drawdown, 6),
                "message": "portfolio drawdown pressure",
            },
            {
                "name": "execution_constraints",
                "level": "high" if execution_constraints.get("excluded_count", 0) >= 3 else "medium" if execution_constraints.get("excluded_count", 0) else "low",
                "value": execution_constraints.get("excluded_count", 0),
                "message": "trades excluded by invalid price, suspension, or limit constraints",
            },
            {
                "name": "cost_drag",
                "level": "medium" if estimated_cost > 0.02 else "low",
                "value": round(estimated_cost, 6),
                "message": "fee and slippage drag on returns",
            },
            {
                "name": "benchmark_gap",
                "level": "high" if net_total_return < benchmark_total_return else "low",
                "value": round(net_total_return - benchmark_total_return, 6),
                "message": "excess return versus benchmark",
            },
            {
                "name": "loss_ratio",
                "level": "high" if total_count and loss_count / total_count > 0.6 else "medium" if total_count and loss_count / total_count > 0.4 else "low",
                "value": round(loss_count / total_count, 6) if total_count else 0,
                "message": "share of flat or losing trades",
            },
        ]
        highest = "high" if any(item["level"] == "high" for item in factors) else "medium" if any(item["level"] == "medium" for item in factors) else "low"
        return {"schema_version": "risk-attribution/v1", "factors": factors, "highest_risk": highest}

    def _build_explanation(self, summary: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
        total_trades = self._safe_int(summary.get("total_trades"))
        win_rate = self._safe_float(summary.get("win_rate"))
        total_return = self._safe_float(summary.get("total_return"))
        max_drawdown = self._safe_float(summary.get("max_drawdown"))
        sharpe_ratio = self._safe_float(summary.get("sharpe_ratio"))
        profit_factor = self._safe_float(summary.get("profit_factor"))
        risk_level = summary.get("risk_level") or self._risk_level(max_drawdown=max_drawdown, win_rate=win_rate, total_trades=total_trades)
        confidence = self._confidence(total_trades=total_trades)

        score = 50
        reasons = [f"回测交易 {total_trades} 笔", f"胜率 {win_rate:.2%}"]
        risk_tags: list[str] = []
        warnings: list[str] = []

        if total_return > 0:
            score += 20
            reasons.append(f"累计收益 {total_return:.2%}")
        else:
            score -= 10
            risk_tags.append("收益不足")
            warnings.append("累计收益未转正，需谨慎扩大样本验证。")
        if max_drawdown > 0.2:
            score -= 15
            risk_tags.append("回撤偏高")
            warnings.append("最大回撤超过 20%，应检查止损或仓位控制。")
        if total_trades < 3:
            score -= 10
            risk_tags.append("样本偏少")
            warnings.append("交易样本偏少，解释置信度有限。")
        if sharpe_ratio >= 1:
            score += 8
            reasons.append("夏普表现较好")
        if profit_factor >= 1.5:
            score += 7
            reasons.append("盈亏比具备优势")

        if risk_level == "low" and total_return > 0:
            action_suggestion = "可进入观察池，继续用更长区间和真实行情源复核。"
            verdict = "positive"
        elif risk_level == "high":
            action_suggestion = "暂不建议放大使用，优先优化风控参数并扩大样本。"
            verdict = "cautious"
        else:
            action_suggestion = "适合小样本复盘，需结合市场环境和交易成本继续验证。"
            verdict = "neutral"

        return {
            "schema_version": "backtest-explanation/v2",
            "score": max(0, min(100, score)),
            "confidence": confidence,
            "verdict": verdict,
            "strategy_code": meta.get("strategy_code"),
            "strategy_name": meta.get("strategy_name"),
            "period": {"start_date": meta.get("start_date"), "end_date": meta.get("end_date"), "trade_days": meta.get("trade_days")},
            "reasons": reasons,
            "indicators": {
                "total_trades": total_trades,
                "win_rate": win_rate,
                "total_return": total_return,
                "benchmark_total_return": summary.get("benchmark", {}).get("total_return", 0),
                "excess_return": summary.get("benchmark", {}).get("excess_return", 0),
                "max_drawdown": max_drawdown,
                "sharpe_ratio": sharpe_ratio,
                "profit_factor": profit_factor,
                "avg_holding_days": summary.get("avg_holding_days", 0),
            },
            "indicator_groups": {
                "return": {
                    "total_return": total_return,
                    "avg_return": summary.get("avg_return", 0),
                    "best_trade": summary.get("best_trade"),
                    "worst_trade": summary.get("worst_trade"),
                },
                "risk": {
                    "risk_level": risk_level,
                    "max_drawdown": max_drawdown,
                    "max_loss": summary.get("max_loss", 0),
                },
                "sample": {
                    "total_trades": total_trades,
                    "holding_days": meta.get("holding_days"),
                    "max_positions_per_day": meta.get("max_positions_per_day"),
                },
                "signal_attribution": summary.get("signal_attribution", {}),
                "factor_attribution": summary.get("factor_attribution", {}),
            },
            "risk_level": risk_level,
            "risk_tags": risk_tags,
            "warnings": warnings,
            "action_suggestion": action_suggestion,
            "assumptions": ["回测结果包含配置的手续费、滑点和涨跌停/停牌约束，但仍需用真实成交数据复核。", "结果仅作为策略研究参考，不构成投资建议。"],
        }

    def _build_request_options(self, payload: dict[str, Any]) -> dict[str, Any]:
        provided_fields = {key for key, value in payload.items() if value is not None}
        return {
            "holding_days": self._validate_int(payload.get("holding_days"), "holding_days", default=5, minimum=1, maximum=60),
            "max_positions_per_day": self._validate_int(
                payload.get("max_positions_per_day"),
                "max_positions_per_day",
                default=3,
                minimum=1,
                maximum=20,
            ),
            "trade_limit": self._validate_int(payload.get("trade_limit"), "trade_limit", default=100, minimum=1, maximum=500),
            "include_trades": self._validate_bool(payload.get("include_trades"), default=True),
            "fee_bps": self._validate_float(payload.get("fee_bps"), "fee_bps", default=0.0, minimum=0.0, maximum=200.0),
            "slippage_bps": self._validate_float(payload.get("slippage_bps"), "slippage_bps", default=0.0, minimum=0.0, maximum=500.0),
            "limit_up_down_guard": self._validate_bool(payload.get("limit_up_down_guard"), default=True),
            "benchmark_code": (payload.get("benchmark_code") or "000300").strip() or "000300",
            "security_type": self._validate_choice(payload.get("security_type") or payload.get("target_security_type"), "security_type", default="stock", allowed=SECURITY_TYPES),
            "bar_interval": self._validate_choice(
                payload.get("bar_interval") or payload.get("interval"),
                "bar_interval",
                default="1d",
                allowed=BAR_INTERVALS,
                aliases={"day": "1d", "daily": "1d", "15": "15m", "30": "30m", "60m": "1h"},
            ),
            "adjust": str(payload.get("adjust") or ("none" if str(payload.get("bar_interval") or payload.get("interval") or "1d").lower() != "1d" else "qfq")).strip().lower(),
            "experiment_label": (payload.get("experiment_label") or "current").strip() or "current",
            "benchmark_return_pct": self._validate_float(
                payload.get("benchmark_return_pct"),
                "benchmark_return_pct",
                default=0.0,
                minimum=-1.0,
                maximum=1.0,
            ),
            "_provided_fields": sorted(provided_fields),
        }

    def _normalize_param_groups(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        groups = payload.get("param_groups") or []
        if not groups:
            return []
        if not isinstance(groups, list):
            raise AppError("param_groups must be a list")
        if len(groups) > 6:
            raise AppError("param_groups supports at most 6 groups")
        normalized = []
        for index, group in enumerate(groups, start=1):
            if not isinstance(group, dict):
                raise AppError("param_groups items must be objects")
            normalized.append({"label": group.get("label") or f"group-{index}", "payload": {**payload, **group}})
        return normalized

    def _run_single_backtest(self, strategy_code: str, start_date: str, end_date: str, options: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        options = {**options, "start_date": start_date, "end_date": end_date}
        with self._local_market_data_only():
            raw = run_backtest(
                strategy_code,
                start_date,
                end_date,
                holding_days=options["holding_days"],
                max_positions_per_day=options["max_positions_per_day"],
            )
        if not raw.get("success"):
            raise AppError(raw.get("message") or "backtest failed")
        meta = {
            **(raw.get("meta") or {}),
            "request_options": options,
            "holding_days": options["holding_days"],
            "max_positions_per_day": options["max_positions_per_day"],
        }
        summary = self._normalize_summary(raw, include_trades=options["include_trades"], trade_limit=options["trade_limit"], request_options=options)
        return raw, meta, summary

    def run(self, tenant_id: int, strategy_code: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        if not registry.get(strategy_code):
            raise NotFoundError("strategy not found")
        start_date = self._validate_date(payload.get("start_date"), "start_date")
        end_date = self._validate_date(payload.get("end_date"), "end_date")
        if start_date > end_date:
            raise AppError("start_date must be before or equal to end_date")
        options = self._build_request_options(payload)

        _, meta, summary = self._run_single_backtest(strategy_code, start_date, end_date, options)
        parameter_comparison = []
        for group in self._normalize_param_groups(payload):
            group_options = self._build_request_options({**group["payload"], "include_trades": False, "trade_limit": 1})
            _, group_meta, group_summary = self._run_single_backtest(strategy_code, start_date, end_date, group_options)
            parameter_comparison.append(
                {
                    "label": group["label"],
                    "params": {
                        "holding_days": group_options["holding_days"],
                        "max_positions_per_day": group_options["max_positions_per_day"],
                        "fee_bps": group_options["fee_bps"],
                        "slippage_bps": group_options["slippage_bps"],
                        "benchmark_code": group_options["benchmark_code"],
                        "security_type": group_options["security_type"],
                        "bar_interval": group_options["bar_interval"],
                    },
                    "summary": {
                        "total_trades": group_summary["total_trades"],
                        "win_rate": group_summary["win_rate"],
                        "total_return": group_summary["total_return"],
                        "net_total_return": group_summary["net_total_return"],
                        "max_drawdown": group_summary["max_drawdown"],
                        "risk_level": group_summary["risk_level"],
                        "excess_return": group_summary["benchmark"]["excess_return"],
                        "highest_risk": group_summary["risk_attribution"]["highest_risk"],
                    },
                    "explanation": self._build_explanation(group_summary, group_meta),
                }
            )
        return {
            "tenant_id": tenant_id,
            "strategy_code": strategy_code,
            "summary": summary,
            "meta": meta,
            "explanation": self._build_explanation(summary, meta),
            "parameter_comparison": parameter_comparison,
        }

    def history(self, tenant_id: int, strategy_code: str, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        if not registry.get(strategy_code):
            raise NotFoundError("strategy not found")
        items = get_strategy_backtest(strategy_code)
        normalized_items = []
        for item in items:
            summary = {
                "total_trades": item.get("total_trades"),
                "win_rate": item.get("win_rate"),
                "avg_return": item.get("avg_return"),
                "max_return": item.get("max_return"),
                "max_drawdown": item.get("max_drawdown"),
                "sharpe_ratio": item.get("sharpe_ratio"),
                "total_return": item.get("total_return"),
            }
            meta = {"strategy_code": strategy_code, "start_date": item.get("start_date"), "end_date": item.get("end_date")}
            normalized_items.append({**item, "summary": summary, "explanation": self._build_explanation(summary, meta)})
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "tenant_id": tenant_id,
            "strategy_code": strategy_code,
            "items": normalized_items[start:end],
            "total": len(normalized_items),
            "page": page,
            "page_size": page_size,
        }

    def detail(self, tenant_id: int, strategy_code: str, backtest_id: int) -> dict[str, Any]:
        if not registry.get(strategy_code):
            raise NotFoundError("strategy not found")
        item = next(
            (
                candidate
                for candidate in get_strategy_backtest(strategy_code)
                if self._safe_int(candidate.get("id"), default=-1) == backtest_id
            ),
            None,
        )
        if item is None:
            raise NotFoundError("backtest not found")
        summary = {
            "total_trades": item.get("total_trades"),
            "win_rate": item.get("win_rate"),
            "avg_return": item.get("avg_return"),
            "max_return": item.get("max_return"),
            "max_drawdown": item.get("max_drawdown"),
            "sharpe_ratio": item.get("sharpe_ratio"),
            "total_return": item.get("total_return"),
        }
        meta = {
            "strategy_code": strategy_code,
            "start_date": item.get("start_date"),
            "end_date": item.get("end_date"),
            "backtest_date": item.get("backtest_date"),
        }
        audit_items = audit_log_service.list_logs(
            tenant_id=tenant_id,
            action="strategy.backtest.create",
            limit=20,
        )["items"]
        audit_trail = [
            log
            for log in audit_items
            if str(log.get("resource_id") or "") == str(strategy_code)
        ]
        return {
            "tenant_id": tenant_id,
            "strategy_code": strategy_code,
            "item": {**item, "summary": summary, "explanation": self._build_explanation(summary, meta)},
            "audit_trail": audit_trail,
        }


backtest_api_service = BacktestApiService()
