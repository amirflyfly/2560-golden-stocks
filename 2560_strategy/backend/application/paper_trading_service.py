"""Paper trading orchestration for strategy production signals."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from math import floor
from typing import Any

from backend.infrastructure.market_data.utils import normalize_bar_interval
from backend.repositories import market_data_repo
from backend.repositories import paper_trading_repo


LIMIT_UP_RETURN_CODE = "LIMIT_UP_RETURN"
LIMIT_UP_RETURN_BUY_SUBTYPE = "breakout_confirmed"


class BrokerAdapter:
    """Reserved live-trading contract. Production live adapters must implement this interface."""

    mode = "paper"

    def submit_order(self, order_intent: dict) -> dict:  # pragma: no cover - contract only
        raise NotImplementedError

    def reconcile_orders(self, account_id: int) -> dict:  # pragma: no cover - contract only
        raise NotImplementedError


class PaperTradingService:
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

    def _strategy_code(self, strategy: dict | None) -> str:
        return str((strategy or {}).get("code") or "").strip().upper()

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
            limit_up_return_skip_reason = self._limit_up_return_skip_reason(strategy, candidate)
            if limit_up_return_skip_reason:
                skipped.append({"symbol": symbol, "reason": limit_up_return_skip_reason, "signal_subtype": self._candidate_subtype(candidate)})
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
                "supported": False,
                "reserved_adapter": "BrokerAdapter.submit_order/reconcile_orders",
                "guard": "paper execution only; no real broker order is sent",
                "security_type": security_type,
                "bar_interval": bar_interval,
                "allow_t0": allow_t0,
            },
        }
        return result

    def evaluate_exits(self, tenant_id: int, account_id: int, params: dict | None = None) -> dict:
        params = params or {}
        stop_loss_pct = self._decimal(params.get("stop_loss_pct") or os.getenv("PAPER_STOP_LOSS_PCT") or "-0.08")
        take_profit_pct = self._decimal(params.get("take_profit_pct") or os.getenv("PAPER_TAKE_PROFIT_PCT") or "0.15")
        max_holding_days = int(params.get("max_holding_days") or os.getenv("PAPER_MAX_HOLDING_DAYS", "20") or 20)
        fee_rate = self._decimal(params.get("fee_rate") or os.getenv("PAPER_FEE_RATE") or "0")
        orders = []
        skipped = []
        blocked = []
        positions = paper_trading_repo.list_positions(tenant_id, account_id, active_only=True)
        for position in positions:
            symbol = position.get("symbol")
            quantity = int(position.get("quantity") or 0)
            avg_cost = self._decimal(position.get("avg_cost"))
            security_type = str(position.get("security_type") or "stock").strip().lower()
            bar_interval = normalize_bar_interval(position.get("bar_interval") or params.get("bar_interval") or params.get("interval") or "1d")
            adjust = str(params.get("adjust") or ("none" if bar_interval != "1d" else "qfq")).strip().lower()
            allow_t0 = self._bool_value(params.get("allow_t0"), default=security_type == "convertible_bond")
            snapshot = market_data_repo.get_latest_snapshot(symbol)
            sell_block_reason = self._sell_block_reason(snapshot, position)
            if sell_block_reason:
                blocked.append({"symbol": symbol, "reason": sell_block_reason, "side": "SELL", "snapshot": snapshot or {}})
                continue
            price = self._decimal((snapshot or {}).get("last_price") or position.get("market_price"))
            if quantity <= 0 or price <= 0 or avg_cost <= 0:
                skipped.append({"symbol": symbol, "reason": "missing_exit_price"})
                continue
            return_pct = (price - avg_cost) / avg_cost
            holding_days = self._holding_days(position.get("opened_at"))
            if holding_days == 0 and not allow_t0:
                skipped.append({"symbol": symbol, "reason": "t0_sell_blocked", "security_type": security_type})
                continue
            reason = ""
            if return_pct <= stop_loss_pct:
                reason = "stop_loss"
            elif return_pct >= take_profit_pct:
                reason = "take_profit"
            else:
                reason = self._technical_exit_reason(symbol, price, bar_interval=bar_interval, adjust=adjust, params=params)
            if not reason and holding_days >= max_holding_days:
                reason = "max_holding_days"
            if not reason:
                continue
            idempotency_key = f"paper:sell:{tenant_id}:{account_id}:{symbol}:{datetime.now().date().isoformat()}:{reason}"
            try:
                created = paper_trading_repo.create_filled_order(
                    tenant_id,
                    account_id=account_id,
                    symbol=symbol,
                    side="SELL",
                    quantity=quantity,
                    price=price,
                    strategy_id=None,
                    strategy_code="exit_rule",
                    idempotency_key=idempotency_key,
                    source_signal_hash=reason,
                    reason=reason,
                    metadata={"position": position, "snapshot": snapshot or {}, "return_pct": float(return_pct), "holding_days": holding_days, "security_type": security_type, "bar_interval": bar_interval, "adjust": adjust, "allow_t0": allow_t0},
                    security_type=security_type,
                    bar_interval=bar_interval,
                    fee_rate=fee_rate,
                )
                orders.append(created.get("order"))
            except Exception as exc:
                skipped.append({"symbol": symbol, "reason": str(exc)})
        report = self._execution_report(skipped=skipped, blocked=blocked, sample_count=len(positions))
        return {"orders": [item for item in orders if item], "skipped": skipped, "blocked": blocked, **report, "execution_report": report}

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
