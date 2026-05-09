"""Convertible bond low-premium strategy.

The strategy uses local market data only. Convertible-bond terms are read from
the stock row's limit_rule_profile under the "convertible_bond" or "terms" key.
Expected term fields include underlying_symbol, conversion_price,
remaining_size_yi, redeem_status, and rating_status.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from backend.infrastructure.market_data.utils import infer_exchange
from backend.repositories import market_data_repo
from backend.strategies import BaseStrategy, register_strategy


SIGNAL_SCHEMA_VERSION = "convertible-bond-low-premium/v1"
STRATEGY_CODE = "CONVERTIBLE_BOND_LOW_PREMIUM"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on", "st", "risk", "delisting"}


def _date_before(target_date: str, days: int) -> str:
    return (datetime.strptime(target_date, "%Y-%m-%d").date() - timedelta(days=days)).isoformat()


def _frame_from_bars(bars: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for bar in bars:
        rows.append(
            {
                "date": bar.get("trade_date"),
                "open": _safe_float(bar.get("open")),
                "high": _safe_float(bar.get("high")),
                "low": _safe_float(bar.get("low")),
                "close": _safe_float(bar.get("close")),
                "volume": _safe_float(bar.get("volume")),
                "amount": _safe_float(bar.get("amount")),
                "source": bar.get("source"),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("date").reset_index(drop=True)


@register_strategy
class ConvertibleBondLowPremiumStrategy(BaseStrategy):
    """Low-price, low-premium convertible bond rotation strategy."""

    def __init__(self):
        self.config = {
            "strategy": {
                "scan_limit": 500,
                "select_count": 25,
                "min_bars": 20,
                "min_price": 100.0,
                "max_price": 118.0,
                "max_entry_price": 125.0,
                "max_premium_rate": 0.25,
                "max_entry_premium_rate": 0.30,
                "max_double_low": 145.0,
                "min_remaining_size_yi": 2.0,
                "min_avg_amount_20d": 20_000_000.0,
                "max_stock_20d_drop": -0.20,
                "take_profit_price": 130.0,
                "sell_premium_rate": 0.40,
                "stop_loss_pct": -0.06,
                "max_holding_days": 20,
            }
        }
        super().__init__()

    def get_code(self) -> str:
        return STRATEGY_CODE

    def get_name(self) -> str:
        return "Convertible Bond Low Premium"

    def get_description(self) -> str:
        return "Low-price, low-premium convertible bond rotation with forced redemption and credit filters."

    @property
    def params(self) -> dict[str, Any]:
        return self.config["strategy"]

    def scan(self, date: str | None = None) -> list[dict[str, Any]]:
        target_date = date or datetime.now().date().isoformat()
        candidates = []
        for row in self._list_universe():
            matched, _, payload = self._analyze_bond(row, target_date)
            if matched:
                candidates.append(payload)
        candidates.sort(key=lambda item: (_safe_float(item.get("risk_score"), 100), -_safe_float(item.get("total_score"))))
        return candidates[: _safe_int(self.params.get("select_count"), 25)]

    def _list_universe(self) -> list[dict[str, Any]]:
        payload = market_data_repo.list_stocks(
            limit=_safe_int(self.params.get("scan_limit"), 500),
            security_type="convertible_bond",
        )
        return [dict(item) for item in payload.get("items", [])]

    def _terms_from_row(self, row: dict[str, Any]) -> dict[str, Any]:
        profile = row.get("limit_rule_profile")
        if isinstance(profile, str) and profile.strip():
            try:
                profile = json.loads(profile)
            except json.JSONDecodeError:
                profile = {}
        if not isinstance(profile, dict):
            profile = {}
        terms = profile.get("convertible_bond") or profile.get("terms") or profile
        return terms if isinstance(terms, dict) else {}

    def _get_bars(self, symbol: str, start_date: str, end_date: str, *, adjust: str = "none") -> pd.DataFrame:
        bars = market_data_repo.get_daily_bars(symbol, start_date, end_date, adjust=adjust, interval="1d")
        if not bars and adjust != "qfq":
            bars = market_data_repo.get_daily_bars(symbol, start_date, end_date, adjust="qfq", interval="1d")
        return _frame_from_bars(bars)

    def _conversion_value(self, terms: dict[str, Any], target_date: str) -> tuple[float, dict[str, Any]]:
        direct_value = _safe_float(terms.get("conversion_value") or terms.get("convert_value"))
        if direct_value > 0:
            return direct_value, {"source": "terms", "underlying_close": None}
        conversion_price = _safe_float(terms.get("conversion_price") or terms.get("convert_price"))
        underlying_symbol = str(terms.get("underlying_symbol") or terms.get("stock_code") or "").strip()
        if conversion_price <= 0 or not underlying_symbol:
            return 0.0, {"source": "missing_terms", "underlying_close": None}
        stock_df = self._get_bars(underlying_symbol, _date_before(target_date, 45), target_date, adjust="qfq")
        if stock_df.empty:
            return 0.0, {"source": "missing_underlying_bars", "underlying_close": None}
        underlying_close = _safe_float(stock_df.iloc[-1].get("close"))
        if underlying_close <= 0:
            return 0.0, {"source": "invalid_underlying_close", "underlying_close": None}
        return underlying_close / conversion_price * 100.0, {
            "source": "underlying",
            "underlying_symbol": underlying_symbol,
            "underlying_close": round(underlying_close, 4),
            "conversion_price": round(conversion_price, 4),
        }

    def _remaining_size_yi(self, terms: dict[str, Any]) -> float:
        for key in ("remaining_size_yi", "remaining_size", "balance_yi", "outstanding_yi"):
            value = _safe_float(terms.get(key), default=-1.0)
            if value >= 0:
                return value
        amount = _safe_float(terms.get("remaining_amount") or terms.get("balance_amount"), default=-1.0)
        return amount / 100_000_000 if amount >= 0 else 0.0

    def _event_risk(self, row: dict[str, Any], terms: dict[str, Any]) -> tuple[bool, list[str]]:
        flags: list[str] = []
        if _as_bool(row.get("is_st")) or _as_bool(row.get("is_delisting")):
            flags.append("stock_risk_warning_or_delisting")
        if str(row.get("status") or "").strip().lower() not in {"", "active", "listed"}:
            flags.append("inactive_security")
        redeem_status = str(terms.get("redeem_status") or terms.get("force_redeem_status") or "").strip().lower()
        if redeem_status in {"announced", "triggered", "near", "counting", "in_progress", "redeem"}:
            flags.append("force_redeem_risk")
        if _as_bool(terms.get("force_redeem_risk")) or _as_bool(terms.get("redeem_announced")):
            flags.append("force_redeem_risk")
        rating_status = str(terms.get("rating_status") or terms.get("credit_status") or "").strip().lower()
        if rating_status in {"downgraded", "negative", "watch", "default", "overdue"}:
            flags.append("credit_risk")
        if _as_bool(terms.get("suspended")):
            flags.append("suspended")
        if _as_bool(terms.get("delisting_risk")):
            flags.append("delisting_risk")
        return bool(flags), sorted(set(flags))

    def _stock_trend_score(self, terms: dict[str, Any], target_date: str) -> tuple[float, dict[str, Any]]:
        underlying_symbol = str(terms.get("underlying_symbol") or terms.get("stock_code") or "").strip()
        if not underlying_symbol:
            return 7.0, {"source": "neutral_missing_symbol"}
        stock_df = self._get_bars(underlying_symbol, _date_before(target_date, 120), target_date, adjust="qfq")
        if len(stock_df) < 20:
            return 7.0, {"source": "neutral_missing_bars", "underlying_symbol": underlying_symbol}
        close = stock_df["close"].astype(float)
        last_close = float(close.iloc[-1])
        ma20 = float(close.tail(20).mean())
        ma60 = float(close.tail(min(60, len(close))).mean())
        change_20d = (last_close / float(close.iloc[-20]) - 1.0) if close.iloc[-20] else 0.0
        score = 7.0
        if last_close >= ma20:
            score += 4.0
        if last_close >= ma60:
            score += 3.0
        if change_20d >= 0:
            score += 1.0
        if change_20d < _safe_float(self.params.get("max_stock_20d_drop"), -0.20):
            score = 0.0
        return _clamp(score, 0.0, 15.0), {
            "source": "underlying",
            "underlying_symbol": underlying_symbol,
            "underlying_close": round(last_close, 4),
            "underlying_ma20": round(ma20, 4),
            "underlying_ma60": round(ma60, 4),
            "underlying_change_20d": round(change_20d, 6),
        }

    def _score(
        self,
        *,
        price: float,
        premium_rate: float,
        double_low: float,
        avg_amount_20d: float,
        remaining_size_yi: float,
        trend_score: float,
        event_flags: list[str],
    ) -> tuple[float, float, dict[str, float]]:
        p = self.params
        price_score = _clamp((_safe_float(p["max_entry_price"]) - price) / (_safe_float(p["max_entry_price"]) - _safe_float(p["min_price"])) * 40.0, 0.0, 40.0)
        premium_score = _clamp((_safe_float(p["max_entry_premium_rate"]) - premium_rate) / (_safe_float(p["max_entry_premium_rate"]) + 0.10) * 30.0, 0.0, 30.0)
        double_low_score = _clamp((_safe_float(p["max_double_low"]) - double_low) / 45.0 * 10.0, 0.0, 10.0)
        liquidity_score = _clamp(avg_amount_20d / max(_safe_float(p["min_avg_amount_20d"]), 1.0) * 6.0, 0.0, 6.0)
        size_score = _clamp(remaining_size_yi / max(_safe_float(p["min_remaining_size_yi"]), 1.0) * 4.0, 0.0, 4.0)
        event_score = 5.0 if not event_flags else 0.0
        total_score = price_score + premium_score + double_low_score + trend_score + liquidity_score + size_score + event_score
        risk_score = _clamp(100.0 - total_score + len(event_flags) * 15.0, 0.0, 100.0)
        return round(total_score, 2), round(risk_score, 2), {
            "price_score": round(price_score, 2),
            "premium_score": round(premium_score, 2),
            "double_low_score": round(double_low_score, 2),
            "trend_score": round(trend_score, 2),
            "liquidity_score": round(liquidity_score, 2),
            "size_score": round(size_score, 2),
            "event_score": event_score,
        }

    def _analyze_bond(self, row: dict[str, Any], target_date: str) -> tuple[bool, str, dict[str, Any]]:
        p = self.params
        symbol = str(row.get("symbol") or row.get("code") or "").strip()
        name = str(row.get("name") or symbol).strip()
        terms = self._terms_from_row(row)
        df = self._get_bars(symbol, _date_before(target_date, 180), target_date, adjust="none")
        if len(df) < _safe_int(p.get("min_bars"), 20):
            return False, "insufficient_bars", {}
        last = df.iloc[-1]
        price = _safe_float(last.get("close"))
        if price <= 0:
            return False, "invalid_price", {}

        conversion_value, conversion_meta = self._conversion_value(terms, target_date)
        if conversion_value <= 0:
            return False, "missing_conversion_value", {}
        premium_rate = price / conversion_value - 1.0
        double_low = price + premium_rate * 100.0
        remaining_size_yi = self._remaining_size_yi(terms)
        avg_amount_20d = float(df["amount"].tail(20).mean()) if "amount" in df else 0.0
        trend_score, trend_meta = self._stock_trend_score(terms, target_date)
        has_event_risk, event_flags = self._event_risk(row, terms)

        if has_event_risk:
            return False, ",".join(event_flags), {}
        if price < _safe_float(p["min_price"]) or price > _safe_float(p["max_entry_price"]):
            return False, "price_out_of_range", {}
        if premium_rate > _safe_float(p["max_entry_premium_rate"]):
            return False, "premium_too_high", {}
        if double_low > _safe_float(p["max_double_low"]):
            return False, "double_low_too_high", {}
        if remaining_size_yi < _safe_float(p["min_remaining_size_yi"]):
            return False, "remaining_size_too_small", {}
        if avg_amount_20d < _safe_float(p["min_avg_amount_20d"]):
            return False, "liquidity_too_low", {}

        total_score, risk_score, score_parts = self._score(
            price=price,
            premium_rate=premium_rate,
            double_low=double_low,
            avg_amount_20d=avg_amount_20d,
            remaining_size_yi=remaining_size_yi,
            trend_score=trend_score,
            event_flags=event_flags,
        )
        signal_subtype = "core_low_price_low_premium" if price <= _safe_float(p["max_price"]) and premium_rate <= _safe_float(p["max_premium_rate"]) else "watch_low_double_low"
        payload = {
            "schema_version": SIGNAL_SCHEMA_VERSION,
            "strategy_code": STRATEGY_CODE,
            "code": symbol,
            "symbol": symbol,
            "name": name,
            "stock_name": name,
            "exchange": row.get("exchange") or infer_exchange(symbol),
            "security_type": "convertible_bond",
            "bar_interval": "1d",
            "interval": "1d",
            "adjust": "none",
            "trade_date": target_date,
            "pick_date": target_date,
            "pick_price": round(price, 4),
            "last_price": round(price, 4),
            "signal": "low_price_low_premium",
            "reason_tag": "convertible_bond_low_premium",
            "signal_subtype": signal_subtype,
            "volume_phase": "liquid_rotation",
            "total_score": total_score,
            "score": total_score,
            "risk_score": risk_score,
            "conversion_value": round(conversion_value, 4),
            "premium_rate": round(premium_rate, 6),
            "double_low": round(double_low, 4),
            "remaining_size_yi": round(remaining_size_yi, 4),
            "avg_amount_20d": round(avg_amount_20d, 2),
            "recommend_reason": "Low price, controlled conversion premium, adequate liquidity, and no forced redemption or credit flag.",
            "prediction_reason": "Expected payoff comes from premium repair, underlying trend, and bond-floor protection.",
            "note": f"premium={premium_rate:.2%}; double_low={double_low:.2f}; avg_amount_20d={avg_amount_20d:.0f}",
            "indicators": {
                "price": round(price, 4),
                "conversion_value": round(conversion_value, 4),
                "premium_rate": round(premium_rate, 6),
                "premium_pct": round(premium_rate * 100.0, 4),
                "double_low": round(double_low, 4),
                "remaining_size_yi": round(remaining_size_yi, 4),
                "avg_amount_20d": round(avg_amount_20d, 2),
                "score_parts": score_parts,
                "conversion": conversion_meta,
                "underlying_trend": trend_meta,
            },
            "risk": {
                "risk_score": risk_score,
                "event_flags": event_flags,
                "force_redeem_guard": True,
                "credit_guard": True,
                "liquidity_guard": True,
            },
            "phase": {
                "signal_subtype": signal_subtype,
                "volume_phase": "liquid_rotation",
                "rotation_bucket": "core" if signal_subtype == "core_low_price_low_premium" else "watch",
            },
            "data": {
                "bar_count": len(df),
                "terms_source": "stocks.limit_rule_profile.convertible_bond",
                "allow_t0": True,
            },
            "metadata": {
                "security_type": "convertible_bond",
                "allow_t0": True,
                "buy_model": {
                    "max_entry_price": p["max_entry_price"],
                    "max_entry_premium_rate": p["max_entry_premium_rate"],
                    "max_double_low": p["max_double_low"],
                },
                "sell_model": {
                    "take_profit_price": p["take_profit_price"],
                    "sell_premium_rate": p["sell_premium_rate"],
                    "stop_loss_pct": p["stop_loss_pct"],
                    "max_holding_days": p["max_holding_days"],
                },
            },
        }
        return True, "matched", payload

    def run_model_backtest(
        self,
        start_date: str,
        end_date: str,
        *,
        trading_dates: list[str],
        holding_days: int = 5,
        max_positions_per_day: int = 3,
    ) -> dict[str, Any]:
        max_holding_days = max(1, min(_safe_int(self.params.get("max_holding_days"), 20), int(holding_days or 5)))
        trades: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for index, trade_date in enumerate(trading_dates[:-1]):
            picks = self.scan(trade_date)
            if not picks:
                continue
            entry_date = trading_dates[index + 1]
            for pick in picks[: max(1, int(max_positions_per_day or 1))]:
                trade = self._simulate_trade(
                    pick=pick,
                    signal_date=trade_date,
                    entry_date=entry_date,
                    trading_dates=trading_dates,
                    entry_index=index + 1,
                    max_holding_days=max_holding_days,
                )
                if trade.get("skip_reason"):
                    skipped.append(trade)
                else:
                    trades.append(trade)

        return {
            "trades": trades,
            "skipped_trades": skipped,
            "execution_summary": {
                "t_plus_one": True,
                "allow_t0": True,
                "candidate_count": len(trades) + len(skipped),
                "included_count": len(trades),
                "skipped_count": len(skipped),
                "sell_model": {
                    "take_profit_price": self.params["take_profit_price"],
                    "sell_premium_rate": self.params["sell_premium_rate"],
                    "stop_loss_pct": self.params["stop_loss_pct"],
                    "max_holding_days": max_holding_days,
                },
            },
        }

    def _simulate_trade(
        self,
        *,
        pick: dict[str, Any],
        signal_date: str,
        entry_date: str,
        trading_dates: list[str],
        entry_index: int,
        max_holding_days: int,
    ) -> dict[str, Any]:
        symbol = str(pick.get("code") or "").strip()
        entry_bar = self._bar_on(symbol, entry_date)
        entry_price = _safe_float(entry_bar.get("open") or entry_bar.get("close")) if entry_bar else 0.0
        if entry_price <= 0:
            return self._skipped_backtest_trade(pick, signal_date, entry_date, "invalid_entry_price")

        exit_bar = entry_bar
        exit_date = entry_date
        exit_reason = "max_holding_days"
        end_index = min(entry_index + max_holding_days - 1, len(trading_dates) - 1)

        for idx in range(entry_index, end_index + 1):
            current_date = trading_dates[idx]
            current_bar = self._bar_on(symbol, current_date)
            if not current_bar:
                continue
            current_close = _safe_float(current_bar.get("close"))
            current_return = (current_close - entry_price) / entry_price if entry_price > 0 else 0.0
            exit_bar = current_bar
            exit_date = current_date
            current_premium = self._premium_on_date(pick, current_close, current_date)
            if current_close >= _safe_float(self.params.get("take_profit_price"), 130.0):
                exit_reason = "take_profit_price"
                break
            if current_premium is not None and current_premium >= _safe_float(self.params.get("sell_premium_rate"), 0.40):
                exit_reason = "premium_expanded"
                break
            if current_return <= _safe_float(self.params.get("stop_loss_pct"), -0.06):
                exit_reason = "stop_loss"
                break

        exit_price = _safe_float(exit_bar.get("close")) if exit_bar else 0.0
        if exit_price <= 0:
            return self._skipped_backtest_trade(pick, signal_date, entry_date, "invalid_exit_price")
        return_pct = (exit_price - entry_price) / entry_price
        holding_days = max(1, trading_dates.index(exit_date) - entry_index + 1 if exit_date in trading_dates else max_holding_days)
        metadata = dict(pick.get("metadata") or {})
        metadata.update(
            {
                "signal_subtype": pick.get("signal_subtype"),
                "volume_phase": pick.get("volume_phase"),
                "premium_rate": pick.get("premium_rate"),
                "double_low": pick.get("double_low"),
                "remaining_size_yi": pick.get("remaining_size_yi"),
                "exit_reason": exit_reason,
                "allow_t0": True,
            }
        )
        return {
            "strategy_code": STRATEGY_CODE,
            "strategy_name": self.name,
            "signal_date": signal_date,
            "entry_date": entry_date,
            "exit_date": exit_date,
            "holding_days": holding_days,
            "code": symbol,
            "name": pick.get("name"),
            "signal": pick.get("signal"),
            "reason_tag": pick.get("reason_tag"),
            "note": f"{pick.get('note', '')}; exit={exit_reason}",
            "entry_price": round(entry_price, 4),
            "exit_price": round(exit_price, 4),
            "return_pct": round(return_pct, 6),
            "risk_score": round(_safe_float(pick.get("risk_score")), 2),
            "score": round(_safe_float(pick.get("total_score")), 2),
            "signal_subtype": pick.get("signal_subtype"),
            "volume_phase": pick.get("volume_phase"),
            "metadata": metadata,
            "t_plus_one": True,
            "execution_flags": {
                "t_plus_one": True,
                "allow_t0": True,
                "suspended": False,
                "limit_up": False,
                "limit_down": False,
            },
        }

    def _bar_on(self, symbol: str, trade_date: str) -> dict[str, Any] | None:
        bars = market_data_repo.get_daily_bars(symbol, trade_date, trade_date, adjust="none", interval="1d")
        if not bars:
            bars = market_data_repo.get_daily_bars(symbol, trade_date, trade_date, adjust="qfq", interval="1d")
        return bars[0] if bars else None

    def _premium_on_date(self, pick: dict[str, Any], bond_price: float, trade_date: str) -> float | None:
        indicators = pick.get("indicators") if isinstance(pick.get("indicators"), dict) else {}
        conversion = indicators.get("conversion") if isinstance(indicators.get("conversion"), dict) else {}
        conversion_price = _safe_float(conversion.get("conversion_price"))
        underlying_symbol = str(conversion.get("underlying_symbol") or "").strip()
        if conversion_price <= 0 or not underlying_symbol:
            conversion_value = _safe_float(pick.get("conversion_value"))
            return bond_price / conversion_value - 1.0 if conversion_value > 0 else None
        bar = self._bar_on(underlying_symbol, trade_date)
        if not bar:
            return None
        underlying_close = _safe_float(bar.get("close"))
        conversion_value = underlying_close / conversion_price * 100.0 if conversion_price > 0 else 0.0
        return bond_price / conversion_value - 1.0 if conversion_value > 0 else None

    def _skipped_backtest_trade(self, pick: dict[str, Any], signal_date: str, entry_date: str, reason: str) -> dict[str, Any]:
        return {
            "strategy_code": STRATEGY_CODE,
            "strategy_name": self.name,
            "signal_date": signal_date,
            "entry_date": entry_date,
            "intended_entry_date": entry_date,
            "code": pick.get("code"),
            "name": pick.get("name"),
            "signal": pick.get("signal"),
            "reason": reason,
            "skip_reason": reason,
            "action": "invalid_price",
            "metadata": dict(pick.get("metadata") or {}),
        }
