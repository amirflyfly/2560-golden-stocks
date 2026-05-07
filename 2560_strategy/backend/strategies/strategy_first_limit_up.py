"""First limit-up next-day entry strategy.

The model is deliberately split into two stages:

1. T-day preselection: find first limit-up stocks with acceptable market,
   sector, limit-up quality, volume/liquidity, and stock-character factors.
2. T+1 auction confirmation: only a confirmed auction/open snapshot may become
   an executable signal. T-day candidates remain observation-only.

The strategy uses the local market data service first and returns the same
explainable payload contract used by the scan API.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from backend.infrastructure.market_data.utils import infer_board_type, infer_exchange, infer_security_type
from backend.strategies import BaseStrategy, register_strategy
from backend.strategies.strategy_limit_up_return import LimitUpRule, infer_limit_up_rule

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - local test fallback
    pd = None


SIGNAL_SCHEMA_VERSION = "strategy-signal/first-limit-up-next-board/v1"


@register_strategy
class StrategyFirstLimitUp(BaseStrategy):
    """First limit-up watchlist with next-day auction confirmation."""

    essential_cols = ["date", "open", "close", "high", "low", "volume"]

    def __init__(self):
        super().__init__()
        self.config: dict[str, Any] = {
            "lookback_days": 160,
            "scan_limit": 600,
            "select_count": 10,
            "min_bars": 35,
            "no_limit_up_lookback": 10,
            "price_limit": 0,
            "exclude_st": True,
            "exclude_kechuang": False,
            "exclude_bj": True,
            "min_amount": 20_000_000,
            "min_turnover": 1.5,
            "max_turnover": 35.0,
            "min_amount_ratio_20": 0.5,
            "max_amount_ratio_20": 5.0,
            "one_word_turnover": 1.5,
            "one_word_amount_ratio": 0.55,
            "limit_price_tolerance_pct": 0.003,
            "min_preselect_score": 70,
            "min_auction_score": 70,
            "market_min_score": 40,
            "auction_open_min_ratio": 0.20,
            "auction_open_max_ratio": 0.75,
            "auction_open_reject_ratio": 0.90,
            "auction_amount_ratio_min": 0.03,
            "auction_volume_ratio_min": 0.03,
            "min_auction_amount": 3_000_000,
            "include_rejected": False,
            "bar_interval": "1d",
            "adjust": "qfq",
        }

    def get_code(self) -> str:
        return "FIRST_LIMIT_UP"

    def get_name(self) -> str:
        return "First Limit-Up Next-Day Entry"

    def get_description(self) -> str:
        return "T-day first limit-up preselection plus T+1 auction confirmation for next-board candidates."

    def get_category(self) -> str:
        return "Short-term event strategy"

    def get_parameters(self) -> dict[str, Any]:
        return {
            "no_limit_up_lookback": {"type": "int", "default": 10, "min": 3, "max": 30},
            "min_preselect_score": {"type": "float", "default": 70, "min": 50, "max": 90},
            "min_auction_score": {"type": "float", "default": 70, "min": 50, "max": 90},
            "auction_open_min_ratio": {"type": "float", "default": 0.20, "min": 0.0, "max": 0.5},
            "auction_open_max_ratio": {"type": "float", "default": 0.75, "min": 0.4, "max": 1.0},
            "auction_amount_ratio_min": {"type": "float", "default": 0.03, "min": 0.0, "max": 0.2},
            "bar_interval": {"type": "string", "default": "1d"},
            "adjust": {"type": "string", "default": "qfq"},
        }

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return default
            if pd is not None and pd.isna(value):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(float(value))
        except (TypeError, ValueError):
            return default

    def _float_config(self, key: str, default: float) -> float:
        return self._safe_float(self.config.get(key), default)

    def _int_config(self, key: str, default: int) -> int:
        return self._safe_int(self.config.get(key), default)

    def _bool_config(self, key: str, default: bool = False) -> bool:
        value = self.config.get(key)
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    def _find_column(self, df, candidates: list[str]) -> str | None:
        lower_to_col = {str(col).strip().lower(): col for col in getattr(df, "columns", [])}
        for candidate in candidates:
            found = lower_to_col.get(str(candidate).strip().lower())
            if found is not None:
                return found
        return None

    def _normalize_hist_cols(self, df):
        if pd is None or df is None or getattr(df, "empty", True):
            return df
        aliases = {
            "date": ["date", "trade_date", "datetime", "日期"],
            "open": ["open", "开盘"],
            "close": ["close", "last_price", "收盘", "最新价"],
            "high": ["high", "最高"],
            "low": ["low", "最低"],
            "volume": ["volume", "vol", "成交量"],
            "amount": ["amount", "成交额"],
            "turnover": ["turnover", "turnover_rate", "换手率"],
            "pct_chg": ["pct_chg", "change_pct", "pct_change", "涨跌幅"],
            "source": ["source", "provider"],
            "adjust": ["adjust"],
            "interval": ["interval", "bar_interval"],
        }
        rename_map: dict[Any, str] = {}
        for target, candidates in aliases.items():
            column = self._find_column(df, candidates)
            if column is not None:
                rename_map[column] = target
        normalized = df.rename(columns=rename_map).copy()
        for col in self.essential_cols:
            if col not in normalized.columns:
                normalized[col] = None
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
        normalized = normalized.dropna(subset=["date"]).sort_values("date")
        normalized["date"] = normalized["date"].dt.strftime("%Y-%m-%d")
        for col in ["open", "close", "high", "low", "volume", "amount", "turnover", "pct_chg"]:
            if col in normalized.columns:
                normalized[col] = pd.to_numeric(normalized[col], errors="coerce")
        normalized = normalized.dropna(subset=self.essential_cols)
        normalized = normalized.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
        if "amount" not in normalized.columns or normalized["amount"].isna().all():
            normalized["amount"] = normalized["close"] * normalized["volume"]
        if "turnover" not in normalized.columns:
            normalized["turnover"] = 0.0
        return normalized

    def _calculate_indicators(self, df):
        if pd is None:
            return df
        df = self._normalize_hist_cols(df)
        if df is None or df.empty:
            return df
        df["prev_close"] = df["close"].shift(1)
        df["pct_chg_calc"] = (df["close"] / df["prev_close"] - 1.0) * 100
        if "pct_chg" not in df.columns or df["pct_chg"].isna().all():
            df["pct_chg"] = df["pct_chg_calc"]
        df["ma20_close"] = df["close"].rolling(window=20, min_periods=5).mean()
        df["ma60_close"] = df["close"].rolling(window=60, min_periods=20).mean()
        df["ma20_volume"] = df["volume"].rolling(window=20, min_periods=5).mean()
        df["ma20_amount"] = df["amount"].rolling(window=20, min_periods=5).mean()
        df["volume_ratio_20"] = df["volume"] / df["ma20_volume"].shift(1).replace(0, pd.NA)
        df["amount_ratio_20"] = df["amount"] / df["ma20_amount"].shift(1).replace(0, pd.NA)
        day_range = (df["high"] - df["low"]).replace(0, pd.NA)
        df["close_position"] = (df["close"] - df["low"]) / day_range
        df["return_5d"] = df["close"] / df["close"].shift(5) - 1.0
        df["volatility_20"] = df["close"].pct_change().rolling(window=20, min_periods=5).std()
        return df

    def _limit_price(self, prev_close: float, rule: LimitUpRule) -> float | None:
        if prev_close <= 0 or rule.percent is None:
            return None
        return round(prev_close * (1.0 + rule.percent) + 1e-8, 2)

    def _is_limit_up_bar(self, row, rule: LimitUpRule) -> tuple[bool, float | None, float]:
        prev_close = self._safe_float(row.get("prev_close"))
        close = self._safe_float(row.get("close"))
        high = self._safe_float(row.get("high"))
        pct_chg = self._safe_float(row.get("pct_chg"))
        limit_price = self._limit_price(prev_close, rule)
        if limit_price is None:
            return False, None, pct_chg
        tolerance = self._float_config("limit_price_tolerance_pct", 0.003)
        price_hit = close >= limit_price * (1 - tolerance) and high >= limit_price * (1 - tolerance)
        pct_hit = pct_chg >= (rule.percent * 100) - 0.25
        return bool(price_hit or pct_hit), limit_price, pct_chg

    def _no_recent_limit_up(self, df, current_index: int, rule: LimitUpRule) -> bool:
        lookback = self._int_config("no_limit_up_lookback", 10)
        start = max(1, current_index - lookback)
        for idx in range(start, current_index):
            matched, _, _ = self._is_limit_up_bar(df.iloc[idx], rule)
            if matched:
                return False
        return True

    def _stock_info(self, row: dict) -> dict[str, Any]:
        code = str(row.get("code") or row.get("symbol") or row.get("stock_code") or row.get("代码") or row.get("证券代码") or "").strip()
        name = str(row.get("name") or row.get("stock_name") or row.get("名称") or row.get("证券简称") or code).strip()
        exchange = str(row.get("exchange") or infer_exchange(code)).strip().upper()
        security_type = str(row.get("security_type") or infer_security_type(code, name)).strip().lower()
        board_type = str(row.get("board_type") or infer_board_type(code, exchange=exchange, security_type=security_type)).strip().lower()
        return {
            "code": code,
            "name": name,
            "exchange": exchange,
            "market": str(row.get("market") or "").strip().lower(),
            "security_type": security_type,
            "board_type": board_type,
            "industry": str(row.get("industry") or "").strip(),
            "status": str(row.get("status") or "").strip().lower(),
            "is_st": bool(row.get("is_st")) or name.upper().replace(" ", "").startswith(("*ST", "ST")),
            "is_suspended": bool(row.get("is_suspended")),
            "is_delisting": bool(row.get("is_delisting")) or "退" in name,
        }

    def _should_exclude(self, info: dict[str, Any]) -> bool:
        code = info.get("code") or ""
        if not code:
            return True
        if info.get("security_type") != "stock":
            return True
        if self._bool_config("exclude_st", True) and info.get("is_st"):
            return True
        if info.get("is_suspended") or info.get("status") in {"suspended", "halted"}:
            return True
        if info.get("is_delisting"):
            return True
        if self._bool_config("exclude_kechuang", False) and code.startswith(("688", "689")):
            return True
        if self._bool_config("exclude_bj", True) and (info.get("exchange") == "BJ" or code.startswith(("4", "8", "920"))):
            return True
        return False

    def _sector_key(self, info: dict[str, Any]) -> str:
        return str(info.get("industry") or info.get("board_type") or info.get("exchange") or "unknown").strip() or "unknown"

    def _history_summary(self, info: dict[str, Any], df) -> dict[str, Any] | None:
        if df is None or getattr(df, "empty", True) or len(df) < 2:
            return None
        rule = infer_limit_up_rule(info.get("code"), info.get("name"), info.get("exchange"), info.get("security_type"))
        last = df.iloc[-1]
        limit_up, _, pct_chg = self._is_limit_up_bar(last, rule)
        close = self._safe_float(last.get("close"))
        ma20 = self._safe_float(last.get("ma20_close"))
        return {
            "code": info.get("code"),
            "sector_key": self._sector_key(info),
            "pct_chg": pct_chg,
            "limit_up": limit_up,
            "above_ma20": bool(ma20 > 0 and close >= ma20),
            "amount": self._safe_float(last.get("amount")),
            "turnover": self._safe_float(last.get("turnover")),
            "rule_percent": rule.percent or 0.10,
        }

    def _candidate_from_frame(self, info: dict[str, Any], df) -> tuple[dict[str, Any] | None, str]:
        if df is None or getattr(df, "empty", True):
            return None, "no history"
        if len(df) < self._int_config("min_bars", 35):
            return None, "insufficient history"
        rule = infer_limit_up_rule(info.get("code"), info.get("name"), info.get("exchange"), info.get("security_type"))
        if rule.percent is None:
            return None, "limit rule unavailable"

        last = df.iloc[-1]
        limit_up, limit_price, pct_chg = self._is_limit_up_bar(last, rule)
        if not limit_up or limit_price is None:
            return None, "not limit-up"
        if not self._no_recent_limit_up(df, len(df) - 1, rule):
            return None, "not first limit-up"

        close = self._safe_float(last.get("close"))
        price_limit = self._float_config("price_limit", 0)
        if price_limit > 0 and close > price_limit:
            return None, "price above limit"

        turnover = self._safe_float(last.get("turnover"))
        amount = self._safe_float(last.get("amount"))
        amount_ratio_20 = self._safe_float(last.get("amount_ratio_20"), 1.0)
        volume_ratio_20 = self._safe_float(last.get("volume_ratio_20"), 1.0)
        open_price = self._safe_float(last.get("open"))
        low = self._safe_float(last.get("low"))
        close_position = self._safe_float(last.get("close_position"), 1.0)

        risk_flags: list[str] = []
        if not rule.confirmed:
            risk_flags.append("limit_rule_unconfirmed")

        min_amount = self._float_config("min_amount", 20_000_000)
        if min_amount > 0 and amount < min_amount:
            return None, "amount below minimum"
        if turnover > 0 and turnover < self._float_config("min_turnover", 1.5):
            return None, "turnover below minimum"
        if turnover > self._float_config("max_turnover", 35.0):
            return None, "turnover too high"
        if amount_ratio_20 < self._float_config("min_amount_ratio_20", 0.5):
            return None, "amount ratio too low"
        if amount_ratio_20 > self._float_config("max_amount_ratio_20", 5.0) and close_position < 0.9:
            return None, "over-volume weak close"

        one_word = (
            abs(open_price - limit_price) / limit_price <= self._float_config("limit_price_tolerance_pct", 0.003)
            and abs(low - limit_price) / limit_price <= self._float_config("limit_price_tolerance_pct", 0.003)
        )
        if one_word and (
            (turnover > 0 and turnover < self._float_config("one_word_turnover", 1.5))
            or amount_ratio_20 < self._float_config("one_word_amount_ratio", 0.55)
        ):
            return None, "one-word shrink limit-up"

        if self._safe_float(last.get("return_5d")) > 0.35:
            risk_flags.append("short_term_overheated")
        if self._safe_float(last.get("volatility_20")) > 0.06:
            risk_flags.append("high_volatility")
        if turnover <= 0:
            risk_flags.append("turnover_missing")

        return {
            "info": info,
            "df": df,
            "rule": rule,
            "last": last.to_dict(),
            "limit_price": limit_price,
            "pct_chg": pct_chg,
            "amount": amount,
            "turnover": turnover,
            "amount_ratio_20": amount_ratio_20,
            "volume_ratio_20": volume_ratio_20,
            "close_position": close_position,
            "one_word": one_word,
            "sector_key": self._sector_key(info),
            "risk_flags": risk_flags,
        }, "candidate"

    def _market_context(self, summaries: list[dict[str, Any]]) -> dict[str, Any]:
        valid = [item for item in summaries if item]
        total = len(valid)
        if not total:
            return {
                "total": 0,
                "advancers": 0,
                "decliners": 0,
                "limit_up_count": 0,
                "limit_down_count": 0,
                "advance_ratio": 0.5,
                "above_ma20_ratio": 0.5,
                "score": 8.0,
                "regime": "neutral",
            }
        advancers = sum(1 for item in valid if self._safe_float(item.get("pct_chg")) > 0)
        decliners = sum(1 for item in valid if self._safe_float(item.get("pct_chg")) < 0)
        limit_up_count = sum(1 for item in valid if item.get("limit_up"))
        limit_down_count = sum(
            1
            for item in valid
            if self._safe_float(item.get("pct_chg")) <= -(self._safe_float(item.get("rule_percent"), 0.10) * 100 - 0.25)
        )
        above_ma20 = sum(1 for item in valid if item.get("above_ma20"))
        advance_ratio = advancers / total
        above_ma20_ratio = above_ma20 / total
        limit_ratio = limit_up_count / total

        score = 7.5
        if advance_ratio >= 0.60:
            score += 3.0
        elif advance_ratio <= 0.35:
            score -= 4.0
        if above_ma20_ratio >= 0.55:
            score += 2.0
        elif above_ma20_ratio <= 0.30:
            score -= 2.0
        if limit_up_count >= max(2, int(total * 0.03)) or limit_ratio >= 0.04:
            score += 2.5
        if limit_down_count > limit_up_count:
            score -= 4.0
        score = max(0.0, min(15.0, score))
        if score >= 11:
            regime = "risk_on"
        elif score <= 5:
            regime = "risk_off"
        else:
            regime = "neutral"
        return {
            "total": total,
            "advancers": advancers,
            "decliners": decliners,
            "limit_up_count": limit_up_count,
            "limit_down_count": limit_down_count,
            "advance_ratio": round(advance_ratio, 4),
            "above_ma20_ratio": round(above_ma20_ratio, 4),
            "score": round(score, 2),
            "regime": regime,
        }

    def _sector_context(self, summaries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in summaries:
            grouped.setdefault(str(item.get("sector_key") or "unknown"), []).append(item)
        result = {}
        for key, items in grouped.items():
            total = len(items)
            limit_count = sum(1 for item in items if item.get("limit_up"))
            advancers = sum(1 for item in items if self._safe_float(item.get("pct_chg")) > 0)
            avg_pct = sum(self._safe_float(item.get("pct_chg")) for item in items) / total if total else 0.0
            result[key] = {
                "sector_key": key,
                "total": total,
                "limit_up_count": limit_count,
                "advance_ratio": round(advancers / total, 4) if total else 0,
                "avg_pct_chg": round(avg_pct, 4),
            }
        return result

    def _limit_quality_score(self, candidate: dict[str, Any]) -> float:
        last = candidate["last"]
        limit_price = self._safe_float(candidate.get("limit_price"))
        close = self._safe_float(last.get("close"))
        high = self._safe_float(last.get("high"))
        close_position = self._safe_float(candidate.get("close_position"), 1.0)
        amount_ratio = self._safe_float(candidate.get("amount_ratio_20"), 1.0)
        turnover = self._safe_float(candidate.get("turnover"))

        score = 0.0
        if limit_price > 0 and abs(close - limit_price) / limit_price <= 0.003:
            score += 8
        elif limit_price > 0 and close >= limit_price * 0.995:
            score += 6
        if limit_price > 0 and high >= limit_price * 0.997:
            score += 4
        if close_position >= 0.95:
            score += 4
        elif close_position >= 0.85:
            score += 2
        if 1.0 <= amount_ratio <= 3.5:
            score += 5
        elif 0.7 <= amount_ratio < 1.0 or 3.5 < amount_ratio <= 5.0:
            score += 3
        if 3.0 <= turnover <= 15.0:
            score += 4
        elif 1.5 <= turnover < 3.0 or 15.0 < turnover <= 25.0:
            score += 2
        if candidate.get("one_word"):
            score -= 2
        return round(max(0.0, min(25.0, score)), 2)

    def _volume_score(self, candidate: dict[str, Any]) -> float:
        amount = self._safe_float(candidate.get("amount"))
        amount_ratio = self._safe_float(candidate.get("amount_ratio_20"), 1.0)
        volume_ratio = self._safe_float(candidate.get("volume_ratio_20"), 1.0)
        turnover = self._safe_float(candidate.get("turnover"))
        score = 0.0
        if amount >= 500_000_000:
            score += 5
        elif amount >= 100_000_000:
            score += 4
        elif amount >= 20_000_000:
            score += 2.5
        if 1.0 <= amount_ratio <= 3.5:
            score += 4
        elif 0.6 <= amount_ratio < 1.0 or 3.5 < amount_ratio <= 5.0:
            score += 2
        if 1.0 <= volume_ratio <= 3.5:
            score += 3
        elif 0.6 <= volume_ratio < 1.0 or 3.5 < volume_ratio <= 5.0:
            score += 1.5
        if 3.0 <= turnover <= 18.0:
            score += 3
        elif turnover > 0:
            score += 1.5
        return round(max(0.0, min(15.0, score)), 2)

    def _stock_character_score(self, candidate: dict[str, Any]) -> tuple[float, dict[str, Any]]:
        df = candidate["df"]
        rule = candidate["rule"]
        events = []
        for idx in range(1, max(1, len(df) - 1)):
            if idx >= len(df) - 1:
                continue
            matched, _, _ = self._is_limit_up_bar(df.iloc[idx], rule)
            if not matched:
                continue
            current = df.iloc[idx]
            next_row = df.iloc[idx + 1]
            base = self._safe_float(current.get("close"))
            if base <= 0:
                continue
            next_open = self._safe_float(next_row.get("open"))
            next_high = self._safe_float(next_row.get("high"))
            next_close = self._safe_float(next_row.get("close"))
            next_limit, _, _ = self._is_limit_up_bar(next_row, rule)
            events.append(
                {
                    "open_up": next_open > base,
                    "close_up": next_close > base,
                    "next_limit": next_limit,
                    "high_follow_pct": (next_high / base) - 1.0 if next_high > 0 else 0.0,
                }
            )
        if not events:
            return 7.5, {
                "sample_count": 0,
                "next_open_up_rate": None,
                "next_close_up_rate": None,
                "next_limit_rate": None,
                "avg_high_follow_pct": None,
            }
        total = len(events)
        open_rate = sum(1 for item in events if item["open_up"]) / total
        close_rate = sum(1 for item in events if item["close_up"]) / total
        next_limit_rate = sum(1 for item in events if item["next_limit"]) / total
        avg_high_follow = sum(item["high_follow_pct"] for item in events) / total
        score = 5.0 + open_rate * 3.0 + close_rate * 2.0 + next_limit_rate * 4.0 + min(max(avg_high_follow, 0.0) * 40, 1.0)
        return round(max(0.0, min(15.0, score)), 2), {
            "sample_count": total,
            "next_open_up_rate": round(open_rate, 4),
            "next_close_up_rate": round(close_rate, 4),
            "next_limit_rate": round(next_limit_rate, 4),
            "avg_high_follow_pct": round(avg_high_follow, 4),
        }

    def _sector_score(self, candidate: dict[str, Any], sector_context: dict[str, dict[str, Any]]) -> float:
        sector = sector_context.get(candidate.get("sector_key")) or {}
        score = 8.0
        limit_count = int(sector.get("limit_up_count") or 0)
        advance_ratio = self._safe_float(sector.get("advance_ratio"), 0.5)
        avg_pct = self._safe_float(sector.get("avg_pct_chg"))
        if limit_count >= 3:
            score += 7
        elif limit_count == 2:
            score += 4
        elif limit_count == 1:
            score += 2
        if advance_ratio >= 0.60:
            score += 3
        elif advance_ratio <= 0.35:
            score -= 2
        if avg_pct >= 2:
            score += 2
        elif avg_pct < 0:
            score -= 2
        return round(max(0.0, min(20.0, score)), 2)

    def _score_candidate(
        self,
        candidate: dict[str, Any],
        market_context: dict[str, Any],
        sector_context: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        risk_flags = list(candidate.get("risk_flags") or [])
        market_score = self._safe_float(market_context.get("score"), 8.0)
        if market_score / 15.0 * 100 < self._float_config("market_min_score", 40):
            risk_flags.append("weak_market_regime")
        sector_score = self._sector_score(candidate, sector_context)
        quality_score = self._limit_quality_score(candidate)
        volume_score = self._volume_score(candidate)
        character_score, character_stats = self._stock_character_score(candidate)
        event_risk_score = max(0.0, 10.0 - len(set(risk_flags)) * 2.0)
        total_score = market_score + sector_score + quality_score + volume_score + character_score + event_risk_score
        total_score = round(max(0.0, min(100.0, total_score)), 2)
        if total_score < self._float_config("min_preselect_score", 70):
            return None
        return {
            **candidate,
            "component_scores": {
                "market": round(market_score, 2),
                "sector": sector_score,
                "limit_quality": quality_score,
                "volume_liquidity": volume_score,
                "stock_character": character_score,
                "event_risk": round(event_risk_score, 2),
            },
            "stock_character": character_stats,
            "market_context": market_context,
            "sector_context": sector_context.get(candidate.get("sector_key")) or {},
            "preselect_score": total_score,
            "risk_flags": sorted(set(risk_flags)),
        }

    def _get_snapshot(self, symbol: str) -> dict | None:
        try:
            from backend.repositories import market_data_repo

            return market_data_repo.get_latest_snapshot(symbol)
        except Exception:
            return None

    def _get_auction_snapshot(self, symbol: str) -> dict | None:
        try:
            from backend.repositories import market_data_repo

            return market_data_repo.get_latest_auction_snapshot(symbol)
        except Exception:
            return None

    def _auction_microstructure_score(self, snapshot: dict[str, Any], matched_volume: float) -> tuple[float, dict[str, Any], bool]:
        buy_volume = self._safe_float(snapshot.get("unmatched_buy_volume") or snapshot.get("bid_volume"))
        sell_volume = self._safe_float(snapshot.get("unmatched_sell_volume") or snapshot.get("ask_volume"))
        withdrawal_buy = self._safe_float(snapshot.get("withdrawal_buy_volume"))
        withdrawal_sell = self._safe_float(snapshot.get("withdrawal_sell_volume"))
        seal_volume = self._safe_float(snapshot.get("seal_volume"))
        seal_side = str(snapshot.get("seal_side") or "").strip().lower()

        has_book = buy_volume > 0 or sell_volume > 0
        if has_book:
            total_book = buy_volume + sell_volume
            book_imbalance = (buy_volume - sell_volume) / total_book if total_book > 0 else 0.0
            book_score = 5.0 if book_imbalance >= 0.25 else 3.0 if book_imbalance >= -0.10 else 0.0
        else:
            book_imbalance = None
            book_score = 5.0

        if seal_volume > 0 and seal_side in {"buy", "bid", "b"}:
            seal_score = 5.0
        elif seal_volume > 0 and seal_side in {"sell", "ask", "s"}:
            seal_score = 0.0
        else:
            seal_score = 5.0 if not has_book else 2.5

        withdrawal_pressure = withdrawal_sell / matched_volume if matched_volume > 0 and withdrawal_sell > 0 else 0.0
        micro_ok = True
        if book_imbalance is not None and book_imbalance < -0.20:
            micro_ok = False
        if withdrawal_pressure > 1.5 and withdrawal_sell > max(withdrawal_buy * 2, matched_volume):
            micro_ok = False
        if seal_volume > 0 and seal_side in {"sell", "ask", "s"}:
            micro_ok = False

        return round(book_score + seal_score, 2), {
            "unmatched_buy_volume": buy_volume,
            "unmatched_sell_volume": sell_volume,
            "order_book_imbalance": round(book_imbalance, 4) if book_imbalance is not None else None,
            "withdrawal_buy_volume": withdrawal_buy,
            "withdrawal_sell_volume": withdrawal_sell,
            "withdrawal_sell_pressure": round(withdrawal_pressure, 4),
            "seal_side": seal_side,
            "seal_volume": seal_volume,
            "seal_amount": self._safe_float(snapshot.get("seal_amount")),
        }, micro_ok

    def _auction_confirmation(self, candidate: dict[str, Any]) -> dict[str, Any]:
        info = candidate["info"]
        last = candidate["last"]
        rule = candidate["rule"]
        auction_snapshot = self._get_auction_snapshot(info["code"])
        snapshot = auction_snapshot or self._get_snapshot(info["code"])
        if not snapshot:
            return {
                "available": False,
                "signal_subtype": "preopen_watch",
                "signal": "first_limit_watch",
                "score": None,
                "reason": "T-day first-limit candidate; waiting for T+1 9:20-9:25 auction/order-book confirmation.",
                "snapshot": None,
                "metrics": {"auction_data_source": "missing"},
            }
        uses_auction_model = bool(auction_snapshot)
        prev_close = self._safe_float(snapshot.get("prev_close"))
        open_price = self._safe_float(snapshot.get("indicative_price") if uses_auction_model else snapshot.get("open"))
        last_price = self._safe_float(snapshot.get("indicative_price") if uses_auction_model else snapshot.get("last_price"))
        snapshot_amount = self._safe_float(snapshot.get("matched_amount") if uses_auction_model else snapshot.get("amount"))
        snapshot_volume = self._safe_float(snapshot.get("matched_volume") if uses_auction_model else snapshot.get("volume"))
        t_close = self._safe_float(last.get("close"))
        t_amount = self._safe_float(last.get("amount"))
        t_volume = self._safe_float(last.get("volume"))
        if prev_close <= 0 or open_price <= 0 or t_close <= 0:
            return {
                "available": False,
                "signal_subtype": "preopen_watch",
                "signal": "first_limit_watch",
                "score": None,
                "reason": "Auction/open snapshot exists but indicative/open price or prev_close is incomplete; keep observation-only.",
                "snapshot": snapshot,
                "metrics": {"auction_data_source": "auction_model" if uses_auction_model else "quote_snapshot"},
            }
        if abs(prev_close - t_close) / t_close > 0.03:
            return {
                "available": False,
                "signal_subtype": "preopen_watch",
                "signal": "first_limit_watch",
                "score": None,
                "reason": "Auction/open snapshot prev_close does not match T-day limit-up close; keep observation-only.",
                "snapshot": snapshot,
                "metrics": {"prev_close": prev_close, "t_close": t_close, "auction_data_source": "auction_model" if uses_auction_model else "quote_snapshot"},
            }

        open_gap = (open_price / prev_close) - 1.0
        limit_rate = rule.percent or 0.10
        normalized_open = open_gap / limit_rate if limit_rate else 0.0
        amount_ratio = snapshot_amount / t_amount if t_amount > 0 and snapshot_amount > 0 else 0.0
        volume_ratio = snapshot_volume / t_volume if t_volume > 0 and snapshot_volume > 0 else 0.0
        price_stability = (last_price / open_price - 1.0) if last_price > 0 and open_price > 0 else 0.0

        open_score = 25.0 if self._float_config("auction_open_min_ratio", 0.20) <= normalized_open <= self._float_config("auction_open_max_ratio", 0.75) else 8.0
        if normalized_open <= 0:
            open_score = 0.0
        elif normalized_open > self._float_config("auction_open_reject_ratio", 0.90):
            open_score = 6.0
        amount_score = 25.0 if amount_ratio >= self._float_config("auction_amount_ratio_min", 0.03) else max(0.0, amount_ratio / self._float_config("auction_amount_ratio_min", 0.03) * 18.0)
        volume_score = 15.0 if volume_ratio >= self._float_config("auction_volume_ratio_min", 0.03) else max(0.0, volume_ratio / self._float_config("auction_volume_ratio_min", 0.03) * 10.0)
        stability_score = 10.0 if price_stability >= -0.005 else 5.0 if price_stability >= -0.015 else 0.0
        sector_score = min(15.0, self._safe_float(candidate.get("component_scores", {}).get("sector")) / 20.0 * 15.0)
        market_score = min(5.0, self._safe_float(candidate.get("component_scores", {}).get("market")) / 15.0 * 5.0)
        imbalance_score, micro_metrics, micro_ok = (
            self._auction_microstructure_score(snapshot, snapshot_volume) if uses_auction_model else (10.0, {}, True)
        )
        score = round(open_score + amount_score + volume_score + stability_score + sector_score + market_score + imbalance_score, 2)

        hard_confirmed = (
            self._float_config("auction_open_min_ratio", 0.20)
            <= normalized_open
            <= self._float_config("auction_open_max_ratio", 0.75)
            and amount_ratio >= self._float_config("auction_amount_ratio_min", 0.03)
            and volume_ratio >= self._float_config("auction_volume_ratio_min", 0.03)
            and snapshot_amount >= self._float_config("min_auction_amount", 3_000_000)
            and price_stability >= -0.015
            and micro_ok
        )
        confirmed = hard_confirmed and score >= self._float_config("min_auction_score", 70)
        signal_subtype = "auction_confirmed" if confirmed else "auction_rejected"
        reason = (
            "T+1 9:20-9:25 auction model confirms suitable gap, matched volume, order-book/withdrawal/seal support."
            if confirmed and uses_auction_model
            else "T+1 auction/open snapshot confirms suitable gap, volume commitment, and sector/market support."
            if confirmed
            else "T+1 9:20-9:25 auction/order-book data does not meet entry confirmation rules."
            if uses_auction_model
            else "T+1 auction/open snapshot does not meet entry confirmation rules."
        )
        return {
            "available": True,
            "signal_subtype": signal_subtype,
            "signal": "auction_entry_confirmed" if confirmed else "auction_rejected",
            "score": score,
            "reason": reason,
            "snapshot": snapshot,
            "metrics": {
                "open_gap_pct": round(open_gap * 100, 4),
                "normalized_open_strength": round(normalized_open, 4),
                "amount_ratio_to_limit_day": round(amount_ratio, 4),
                "volume_ratio_to_limit_day": round(volume_ratio, 4),
                "price_stability_pct": round(price_stability * 100, 4),
                "snapshot_amount": snapshot_amount,
                "snapshot_volume": snapshot_volume,
                "auction_data_source": "auction_model" if uses_auction_model else "quote_snapshot",
                "auction_phase": snapshot.get("phase") or ("call_auction_0920_0925" if uses_auction_model else "open_snapshot"),
                **micro_metrics,
            },
        }

    def _build_recommend_reason(self, candidate: dict[str, Any], auction: dict[str, Any]) -> str:
        info = candidate["info"]
        market = candidate["market_context"]
        sector = candidate["sector_context"]
        scores = candidate["component_scores"]
        if auction["signal_subtype"] == "auction_confirmed":
            auction_text = (
                f"T+1竞价确认：高开{auction['metrics'].get('open_gap_pct', 0):.2f}%，"
                f"竞价/快照成交额为T日{auction['metrics'].get('amount_ratio_to_limit_day', 0) * 100:.1f}%。"
            )
        elif auction["signal_subtype"] == "auction_rejected":
            auction_text = "T+1竞价未达到上车条件，模型建议放弃或继续观察。"
        else:
            auction_text = "T日预选通过，等待T+1 9:20-9:25后的真实竞价确认。"
        return (
            f"{info['code']} {info['name']}为首板涨停候选，近{self._int_config('no_limit_up_lookback', 10)}个交易日无涨停；"
            f"预选分{candidate['preselect_score']:.1f}/100。"
            f"大盘情绪{market.get('regime')}，涨停{market.get('limit_up_count')}家、跌停{market.get('limit_down_count')}家；"
            f"板块/分组{candidate.get('sector_key')}内涨停{sector.get('limit_up_count', 0)}只；"
            f"涨停质量{scores['limit_quality']:.1f}/25、量能流动性{scores['volume_liquidity']:.1f}/15、股性{scores['stock_character']:.1f}/15。"
            f"{auction_text}"
        )

    def _build_payload(self, candidate: dict[str, Any], auction: dict[str, Any]) -> dict[str, Any]:
        info = candidate["info"]
        last = candidate["last"]
        rule = candidate["rule"]
        auction_score = auction.get("score")
        final_score = candidate["preselect_score"] if auction_score is None else round(candidate["preselect_score"] * 0.6 + self._safe_float(auction_score) * 0.4, 2)
        risk_flags = list(candidate.get("risk_flags") or [])
        if auction["signal_subtype"] == "auction_rejected":
            risk_flags.append("auction_not_confirmed")
        if auction["signal_subtype"] == "preopen_watch":
            risk_flags.append("auction_pending")
        risk_score = round(max(0.0, min(100.0, 100.0 - final_score + len(set(risk_flags)) * 4.0)), 1)
        risk_level = "high" if risk_score >= 70 else "medium" if risk_score >= 45 else "low"
        recommend_reason = self._build_recommend_reason(candidate, auction)
        signal_type = "BUY" if auction["signal_subtype"] == "auction_confirmed" else "WATCH"
        phase = {
            "TDayFirstLimitUp": True,
            "MarketRegime": candidate["market_context"].get("regime"),
            "SectorBreadth": candidate["sector_context"],
            "AuctionConfirmation": auction["signal_subtype"] == "auction_confirmed",
            "signal_subtype": auction["signal_subtype"],
        }
        indicators = {
            "first_limit_up": {
                "limit_rule": asdict(rule),
                "limit_up_date": str(last.get("date")),
                "limit_up_price": round(self._safe_float(last.get("close")), 4),
                "limit_price": round(self._safe_float(candidate.get("limit_price")), 4),
                "pct_chg": round(self._safe_float(candidate.get("pct_chg")), 4),
                "amount": round(self._safe_float(candidate.get("amount")), 2),
                "turnover": round(self._safe_float(candidate.get("turnover")), 4),
                "amount_ratio_20": round(self._safe_float(candidate.get("amount_ratio_20")), 4),
                "volume_ratio_20": round(self._safe_float(candidate.get("volume_ratio_20")), 4),
                "close_position": round(self._safe_float(candidate.get("close_position")), 4),
                "one_word": bool(candidate.get("one_word")),
            },
            "market": candidate["market_context"],
            "sector": candidate["sector_context"],
            "scores": candidate["component_scores"],
            "stock_character": candidate["stock_character"],
            "auction": auction["metrics"],
            "preselect_score": candidate["preselect_score"],
            "auction_score": auction_score,
            "final_score": final_score,
        }
        return {
            "schema_version": SIGNAL_SCHEMA_VERSION,
            "strategy_code": self.get_code(),
            "code": info["code"],
            "symbol": info["code"],
            "name": info["name"],
            "stock_name": info["name"],
            "market": info.get("exchange") or "",
            "security_type": info.get("security_type") or "stock",
            "bar_interval": self.config.get("bar_interval") or "1d",
            "interval": self.config.get("bar_interval") or "1d",
            "adjust": self.config.get("adjust") or "qfq",
            "signal_date": str(last.get("date")),
            "trade_date": str(last.get("date")),
            "date": str(last.get("date")),
            "signal": auction["signal"],
            "signal_type": signal_type,
            "signal_subtype": auction["signal_subtype"],
            "reason_tag": auction["signal"],
            "signal_strength": 5 if auction["signal_subtype"] == "auction_confirmed" else 3,
            "score": final_score,
            "total_score": final_score,
            "preselect_score": candidate["preselect_score"],
            "auction_score": auction_score,
            "second_board_score": final_score,
            "second_board_expectation": "confirmed_entry" if auction["signal_subtype"] == "auction_confirmed" else "watch_only",
            "prediction_reason": recommend_reason,
            "recommend_reason": recommend_reason,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_flags": sorted(set(risk_flags)),
            "pick_price": round(self._safe_float(last.get("close")), 4),
            "last_price": round(self._safe_float(last.get("close")), 4),
            "price_ref": round(self._safe_float(last.get("close")), 4),
            "limit_up_date": str(last.get("date")),
            "limit_up_price": round(self._safe_float(last.get("close")), 4),
            "volume": self._safe_int(last.get("volume")),
            "amount": round(self._safe_float(last.get("amount")), 2),
            "turnover": round(self._safe_float(last.get("turnover")), 4),
            "indicators": indicators,
            "phase": phase,
            "risk": {"risk_score": risk_score, "risk_level": risk_level, "risk_flags": sorted(set(risk_flags))},
            "data": {
                "source": str(last.get("source") or "local"),
                "provider": str(last.get("source") or "local"),
                "data_quality": "primary",
                "fallback_used": False,
                "bar_count": int(len(candidate["df"])),
                "latest_bar_time": str(last.get("date")),
                "auction_snapshot": auction.get("snapshot"),
            },
            "reason": recommend_reason,
            "note": recommend_reason,
        }

    def _get_hist(self, stock_code: str, target_date: str | None, bar_interval: str, adjust: str):
        from backend.services.stock_data_service import get_stock_data_service

        end_date = datetime.strptime(target_date, "%Y-%m-%d") if target_date else datetime.now()
        start_date = end_date - timedelta(days=int(self.config["lookback_days"]))
        stock_data = get_stock_data_service()
        try:
            return stock_data.get_stock_hist(
                symbol=stock_code,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                adjust=adjust,
                interval=bar_interval,
            )
        except TypeError:
            return stock_data.get_stock_hist(
                stock_code,
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
                adjust=adjust,
            )

    def _get_stock_list(self):
        if pd is None:
            return []
        try:
            from backend.repositories import market_data_repo

            payload = market_data_repo.list_stocks(limit=int(self.config["scan_limit"]), security_type="stock")
            rows = payload.get("items") or []
            if rows:
                return pd.DataFrame(
                    [
                        {
                            "code": item.get("symbol") or item.get("code"),
                            "name": item.get("name"),
                            "exchange": item.get("exchange"),
                            "market": item.get("market"),
                            "security_type": item.get("security_type") or "stock",
                            "industry": item.get("industry") or "",
                            "board_type": item.get("board_type"),
                            "status": item.get("status"),
                            "is_st": item.get("is_st"),
                            "is_suspended": item.get("is_suspended"),
                            "is_delisting": item.get("is_delisting"),
                        }
                        for item in rows
                    ]
                )
        except Exception:
            pass
        from backend.services.stock_data_service import get_stock_data_service

        return get_stock_data_service().get_stock_list()

    def _row_records(self, stock_list) -> list[dict[str, Any]]:
        if stock_list is None:
            return []
        if pd is not None and hasattr(stock_list, "iterrows"):
            return [dict(row) for _, row in stock_list.iterrows()]
        return [dict(item) for item in stock_list]

    def _analyze_stock(
        self,
        stock_code: str,
        stock_name: str,
        market: str = "",
        target_date: str | None = None,
        security_type: str = "stock",
        bar_interval: str | None = None,
        adjust: str | None = None,
    ) -> tuple[bool, str, dict[str, Any]]:
        if pd is None:
            return False, "pandas unavailable", {}
        info = self._stock_info(
            {
                "code": stock_code,
                "name": stock_name,
                "exchange": market or infer_exchange(stock_code),
                "security_type": security_type,
            }
        )
        if self._should_exclude(info):
            return False, "excluded security", {}
        bar_interval = str(bar_interval or self.config.get("bar_interval") or "1d")
        adjust = str(adjust or self.config.get("adjust") or "qfq")
        try:
            df = self._calculate_indicators(self._get_hist(info["code"], target_date, bar_interval, adjust))
            summary = self._history_summary(info, df)
            candidate, reason = self._candidate_from_frame(info, df)
            if not candidate:
                return False, reason, {}
            market_context = self._market_context([summary] if summary else [])
            sector_context = self._sector_context([summary] if summary else [])
            scored = self._score_candidate(candidate, market_context, sector_context)
            if not scored:
                return False, "preselect score below threshold", {}
            auction = self._auction_confirmation(scored)
            if auction["signal_subtype"] == "auction_rejected" and not self._bool_config("include_rejected", False):
                return False, "auction rejected", {}
            payload = self._build_payload(scored, auction)
            return True, payload["signal_subtype"], payload
        except Exception as exc:
            return False, f"strategy error:{exc}", {}

    def scan(self, date: str | None = None) -> list[dict[str, Any]]:
        if pd is None:
            return []
        stock_list = self._get_stock_list()
        records = self._row_records(stock_list)
        if not records:
            return []
        scan_limit = int(self.config.get("scan_limit") or 600)
        if scan_limit > 0:
            records = records[:scan_limit]
        bar_interval = str(self.config.get("bar_interval") or "1d")
        adjust = str(self.config.get("adjust") or "qfq")

        summaries: list[dict[str, Any]] = []
        raw_candidates: list[dict[str, Any]] = []
        for row in records:
            info = self._stock_info(row)
            if self._should_exclude(info):
                continue
            try:
                df = self._calculate_indicators(self._get_hist(info["code"], date, bar_interval, adjust))
            except Exception:
                continue
            summary = self._history_summary(info, df)
            if summary:
                summaries.append(summary)
            candidate, _ = self._candidate_from_frame(info, df)
            if candidate:
                raw_candidates.append(candidate)

        market_context = self._market_context(summaries)
        sector_context = self._sector_context(summaries)
        results: list[dict[str, Any]] = []
        for candidate in raw_candidates:
            scored = self._score_candidate(candidate, market_context, sector_context)
            if not scored:
                continue
            auction = self._auction_confirmation(scored)
            if auction["signal_subtype"] == "auction_rejected" and not self._bool_config("include_rejected", False):
                continue
            results.append(self._build_payload(scored, auction))

        rank = {"auction_confirmed": 0, "preopen_watch": 1, "auction_rejected": 2}
        results.sort(
            key=lambda item: (
                rank.get(str(item.get("signal_subtype")), 9),
                -self._safe_float(item.get("total_score")),
                self._safe_float(item.get("risk_score")),
                str(item.get("code")),
            )
        )
        return results[: int(self.config.get("select_count") or 10)]

    def backtest(self, start_date: str, end_date: str) -> dict[str, Any]:
        from backend.services.stock_data_service import get_stock_data_service

        dates = get_stock_data_service().get_trading_dates(start_date, end_date)
        if not dates:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            dates = []
            current = start
            while current <= end:
                if current.weekday() < 5:
                    dates.append(current.strftime("%Y-%m-%d"))
                current += timedelta(days=1)
        daily_results = []
        all_signals: list[dict[str, Any]] = []
        for trade_date in dates:
            signals = self.scan(trade_date)
            daily_results.append({"date": trade_date, "count": len(signals), "signals": signals})
            all_signals.extend(signals)
        subtypes: dict[str, int] = {}
        for item in all_signals:
            subtype = str(item.get("signal_subtype") or "")
            subtypes[subtype] = subtypes.get(subtype, 0) + 1
        avg_score = sum(self._safe_float(item.get("total_score")) for item in all_signals) / len(all_signals) if all_signals else 0
        return {
            "start_date": start_date,
            "end_date": end_date,
            "total_trading_days": len(dates),
            "total_signals": len(all_signals),
            "avg_signals_per_day": round(len(all_signals) / len(dates), 2) if dates else 0,
            "signal_subtypes": subtypes,
            "avg_total_score": round(avg_score, 2),
            "daily_results": daily_results,
        }
