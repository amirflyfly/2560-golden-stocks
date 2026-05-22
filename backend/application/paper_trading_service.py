"""Paper trading orchestration for strategy production signals."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from math import floor
from typing import Any

from backend.application.data_quality_gate_service import DataQualityGateService
from backend.application.live_broker_service import BrokerAdapter
from backend.application.pick_api_service import PickApiService
from backend.infrastructure.market_data.utils import normalize_bar_interval
from backend.repositories import market_data_repo
from backend.repositories import paper_trading_repo


LIMIT_UP_RETURN_CODE = "LIMIT_UP_RETURN"
LIMIT_UP_RETURN_BUY_SUBTYPE = "breakout_confirmed"
FIRST_LIMIT_UP_CODE = "FIRST_LIMIT_UP"
FIRST_LIMIT_UP_BUY_SUBTYPE = "auction_confirmed"
CONVERTIBLE_BOND_LOW_PREMIUM_CODE = "CONVERTIBLE_BOND_LOW_PREMIUM"


DEFAULT_EXIT_RULES = {
    "2560": {
        "stop_loss_pct": "-0.08",
        "take_profit_pct": "0.15",
        "max_holding_days": 20,
        "technical_exit_enabled": True,
    },
    FIRST_LIMIT_UP_CODE: {
        "stop_loss_pct": "-0.06",
        "take_profit_pct": "0.12",
        "max_holding_days": 5,
        "technical_exit_enabled": True,
    },
    LIMIT_UP_RETURN_CODE: {
        "stop_loss_pct": "-0.05",
        "take_profit_pct": "0.10",
        "max_holding_days": 7,
        "technical_exit_enabled": True,
    },
    CONVERTIBLE_BOND_LOW_PREMIUM_CODE: {
        "stop_loss_pct": "-0.06",
        "take_profit_pct": None,
        "take_profit_price": "130",
        "sell_premium_rate": "0.40",
        "max_holding_days": 20,
        "technical_exit_enabled": False,
        "allow_t0": True,
    },
}
DEFAULT_EXIT_RULE = DEFAULT_EXIT_RULES["2560"]


class PaperTradingService:
    def __init__(self) -> None:
        self.pick_service = PickApiService()
        self.quality_gate = DataQualityGateService()

    def _decimal(self, value: Any, default: Decimal = Decimal("0")) -> Decimal:
        if value in (None, ""):
            return default
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return default

    def _bool_value(self, value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    def _env_decimal(self, name: str, default: str) -> Decimal:
        return self._decimal(os.getenv(name), Decimal(default))

    def _env_bool(self, name: str) -> bool | None:
        value = os.getenv(name)
        if value is None:
            return None
        return self._bool_value(value)

    def _strategy_env_suffix(self, strategy_code: str) -> str:
        return "".join(ch if ch.isalnum() else "_" for ch in str(strategy_code or "").strip().upper())

    def _strategy_code(self, strategy: dict | None) -> str:
        return str((strategy or {}).get("code") or "").strip().upper()

    def _optional_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        return float(self._decimal(value))

    def _ratio_value(self, value: Any, *, percent_key: bool = False) -> Decimal | None:
        if value in (None, ""):
            return None
        ratio = self._decimal(value)
        if percent_key or ratio > Decimal("1"):
            return ratio / Decimal("100")
        return ratio

    def _premium_rate(self, *sources: dict | None) -> Decimal | None:
        nested_sources: list[dict] = []
        for source in sources:
            if not isinstance(source, dict):
                continue
            for key in ("premium_rate", "premium", "convertible_premium_rate", "conversion_premium_rate"):
                ratio = self._ratio_value(source.get(key))
                if ratio is not None:
                    return ratio
            for key in ("premium_pct", "premium_percent", "premium_rate_pct"):
                ratio = self._ratio_value(source.get(key), percent_key=True)
                if ratio is not None:
                    return ratio
            for key in ("indicators", "metadata", "snapshot"):
                nested = source.get(key)
                if isinstance(nested, dict):
                    nested_sources.append(nested)
        for source in nested_sources:
            ratio = self._premium_rate(source)
            if ratio is not None:
                return ratio
        return None

    def _exit_source_context(self, position: dict, open_link: dict | None) -> dict:
        open_link = open_link or {}
        link_metadata = open_link.get("metadata") if isinstance(open_link.get("metadata"), dict) else {}
        position_metadata = position.get("metadata") if isinstance(position.get("metadata"), dict) else {}
        if not position_metadata and isinstance(position.get("metadata_json"), dict):
            position_metadata = position.get("metadata_json") or {}
        buy_order = {}
        if open_link.get("buy_order_id") and hasattr(paper_trading_repo, "get_order"):
            buy_order = paper_trading_repo.get_order(int(open_link["buy_order_id"])) or {}
        order_metadata = buy_order.get("metadata") if isinstance(buy_order.get("metadata"), dict) else {}
        candidate = order_metadata.get("candidate") if isinstance(order_metadata.get("candidate"), dict) else {}
        candidate_metadata = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
        sell_model = {}
        for source in (position_metadata, link_metadata, order_metadata, candidate_metadata):
            model = source.get("sell_model") if isinstance(source, dict) else None
            if isinstance(model, dict):
                sell_model.update(model)

        strategy_code = (
            position_metadata.get("strategy_code")
            or link_metadata.get("strategy_code")
            or order_metadata.get("strategy_code")
            or candidate.get("strategy_code")
            or buy_order.get("strategy_code")
            or position.get("strategy_code")
            or ""
        )
        signal_subtype = (
            position_metadata.get("signal_subtype")
            or link_metadata.get("signal_subtype")
            or order_metadata.get("signal_subtype")
            or candidate.get("signal_subtype")
            or candidate.get("signal")
            or candidate.get("reason_tag")
            or position.get("signal_subtype")
            or ""
        )
        return {
            "strategy_code": str(strategy_code or "").strip().upper(),
            "signal_subtype": str(signal_subtype or "").strip().lower(),
            "open_link": open_link,
            "buy_order": buy_order,
            "order_metadata": order_metadata,
            "candidate": candidate,
            "sell_model": sell_model,
        }

    def _param_override(self, params: dict, key: str, strategy_code: str = "") -> tuple[Any, str]:
        suffix = self._strategy_env_suffix(strategy_code)
        strategy_param_keys = []
        if strategy_code:
            strategy_param_keys.extend(
                [
                    f"{strategy_code.lower()}_{key}",
                    f"{strategy_code.upper()}_{key}",
                    f"{suffix.lower()}_{key}",
                ]
            )
        for param_key in [*strategy_param_keys, key]:
            if param_key in params:
                return params.get(param_key), "params"

        env_names = []
        if suffix:
            env_names.append(f"PAPER_{suffix}_{key.upper()}")
        env_names.append(f"PAPER_{key.upper()}")
        for env_name in env_names:
            value = os.getenv(env_name)
            if value is not None:
                return value, env_name
        return None, ""

    def _exit_plan(self, position: dict, params: dict, source_context: dict | None = None) -> dict:
        source_context = source_context or {}
        strategy_code = str(source_context.get("strategy_code") or position.get("strategy_code") or "").strip().upper()
        signal_subtype = str(source_context.get("signal_subtype") or position.get("signal_subtype") or "").strip().lower()
        rule = dict(DEFAULT_EXIT_RULES.get(strategy_code, DEFAULT_EXIT_RULE))
        sell_model = source_context.get("sell_model") if isinstance(source_context.get("sell_model"), dict) else {}
        for key in ("stop_loss_pct", "take_profit_pct", "take_profit_price", "sell_premium_rate", "max_holding_days"):
            if key in sell_model:
                rule[key] = sell_model.get(key)
        source = f"default:{strategy_code or '2560'}" if strategy_code in DEFAULT_EXIT_RULES else "default:2560"

        stop_loss_raw, stop_loss_source = self._param_override(params, "stop_loss_pct", strategy_code)
        take_profit_raw, take_profit_source = self._param_override(params, "take_profit_pct", strategy_code)
        take_profit_price_raw, take_profit_price_source = self._param_override(params, "take_profit_price", strategy_code)
        sell_premium_raw, sell_premium_source = self._param_override(params, "sell_premium_rate", strategy_code)
        max_holding_raw, max_holding_source = self._param_override(params, "max_holding_days", strategy_code)
        technical_raw, technical_source = self._param_override(params, "technical_exit_enabled", strategy_code)
        allow_t0_raw, allow_t0_source = self._param_override(params, "allow_t0", strategy_code)

        return {
            "strategy_code": strategy_code,
            "signal_subtype": signal_subtype,
            "stop_loss_pct": float(self._decimal(stop_loss_raw if stop_loss_raw is not None else rule["stop_loss_pct"])),
            "take_profit_pct": self._optional_float(take_profit_raw if take_profit_raw is not None else rule.get("take_profit_pct")),
            "take_profit_price": self._optional_float(take_profit_price_raw if take_profit_price_raw is not None else rule.get("take_profit_price")),
            "sell_premium_rate": self._optional_float(sell_premium_raw if sell_premium_raw is not None else rule.get("sell_premium_rate")),
            "max_holding_days": int(max_holding_raw if max_holding_raw is not None else rule["max_holding_days"]),
            "technical_exit_enabled": self._bool_value(
                technical_raw,
                default=bool(rule["technical_exit_enabled"]),
            ),
            "allow_t0": self._bool_value(allow_t0_raw, default=bool(rule.get("allow_t0", False))),
            "reason": {
                "source": source,
                "stop_loss_pct": stop_loss_source or source,
                "take_profit_pct": take_profit_source or source,
                "take_profit_price": take_profit_price_source or source,
                "sell_premium_rate": sell_premium_source or source,
                "max_holding_days": max_holding_source or source,
                "technical_exit_enabled": technical_source or source,
                "allow_t0": allow_t0_source or source,
            },
        }

    def exit_plan_for_position(self, tenant_id: int, account_id: int, position: dict, params: dict | None = None) -> dict:
        symbol = str(position.get("symbol") or "").strip()
        open_link = paper_trading_repo.get_open_signal_review_link_for_symbol(tenant_id, account_id, symbol) or {}
        source_context = self._exit_source_context(position, open_link)
        return self._exit_plan(position, params or {}, source_context)

    def _strategy_config_value(self, strategy: dict | None, params: dict | None, keys: tuple[str, ...]) -> Any:
        strategy = strategy or {}
        params = params or {}
        sources: list[dict] = []
        for key in ("config", "config_json", "parameters", "params"):
            value = strategy.get(key)
            if isinstance(value, dict):
                sources.append(value)
        sources.extend([strategy, params])
        for source in sources:
            for key in keys:
                if key in source:
                    return source.get(key)
        return None

    def _strategy_kill_switch(self, strategy: dict | None, params: dict | None = None) -> tuple[bool, str]:
        keys = (
            "paper_trading_kill_switch",
            "paper_trade_kill_switch",
            "paper_kill_switch",
            "trading_kill_switch",
            "kill_switch",
            "paper_trading_disabled",
        )
        value = self._strategy_config_value(strategy, params, keys)
        if value is not None:
            return self._bool_value(value), "strategy_config"

        strategy_code = self._strategy_code(strategy)
        suffix = "".join(ch if ch.isalnum() else "_" for ch in strategy_code)
        env_names = []
        if suffix:
            env_names.extend([f"PAPER_TRADING_KILL_SWITCH_{suffix}", f"PAPER_TRADING_DISABLED_{suffix}"])
        env_names.extend(["PAPER_TRADING_KILL_SWITCH", "PAPER_TRADING_DISABLED"])
        for env_name in env_names:
            env_value = self._env_bool(env_name)
            if env_value is not None:
                return env_value, env_name
        return False, ""

    def _is_production_mode(self, params: dict | None = None) -> bool:
        params = params or {}
        if "production_mode" in params and self._bool_value(params.get("production_mode")):
            return True
        for key in ("mode", "run_mode", "execution_mode", "environment"):
            value = str(params.get(key) or "").strip().lower()
            if value in {"prod", "production", "live"}:
                return True
        env_mode = str(os.getenv("APP_ENV") or os.getenv("FLASK_ENV") or os.getenv("ENVIRONMENT") or "").strip().lower()
        return env_mode in {"prod", "production"}

    def _candidate_subtype(self, candidate: dict) -> str:
        return str(candidate.get("signal_subtype") or candidate.get("signal") or candidate.get("reason_tag") or "").strip().lower()

    def _quality_gate_reason(self, candidate: dict, params: dict | None = None) -> str:
        return self.quality_gate.paper_trade_block_reason(candidate, params)

    def _executable_signal_block_reason(self, candidate: dict, params: dict | None = None) -> str:
        params = params or {}
        if self._bool_value(params.get("allow_non_executable_signals")):
            return ""
        runner = str(candidate.get("strategy_runner") or "").strip().lower()
        if runner == "market_sample":
            return "market_sample_not_executable"
        explicit = candidate.get("executable_signal")
        if explicit is not None:
            return "" if self._bool_value(explicit) else "non_executable_signal"
        signal_type = str(candidate.get("signal_type") or candidate.get("side") or "").strip().upper()
        if signal_type and signal_type != "BUY":
            return "non_buy_signal"
        return ""

    def _limit_up_return_skip_reason(self, strategy: dict, candidate: dict) -> str:
        if self._strategy_code(strategy) != LIMIT_UP_RETURN_CODE:
            return ""
        subtype = self._candidate_subtype(candidate)
        if subtype == LIMIT_UP_RETURN_BUY_SUBTYPE:
            return ""
        if subtype == "pullback_setup":
            return "limit_up_return_observation_only"
        if subtype == "failed_pullback":
            return "limit_up_return_failed_pullback"
        return "limit_up_return_unconfirmed_signal"

    def _first_limit_up_skip_reason(self, strategy: dict, candidate: dict) -> str:
        if self._strategy_code(strategy) != FIRST_LIMIT_UP_CODE:
            return ""
        subtype = self._candidate_subtype(candidate)
        if subtype == FIRST_LIMIT_UP_BUY_SUBTYPE:
            return ""
        if subtype == "preopen_watch":
            return "first_limit_up_auction_pending"
        if subtype == "auction_rejected":
            return "first_limit_up_auction_rejected"
        return "first_limit_up_unconfirmed_signal"

    def _snapshot_flag(self, snapshot: dict | None, candidate: dict | None, keys: tuple[str, ...]) -> bool:
        for source in (snapshot or {}, candidate or {}):
            for key in keys:
                if key in source and self._bool_value(source.get(key)):
                    return True
        return False

    def _snapshot_text_contains(self, snapshot: dict | None, candidate: dict | None, needles: tuple[str, ...]) -> bool:
        for source in (snapshot or {}, candidate or {}):
            for key in ("status", "trading_status", "trade_status", "limit_status", "market_status"):
                text = str(source.get(key) or "").strip().lower()
                if text and any(needle in text for needle in needles):
                    return True
        return False

    def _suspended_reason(self, snapshot: dict | None, candidate: dict | None = None) -> str:
        if self._snapshot_flag(snapshot, candidate, ("is_suspended", "suspended", "halted", "is_halted")):
            return "suspended"
        if self._snapshot_text_contains(snapshot, candidate, ("suspended", "halted", "pause", "停牌")):
            return "suspended"
        return ""

    def _limit_rate(self, snapshot: dict | None, candidate: dict | None, direction: str) -> Decimal:
        keys = (
            ("limit_up_rate", "up_limit_rate", "limit_rate")
            if direction == "up"
            else ("limit_down_rate", "down_limit_rate", "limit_rate")
        )
        for source in (snapshot or {}, candidate or {}):
            for key in keys:
                value = self._decimal(source.get(key), Decimal("-1"))
                if value > 0:
                    return value if value < 1 else value / Decimal("100")
        indicators = (candidate or {}).get("indicators")
        if isinstance(indicators, dict):
            rule = indicators.get("limit_rule")
            if isinstance(rule, dict):
                value = self._decimal(rule.get("percent"), Decimal("-1"))
                if value > 0:
                    return value if value < 1 else value / Decimal("100")
        return Decimal("0.10")

    def _computed_limit_hit(self, snapshot: dict | None, candidate: dict | None, direction: str) -> bool:
        source = snapshot or candidate or {}
        prev_close = self._decimal(source.get("prev_close"))
        price = self._decimal(source.get("last_price") or source.get("price") or source.get("pick_price"))
        if prev_close <= 0 or price <= 0:
            return False
        rate = self._limit_rate(snapshot, candidate, direction)
        limit_price = prev_close * (Decimal("1") + rate if direction == "up" else Decimal("1") - rate)
        tolerance = max(Decimal("0.01"), limit_price * Decimal("0.001"))
        return price >= limit_price - tolerance if direction == "up" else price <= limit_price + tolerance

    def _buy_block_reason(self, snapshot: dict | None, candidate: dict, *, production_mode: bool) -> str:
        suspended = self._suspended_reason(snapshot, candidate)
        if suspended:
            return suspended
        if not snapshot and production_mode:
            return "missing_realtime_snapshot"
        if self._snapshot_flag(
            snapshot,
            candidate,
            ("is_limit_up", "limit_up", "at_limit_up", "one_word_limit_up", "is_one_word_limit_up", "one_price_limit_up"),
        ):
            return "limit_up"
        if self._snapshot_text_contains(snapshot, candidate, ("limit_up", "涨停", "one_word", "一字")):
            return "limit_up"
        if self._computed_limit_hit(snapshot, candidate, "up"):
            return "limit_up"
        return ""

    def _sell_block_reason(self, snapshot: dict | None, position: dict) -> str:
        suspended = self._suspended_reason(snapshot, position)
        if suspended:
            return suspended
        if self._snapshot_flag(snapshot, position, ("is_limit_down", "limit_down", "at_limit_down")):
            return "limit_down"
        if self._snapshot_text_contains(snapshot, position, ("limit_down", "跌停")):
            return "limit_down"
        if self._computed_limit_hit(snapshot, position, "down"):
            return "limit_down"
        return ""

    def _reason_counts(self, items: list[dict]) -> dict:
        counts: dict[str, int] = {}
        for item in items:
            reason = str(item.get("reason") or "unknown")
            counts[reason] = counts.get(reason, 0) + 1
        return counts

    def _execution_report(self, *, skipped: list[dict], blocked: list[dict], sample_count: int) -> dict:
        non_executable = len(skipped) + len(blocked)
        ratio = round(non_executable / sample_count, 4) if sample_count > 0 else 0
        return {
            "sample_count": sample_count,
            "skipped_count": len(skipped),
            "blocked_count": len(blocked),
            "non_executable_count": non_executable,
            "non_executable_sample_ratio": ratio,
            "unfilled_sample_ratio": ratio,
            "skipped_reasons": self._reason_counts(skipped),
            "blocked_reasons": self._reason_counts(blocked),
        }

    def ensure_default_account(self, tenant_id: int, params: dict | None = None) -> dict:
        params = params or {}
        return paper_trading_repo.ensure_default_account(
            tenant_id,
            name=str(params.get("paper_account_name") or os.getenv("PAPER_ACCOUNT_NAME") or "Default Paper Account"),
            initial_cash=params.get("initial_cash") or os.getenv("PAPER_INITIAL_CASH") or Decimal("1000000"),
        )

    def summary(self, tenant_id: int, account_id: int | None = None) -> dict:
        return paper_trading_repo.summary(tenant_id, account_id)

    def mark_to_market(self, tenant_id: int, account_id: int | None = None, payload: dict | None = None) -> dict:
        payload = payload or {}
        requested_account_id = int(account_id or payload.get("account_id") or 0)
        if not requested_account_id:
            account = self.ensure_default_account(tenant_id, payload)
            requested_account_id = int(account.get("id") or 0)
        positions = paper_trading_repo.list_positions(tenant_id, requested_account_id or None, active_only=True)
        updated = []
        missing = []
        stale = []
        for position in positions:
            symbol = str(position.get("symbol") or "").strip()
            if not symbol:
                continue
            snapshot = market_data_repo.get_latest_snapshot(symbol)
            price = self._decimal((snapshot or {}).get("last_price"))
            if price <= 0:
                missing.append({"symbol": symbol, "reason": "missing_latest_snapshot"})
                continue
            trade_time = str((snapshot or {}).get("trade_time") or "")
            if trade_time and trade_time[:10] != date.today().isoformat():
                stale.append({"symbol": symbol, "trade_time": trade_time, "source": (snapshot or {}).get("source")})
            item = paper_trading_repo.update_position_market_price(
                tenant_id,
                int(position.get("account_id") or requested_account_id),
                symbol,
                price,
            )
            if item:
                updated.append({"position": item, "snapshot": snapshot or {}})
        return {
            "schema_version": "paper-mark-to-market/v1",
            "tenant_id": int(tenant_id or 0),
            "account_id": requested_account_id or None,
            "updated": len(updated),
            "missing": missing,
            "stale": stale,
            "items": updated,
            "summary": self.summary(tenant_id, requested_account_id or None),
        }

    def apply_strategy_scan(self, tenant_id: int, strategy: dict, scan: dict | None, params: dict | None = None) -> dict:
        params = params or {}
        if not scan:
            return {"enabled": False, "reason": "no scan result", "orders": [], "fills": [], "summary": self.summary(tenant_id)}
        kill_switch_enabled, kill_switch_source = self._strategy_kill_switch(strategy, params)
        if kill_switch_enabled:
            summary = self.summary(tenant_id)
            reason = "strategy_kill_switch"
            blocked = [{"symbol": None, "reason": reason, "source": kill_switch_source}]
            report = self._execution_report(skipped=[], blocked=blocked, sample_count=0)
            return {
                "enabled": False,
                "reason": reason,
                "orders": [],
                "fills": [],
                "exits": {"orders": [], "skipped": [], "blocked": [], **self._execution_report(skipped=[], blocked=[], sample_count=0)},
                "skipped": [],
                "blocked": blocked,
                "summary": summary,
                **report,
                "execution_report": report,
            }
        account = self.ensure_default_account(tenant_id, params)
        account_id = int(params.get("paper_account_id") or account["id"])
        exits = self.evaluate_exits(tenant_id, account_id, params)
        max_positions = max(1, int(params.get("max_paper_positions") or os.getenv("PAPER_MAX_POSITIONS", "10") or 10))
        max_daily_opens = max(1, int(params.get("max_daily_opens") or params.get("max_daily_open_count") or os.getenv("PAPER_MAX_DAILY_OPENS", str(max_positions)) or max_positions))
        cash_per_trade = self._decimal(params.get("cash_per_trade") or os.getenv("PAPER_CASH_PER_TRADE") or "50000", Decimal("50000"))
        min_signal_score = self._decimal(params.get("min_signal_score") or os.getenv("PAPER_MIN_SIGNAL_SCORE") or "0")
        security_type = str(params.get("security_type") or params.get("target_security_type") or strategy.get("target_security_type") or "stock").strip().lower()
        bar_interval = normalize_bar_interval(params.get("bar_interval") or params.get("interval") or strategy.get("bar_interval") or "1d")
        allow_t0 = self._bool_value(params.get("allow_t0"), default=security_type == "convertible_bond")
        fee_rate = self._decimal(params.get("fee_rate") or os.getenv("PAPER_FEE_RATE") or "0")
        candidates = self._extract_candidates(scan)
        production_mode = self._is_production_mode(params)
        existing_symbols = {
            item["symbol"]
            for item in paper_trading_repo.list_positions(tenant_id, account_id, active_only=True)
            if int(item.get("quantity") or 0) > 0
        }
        orders = []
        skipped = []
        blocked = []
        created_open_count = 0
        for candidate in candidates:
            if len(existing_symbols) >= max_positions:
                skipped.append({"symbol": candidate.get("symbol"), "reason": "max_positions_reached"})
                continue
            symbol = str(candidate.get("symbol") or candidate.get("code") or "").strip()
            if not symbol:
                continue
            quality_gate_reason = self._quality_gate_reason(candidate, params)
            if quality_gate_reason:
                blocked.append({"symbol": symbol, "reason": quality_gate_reason, "side": "BUY", "data_quality": candidate.get("data_quality"), "market_data_source": candidate.get("market_data_source")})
                continue
            limit_up_return_skip_reason = self._limit_up_return_skip_reason(strategy, candidate)
            if limit_up_return_skip_reason:
                skipped.append({"symbol": symbol, "reason": limit_up_return_skip_reason, "signal_subtype": self._candidate_subtype(candidate)})
                continue
            first_limit_up_skip_reason = self._first_limit_up_skip_reason(strategy, candidate)
            if first_limit_up_skip_reason:
                skipped.append({"symbol": symbol, "reason": first_limit_up_skip_reason, "signal_subtype": self._candidate_subtype(candidate)})
                continue
            candidate_score = self._decimal(candidate.get("total_score") if candidate.get("total_score") is not None else candidate.get("score"))
            if min_signal_score > 0 and candidate_score < min_signal_score:
                skipped.append({"symbol": symbol, "reason": "score_below_threshold", "score": float(candidate_score), "threshold": float(min_signal_score)})
                continue
            candidate_signal_type = str(candidate.get("signal_type") or "").strip().upper()
            candidate_subtype = str(candidate.get("signal_subtype") or "").strip().lower()
            if candidate_signal_type == "RISK" or candidate_subtype == "failed_breakout":
                skipped.append({"symbol": symbol, "reason": "risk_signal", "signal_type": candidate_signal_type, "signal_subtype": candidate_subtype})
                continue
            executable_block_reason = self._executable_signal_block_reason(candidate, params)
            if executable_block_reason:
                blocked.append({"symbol": symbol, "reason": executable_block_reason, "side": "BUY", "signal_type": candidate.get("signal_type"), "strategy_runner": candidate.get("strategy_runner")})
                continue
            candidate_security_type = str(candidate.get("security_type") or security_type or "stock").strip().lower()
            candidate_bar_interval = normalize_bar_interval(candidate.get("bar_interval") or candidate.get("interval") or bar_interval)
            candidate_allow_t0 = self._bool_value(params.get("allow_t0"), default=candidate_security_type == "convertible_bond")
            candidate_default_lot_size = "10" if candidate_security_type == "convertible_bond" else "100"
            lot_size = max(1, int(params.get("lot_size") or os.getenv("PAPER_LOT_SIZE", candidate_default_lot_size) or candidate_default_lot_size))
            if symbol in existing_symbols:
                skipped.append({"symbol": symbol, "reason": "position_exists"})
                continue
            if created_open_count >= max_daily_opens:
                skipped.append({"symbol": symbol, "reason": "max_daily_opens_reached", "limit": max_daily_opens})
                continue
            snapshot = market_data_repo.get_latest_snapshot(symbol)
            buy_block_reason = self._buy_block_reason(snapshot, candidate, production_mode=production_mode)
            if buy_block_reason:
                blocked.append({"symbol": symbol, "reason": buy_block_reason, "side": "BUY", "snapshot": snapshot or {}})
                continue
            price = self._decimal((snapshot or {}).get("last_price") or candidate.get("last_price") or candidate.get("pick_price"))
            if price <= 0:
                skipped.append({"symbol": symbol, "reason": "missing_price"})
                continue
            account = paper_trading_repo.get_account(account_id) or account
            available_cash = self._decimal(account.get("cash"))
            budget = min(cash_per_trade, available_cash)
            quantity = floor((budget / price) / Decimal(lot_size)) * lot_size
            if quantity <= 0:
                skipped.append({"symbol": symbol, "reason": "insufficient_cash"})
                continue
            trade_date = str(candidate.get("trade_date") or datetime.now().date().isoformat())
            signal_hash = self._signal_hash(strategy, candidate)
            signal = paper_trading_repo.upsert_trade_signal(
                tenant_id,
                account_id=account_id,
                strategy_id=strategy.get("id"),
                strategy_code=strategy.get("code") or "",
                symbol=symbol,
                signal_date=trade_date,
                signal_type="BUY",
                source_hash=signal_hash,
                score=candidate.get("total_score") or candidate.get("score"),
                price_ref=price,
                data_quality=candidate.get("data_quality"),
                security_type=candidate_security_type,
                bar_interval=candidate_bar_interval,
                payload=candidate,
            )
            idempotency_key = f"paper:buy:{tenant_id}:{account_id}:{strategy.get('id')}:{symbol}:{candidate_security_type}:{candidate_bar_interval}:{trade_date}:{signal_hash[:12]}"
            try:
                created = paper_trading_repo.create_filled_order(
                    tenant_id,
                    account_id=account_id,
                    symbol=symbol,
                    side="BUY",
                    quantity=int(quantity),
                    price=price,
                    strategy_id=strategy.get("id"),
                    strategy_code=strategy.get("code"),
                    idempotency_key=idempotency_key,
                    source_signal_hash=signal_hash,
                    reason=str(candidate.get("signal") or candidate.get("reason_tag") or "strategy signal"),
                    metadata={"signal_id": signal.get("id"), "candidate": candidate, "snapshot": snapshot or {}, "mode": "paper", "security_type": candidate_security_type, "bar_interval": candidate_bar_interval, "allow_t0": candidate_allow_t0},
                    security_type=candidate_security_type,
                    bar_interval=candidate_bar_interval,
                    fee_rate=fee_rate,
                )
                pick = self._upsert_signal_pick(
                    tenant_id,
                    strategy=strategy,
                    candidate=candidate,
                    trade_date=trade_date,
                    symbol=symbol,
                    price=price,
                    signal_hash=signal_hash,
                    signal=signal,
                    snapshot=snapshot,
                    security_type=candidate_security_type,
                    bar_interval=candidate_bar_interval,
                )
                paper_trading_repo.upsert_signal_review_link(
                    tenant_id,
                    signal_hash,
                    trade_signal_id=signal.get("id"),
                    pick_id=(pick or {}).get("id"),
                    buy_order_id=(created.get("order") or {}).get("id"),
                    status="open",
                    metadata={
                        "strategy_code": strategy.get("code") or "",
                        "signal_subtype": self._candidate_subtype(candidate),
                        "symbol": symbol,
                        "trade_date": trade_date,
                        "security_type": candidate_security_type,
                        "bar_interval": candidate_bar_interval,
                        "source_context": candidate.get("source_context") or {},
                    },
                )
            except Exception as exc:
                skipped.append({"symbol": symbol, "reason": str(exc)})
                continue
            if created.get("created"):
                existing_symbols.add(symbol)
                created_open_count += 1
            orders.append(created.get("order"))
        report = self._execution_report(skipped=skipped, blocked=blocked, sample_count=len(candidates))
        result = {
            "enabled": True,
            "mode": "paper",
            "account": paper_trading_repo.get_account(account_id),
            "orders": [item for item in orders if item],
            "exits": exits,
            "skipped": skipped,
            "blocked": blocked,
            "summary": self.summary(tenant_id, account_id),
            **report,
            "execution_report": report,
            "limits": {
                "cash_per_trade": float(cash_per_trade),
                "max_positions": max_positions,
                "max_daily_opens": max_daily_opens,
                "created_open_count": created_open_count,
            },
            "live_trading": {
                "supported": True,
                "default_enabled": False,
                "adapter_contract": "BrokerAdapter.submit_order/reconcile_orders",
                "status_endpoint": "/api/v1/trading/live/broker/status",
                "guard": "paper execution only; live broker adapters are opt-in and guarded by disabled/dry-run defaults",
                "security_type": security_type,
                "bar_interval": bar_interval,
                "allow_t0": allow_t0,
            },
        }
        return result

    def evaluate_exits(self, tenant_id: int, account_id: int, params: dict | None = None) -> dict:
        params = params or {}
        fee_rate = self._decimal(params.get("fee_rate") or os.getenv("PAPER_FEE_RATE") or "0")
        orders = []
        skipped = []
        blocked = []
        evaluated = []
        positions = paper_trading_repo.list_positions(tenant_id, account_id, active_only=True)
        for position in positions:
            symbol = position.get("symbol")
            open_link = paper_trading_repo.get_open_signal_review_link_for_symbol(tenant_id, account_id, symbol) or {}
            source_context = self._exit_source_context(position, open_link)
            exit_plan = self._exit_plan(position, params, source_context)
            exit_rule = exit_plan
            quantity = int(position.get("quantity") or 0)
            avg_cost = self._decimal(position.get("avg_cost"))
            security_type = str(position.get("security_type") or "stock").strip().lower()
            bar_interval = normalize_bar_interval(position.get("bar_interval") or params.get("bar_interval") or params.get("interval") or "1d")
            adjust = str(params.get("adjust") or ("none" if bar_interval != "1d" else "qfq")).strip().lower()
            allow_t0 = self._bool_value(params.get("allow_t0"), default=bool(exit_plan.get("allow_t0")) or security_type == "convertible_bond")
            snapshot = market_data_repo.get_latest_snapshot(symbol)
            sell_block_reason = self._sell_block_reason(snapshot, position)
            if sell_block_reason:
                evaluated.append({"symbol": symbol, "reason": sell_block_reason, "exit_plan": exit_plan, "exit_rule": exit_rule})
                blocked.append({"symbol": symbol, "reason": sell_block_reason, "side": "SELL", "snapshot": snapshot or {}, "exit_plan": exit_plan, "exit_rule": exit_rule})
                continue
            price = self._decimal((snapshot or {}).get("last_price") or position.get("market_price"))
            if quantity <= 0 or price <= 0 or avg_cost <= 0:
                evaluated.append({"symbol": symbol, "reason": "missing_exit_price", "exit_plan": exit_plan, "exit_rule": exit_rule})
                skipped.append({"symbol": symbol, "reason": "missing_exit_price", "exit_plan": exit_plan, "exit_rule": exit_rule})
                continue
            return_pct = (price - avg_cost) / avg_cost
            holding_days = self._holding_days(position.get("opened_at"))
            if holding_days == 0 and not allow_t0:
                evaluated.append({"symbol": symbol, "reason": "t0_sell_blocked", "exit_plan": exit_plan, "exit_rule": exit_rule, "return_pct": float(return_pct), "holding_days": holding_days})
                skipped.append({"symbol": symbol, "reason": "t0_sell_blocked", "security_type": security_type, "exit_plan": exit_plan, "exit_rule": exit_rule, "return_pct": float(return_pct), "holding_days": holding_days})
                continue
            reason = ""
            stop_loss_pct = self._decimal(exit_plan["stop_loss_pct"])
            take_profit_pct = self._decimal(exit_plan["take_profit_pct"]) if exit_plan.get("take_profit_pct") is not None else None
            take_profit_price = self._decimal(exit_plan.get("take_profit_price"))
            sell_premium_rate = self._decimal(exit_plan.get("sell_premium_rate"))
            max_holding_days = int(exit_plan["max_holding_days"])
            premium_rate = self._premium_rate(snapshot or {}, position, source_context.get("candidate"), source_context.get("order_metadata"))
            if return_pct <= stop_loss_pct:
                reason = "stop_loss"
            elif take_profit_price > 0 and price >= take_profit_price:
                reason = "take_profit_price"
            elif sell_premium_rate > 0 and premium_rate is not None and premium_rate >= sell_premium_rate:
                reason = "premium_expanded"
            elif take_profit_pct is not None and return_pct >= take_profit_pct:
                reason = "take_profit"
            else:
                technical_params = {**params, "technical_exit_enabled": exit_plan["technical_exit_enabled"]}
                reason = self._technical_exit_reason(symbol, price, bar_interval=bar_interval, adjust=adjust, params=technical_params)
            if not reason and holding_days >= max_holding_days:
                reason = "max_holding_days"
            evaluation = {
                "symbol": symbol,
                "reason": reason,
                "exit_plan": exit_plan,
                "exit_rule": exit_rule,
                "return_pct": float(return_pct),
                "holding_days": holding_days,
            }
            if premium_rate is not None:
                evaluation["premium_rate"] = float(premium_rate)
            evaluated.append(evaluation)
            if not reason:
                continue
            idempotency_key = f"paper:sell:{tenant_id}:{account_id}:{symbol}:{datetime.now().date().isoformat()}:{reason}"
            source_hash = open_link.get("source_signal_hash") or reason
            try:
                created = paper_trading_repo.create_filled_order(
                    tenant_id,
                    account_id=account_id,
                    symbol=symbol,
                    side="SELL",
                    quantity=quantity,
                    price=price,
                    strategy_id=None,
                    strategy_code=exit_plan.get("strategy_code") or "exit_rule",
                    idempotency_key=idempotency_key,
                    source_signal_hash=source_hash,
                    reason=reason,
                    metadata={"position": position, "snapshot": snapshot or {}, "exit_plan": exit_plan, "exit_rule": exit_rule, "return_pct": float(return_pct), "premium_rate": float(premium_rate) if premium_rate is not None else None, "holding_days": holding_days, "security_type": security_type, "bar_interval": bar_interval, "adjust": adjust, "allow_t0": allow_t0},
                    security_type=security_type,
                    bar_interval=bar_interval,
                    fee_rate=fee_rate,
                )
                order = created.get("order")
                if isinstance(order, dict):
                    order.setdefault("exit_plan", exit_plan)
                    order.setdefault("exit_rule", exit_rule)
                    order.setdefault("return_pct", float(return_pct))
                    order.setdefault("holding_days", holding_days)
                    if premium_rate is not None:
                        order.setdefault("premium_rate", float(premium_rate))
                paper_trading_repo.upsert_signal_review_link(
                    tenant_id,
                    source_hash,
                    sell_order_id=(created.get("order") or {}).get("id"),
                    status="closed",
                    closed_at=datetime.now(),
                    realized_return_pct=float(return_pct * Decimal("100")),
                    metadata={"exit_reason": reason, "exit_plan": exit_plan, "return_pct": float(return_pct), "holding_days": holding_days},
                )
                if open_link.get("pick_id"):
                    self.pick_service.update_review(
                        tenant_id,
                        int(open_link["pick_id"]),
                        {
                            "deal_status": "closed",
                            "return_pct": float(return_pct * Decimal("100")),
                            "holding_days": holding_days,
                            "validation_result": reason,
                        },
                    )
                orders.append(order)
            except Exception as exc:
                skipped.append({"symbol": symbol, "reason": str(exc), "exit_plan": exit_plan, "exit_rule": exit_rule, "return_pct": float(return_pct), "holding_days": holding_days})
        report = self._execution_report(skipped=skipped, blocked=blocked, sample_count=len(positions))
        return {"orders": [item for item in orders if item], "evaluated": evaluated, "skipped": skipped, "blocked": blocked, **report, "execution_report": report}

    def _technical_exit_reason(self, symbol: str, price: Decimal, *, bar_interval: str, adjust: str, params: dict) -> str:
        if not self._bool_value(params.get("technical_exit_enabled"), default=True):
            return ""
        lookback_days = max(90, int(params.get("technical_exit_lookback_days") or os.getenv("PAPER_TECHNICAL_EXIT_LOOKBACK_DAYS", "180") or 180))
        end = date.today()
        start = end - timedelta(days=lookback_days)
        bars = market_data_repo.get_daily_bars(symbol, start.isoformat(), end.isoformat(), adjust=adjust, interval=bar_interval)
        if not bars:
            return ""

        closes = [self._decimal(item.get("close")) for item in bars if self._decimal(item.get("close")) > 0]
        highs = [self._decimal(item.get("high")) for item in bars if self._decimal(item.get("high")) > 0]
        if len(closes) < 25:
            return ""

        latest_close = closes[-1] if closes[-1] > 0 else price
        ma25 = sum(closes[-25:]) / Decimal(25)
        if len(closes) >= 60:
            ma60 = sum(closes[-60:]) / Decimal(60)
            if latest_close < ma60:
                return "ma60_breakdown"
        if latest_close < ma25:
            return "ma25_breakdown"
        if len(highs) >= 26 and len(closes) >= 6:
            prior_high20 = max(highs[-26:-6])
            recent_high = max(highs[-6:-1])
            if prior_high20 > 0 and recent_high > prior_high20 * Decimal("1.01") and latest_close < prior_high20 * Decimal("0.99"):
                return "failed_breakout"
        return ""

    def _extract_candidates(self, scan: dict) -> list[dict]:
        market_data = scan.get("market_data") or {}
        candidates = market_data.get("sample_symbols") or scan.get("items") or scan.get("symbols") or []
        normalized = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or item.get("code") or item.get("stock_code") or "").strip()
            if not symbol:
                continue
            normalized.append({**item, "symbol": symbol})
        return normalized

    def _upsert_signal_pick(
        self,
        tenant_id: int,
        *,
        strategy: dict,
        candidate: dict,
        trade_date: str,
        symbol: str,
        price: Decimal,
        signal_hash: str,
        signal: dict,
        snapshot: dict | None,
        security_type: str,
        bar_interval: str,
    ) -> dict:
        market_data = snapshot or {}
        reason = str(candidate.get("signal") or candidate.get("reason_tag") or candidate.get("signal_subtype") or "strategy_signal")
        note = str(candidate.get("note") or candidate.get("reason") or candidate.get("explain") or "")
        payload = {
            "symbol": symbol,
            "stock_name": candidate.get("name") or candidate.get("stock_name") or symbol,
            "trade_date": trade_date,
            "source": "production_signal",
            "source_channel": "paper_trading",
            "strategy_code": strategy.get("code") or "",
            "reason": reason,
            "note": note,
            "risk_level": candidate.get("risk_level") or candidate.get("risk_grade") or "pending",
            "signal": candidate.get("signal_type") or candidate.get("signal") or "BUY",
            "pick_price": float(price),
            "status": "accepted",
            "deal_status": "filled",
            "secondary_spread": security_type,
            "data_quality": candidate.get("data_quality") or market_data.get("data_quality") or "",
            "market_data_source": candidate.get("market_data_source") or market_data.get("source") or "",
            "fallback_used": bool(candidate.get("fallback_used") or market_data.get("fallback_used")),
            "content_title": f"{strategy.get('code') or 'strategy'} {symbol}",
            "content_ref": signal_hash,
            "legacy_payload_json": {"source_context": candidate.get("source_context") or {}, "signal_hash": signal_hash},
        }
        pick = self.pick_service.create_pick(tenant_id, payload)
        paper_trading_repo.upsert_signal_review_link(
            tenant_id,
            signal_hash,
            trade_signal_id=signal.get("id"),
            pick_id=pick.get("id"),
            status="open",
            metadata={"pick_source": "production_signal", "strategy_code": strategy.get("code") or "", "signal_subtype": self._candidate_subtype(candidate), "symbol": symbol, "source_context": candidate.get("source_context") or {}},
        )
        return pick

    def _signal_hash(self, strategy: dict, candidate: dict) -> str:
        payload = {
            "strategy_id": strategy.get("id"),
            "strategy_code": strategy.get("code"),
            "symbol": candidate.get("symbol"),
            "trade_date": candidate.get("trade_date"),
            "signal": candidate.get("signal") or candidate.get("reason_tag"),
            "security_type": candidate.get("security_type"),
            "bar_interval": candidate.get("bar_interval") or candidate.get("interval"),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _holding_days(self, opened_at: Any) -> int:
        if not opened_at:
            return 0
        if isinstance(opened_at, datetime):
            opened = opened_at
        else:
            try:
                opened = datetime.fromisoformat(str(opened_at).replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                return 0
        return max(0, (datetime.now().date() - opened.date()).days)
