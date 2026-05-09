"""Limit-up pullback and re-attack strategy.

The strategy models a common A-share sequence:

1. LimitUpEvent: a confirmed limit-up bar.
2. PullbackValid: a controlled pullback after the limit-up bar.
3. SupportConfirmed: price holds the limit-up support area.
4. ReAttackTrigger: renewed breakout/volume after the pullback.

It reads local-first historical bars through stock_data_service. Tests can stub
the service or the private history/list methods without touching the network.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any
import re

from backend.strategies import BaseStrategy, register_strategy

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - local test fallback
    pd = None


SIGNAL_SCHEMA_VERSION = "strategy-signal/limit-up-return/v1"


@dataclass(frozen=True)
class LimitUpRule:
    percent: float | None
    label: str
    confirmed: bool
    source: str
    risk_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class LimitUpEvent:
    index: int
    trade_date: str
    close: float
    prev_close: float
    limit_price: float
    pct_chg: float
    rule: LimitUpRule


@dataclass(frozen=True)
class PullbackValid:
    event_index: int
    low: float
    low_date: str
    pullback_pct: float
    bars_after_limit: int


@dataclass(frozen=True)
class SupportConfirmed:
    support_price: float
    close: float
    volume_ratio: float
    confirmed_date: str


@dataclass(frozen=True)
class ReAttackTrigger:
    trigger_price: float
    close: float
    volume_ratio: float
    trigger_date: str


def infer_limit_up_rule(
    symbol: str | None = None,
    name: str | None = None,
    market: str | None = None,
    security_type: str | None = None,
) -> LimitUpRule:
    """Infer the daily limit-up rule from stock identity fields.

    Returns a risk flag instead of guessing when the rule cannot be confirmed.
    """

    code = str(symbol or "").strip().lower()
    if code.startswith(("sh", "sz", "bj")):
        code = code[2:]
    stock_name = str(name or "").strip().upper()
    normalized_market = str(market or "").strip().lower()
    sec_type = str(security_type or "stock").strip().lower()

    if sec_type and sec_type not in {"stock", "a_share", "ashare"}:
        return LimitUpRule(None, "unknown", False, "security_type", ("limit_rule_unconfirmed",))

    if re.match(r"^\*?ST(\b|\s|[\u4e00-\u9fff])", stock_name):
        return LimitUpRule(0.05, "ST", True, "name")

    if normalized_market in {"bj", "bse", "beijing"} or code.startswith(
        ("43", "83", "87", "88", "89", "92", "4", "8")
    ):
        return LimitUpRule(0.30, "BJ", True, "symbol")

    if normalized_market in {"kc", "star", "sse_star", "kechuang"} or code.startswith(("688", "689")):
        return LimitUpRule(0.20, "STAR", True, "symbol")

    if normalized_market in {"cy", "gem", "chinext"} or code.startswith(("300", "301", "302")):
        return LimitUpRule(0.20, "CHINEXT", True, "symbol")

    if normalized_market in {"sh", "sz", "sse", "szse"} or code.startswith(
        ("000", "001", "002", "003", "600", "601", "603", "605")
    ):
        return LimitUpRule(0.10, "MAIN", True, "symbol")

    return LimitUpRule(None, "unknown", False, "identity", ("limit_rule_unconfirmed",))


@register_strategy
class StrategyLimitUpReturn(BaseStrategy):
    """Limit-up return/pullback strategy."""

    essential_cols = ["date", "open", "close", "high", "low", "volume"]

    def __init__(self):
        super().__init__()
        self.config = {
            "lookback_days": 180,
            "scan_limit": 600,
            "select_count": 20,
            "min_bars": 25,
            "max_event_age": 12,
            "pullback_min_pct": 0.025,
            "pullback_max_pct": 0.16,
            "support_tolerance_pct": 0.025,
            "breakout_buffer_pct": 0.01,
            "reattack_volume_ratio": 1.08,
            "shrink_volume_ratio": 0.92,
            "limit_price_tolerance_pct": 0.003,
            "price_limit": 0,
            "bar_interval": "1d",
            "adjust": "qfq",
        }

    def get_code(self) -> str:
        return "LIMIT_UP_RETURN"

    def get_name(self) -> str:
        return "Limit-up Pullback Return"

    def get_description(self) -> str:
        return "Detects limit-up pullback setups, confirmed re-attacks, and failed pullbacks from local market data."

    def get_category(self) -> str:
        return "Short-term event strategy"

    def get_parameters(self) -> dict[str, Any]:
        return {
            "max_event_age": {"type": "int", "default": 12, "min": 3, "max": 30},
            "pullback_max_pct": {"type": "float", "default": 0.16, "min": 0.04, "max": 0.30},
            "support_tolerance_pct": {"type": "float", "default": 0.025, "min": 0.0, "max": 0.08},
            "reattack_volume_ratio": {"type": "float", "default": 1.08, "min": 0.8, "max": 3.0},
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

    def _find_column(self, df, candidates: list[str]) -> str | None:
        lower_to_col = {str(col).strip().lower(): col for col in getattr(df, "columns", [])}
        for candidate in candidates:
            found = lower_to_col.get(candidate.lower())
            if found is not None:
                return found
        return None

    def _normalize_hist_cols(self, df):
        if pd is None or df is None or getattr(df, "empty", True):
            return df
        aliases = {
            "date": ["date", "trade_date", "datetime"],
            "open": ["open"],
            "close": ["close", "last_price"],
            "high": ["high"],
            "low": ["low"],
            "volume": ["volume", "vol"],
            "amount": ["amount"],
            "turnover": ["turnover", "turnover_rate"],
            "pct_chg": ["pct_chg", "change_pct", "pct_change"],
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
        if "amount" not in normalized.columns:
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
        df["ma5_volume"] = df["volume"].rolling(window=5, min_periods=1).mean()
        df["ma10_volume"] = df["volume"].rolling(window=10, min_periods=1).mean()
        df["volume_ratio_5"] = df["volume"] / df["ma5_volume"].shift(1).replace(0, pd.NA)
        df["high_since_5"] = df["high"].rolling(window=5, min_periods=1).max()
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
        tolerance = float(self.config["limit_price_tolerance_pct"])
        price_hit = close >= limit_price * (1 - tolerance) and high >= limit_price * (1 - tolerance)
        pct_hit = pct_chg >= (rule.percent * 100) - 0.25
        return bool(price_hit or pct_hit), limit_price, pct_chg

    def _find_latest_limit_up_event(self, df, rule: LimitUpRule) -> LimitUpEvent | None:
        if rule.percent is None or len(df) < 2:
            return None
        max_age = int(self.config["max_event_age"])
        start_index = max(1, len(df) - max_age - 1)
        for index in range(len(df) - 2, start_index - 1, -1):
            row = df.iloc[index]
            matched, limit_price, pct_chg = self._is_limit_up_bar(row, rule)
            if matched and limit_price is not None:
                return LimitUpEvent(
                    index=index,
                    trade_date=str(row.get("date")),
                    close=self._safe_float(row.get("close")),
                    prev_close=self._safe_float(row.get("prev_close")),
                    limit_price=limit_price,
                    pct_chg=pct_chg,
                    rule=rule,
                )
        return None

    def _pullback_valid(self, df, event: LimitUpEvent) -> PullbackValid | None:
        after = df.iloc[event.index + 1 :]
        if after.empty:
            return None
        low_idx = after["low"].astype(float).idxmin()
        low_row = df.loc[low_idx]
        low = self._safe_float(low_row.get("low"))
        if event.close <= 0:
            return None
        pullback_pct = (event.close - low) / event.close
        min_pullback = float(self.config["pullback_min_pct"])
        max_pullback = float(self.config["pullback_max_pct"])
        support_floor = event.prev_close * (1 - float(self.config["support_tolerance_pct"]))
        if min_pullback <= pullback_pct <= max_pullback and low >= support_floor:
            return PullbackValid(
                event_index=event.index,
                low=low,
                low_date=str(low_row.get("date")),
                pullback_pct=pullback_pct,
                bars_after_limit=len(after),
            )
        return None

    def _support_confirmed(self, df, event: LimitUpEvent, pullback: PullbackValid) -> SupportConfirmed | None:
        last = df.iloc[-1]
        close = self._safe_float(last.get("close"))
        support_price = max(event.prev_close, pullback.low)
        volume_ratio = self._safe_float(last.get("volume_ratio_5"), 1.0)
        close_holds = close >= support_price * (1 - float(self.config["support_tolerance_pct"]))
        controlled_volume = volume_ratio <= float(self.config["shrink_volume_ratio"]) or close >= event.close * 0.98
        if close_holds and controlled_volume:
            return SupportConfirmed(
                support_price=support_price,
                close=close,
                volume_ratio=volume_ratio,
                confirmed_date=str(last.get("date")),
            )
        return None

    def _reattack_trigger(self, df, event: LimitUpEvent, pullback: PullbackValid) -> ReAttackTrigger | None:
        last = df.iloc[-1]
        close = self._safe_float(last.get("close"))
        post_event = df.iloc[event.index + 1 :]
        if post_event.empty:
            return None
        prior_high = self._safe_float(post_event.iloc[:-1]["high"].max()) if len(post_event) > 1 else event.close
        trigger_price = max(event.close, prior_high) * (1 + float(self.config["breakout_buffer_pct"]))
        volume_ratio = self._safe_float(last.get("volume_ratio_5"), 0.0)
        if close >= trigger_price and volume_ratio >= float(self.config["reattack_volume_ratio"]):
            return ReAttackTrigger(
                trigger_price=trigger_price,
                close=close,
                volume_ratio=volume_ratio,
                trigger_date=str(last.get("date")),
            )
        return None

    def _failed_pullback(self, df, event: LimitUpEvent, pullback: PullbackValid | None) -> bool:
        last = df.iloc[-1]
        close = self._safe_float(last.get("close"))
        support = max(event.prev_close, pullback.low if pullback else event.prev_close)
        return close < support * (1 - float(self.config["support_tolerance_pct"]))

    def _score_signal(
        self,
        signal_subtype: str,
        event: LimitUpEvent,
        pullback: PullbackValid | None,
        support: SupportConfirmed | None,
        reattack: ReAttackTrigger | None,
        risk_flags: list[str],
    ) -> float:
        score = 45.0
        if event.rule.confirmed:
            score += 10
        if pullback:
            score += 15
            score += max(0.0, 10.0 - pullback.pullback_pct * 50)
        if support:
            score += 10
        if reattack:
            score += 18
        if signal_subtype == "failed_pullback":
            score -= 35
        score -= len(risk_flags) * 6
        return round(max(0.0, min(100.0, score)), 1)

    def _build_payload(
        self,
        *,
        stock_code: str,
        stock_name: str,
        market: str,
        security_type: str,
        df,
        event: LimitUpEvent,
        pullback: PullbackValid | None,
        support: SupportConfirmed | None,
        reattack: ReAttackTrigger | None,
        signal_subtype: str,
        risk_flags: list[str],
        bar_interval: str,
        adjust: str,
    ) -> dict[str, Any]:
        last = df.iloc[-1]
        signal_name = {
            "pullback_setup": "pullback_setup",
            "breakout_confirmed": "breakout_confirmed",
            "failed_pullback": "failed_pullback",
        }[signal_subtype]
        score = self._score_signal(signal_subtype, event, pullback, support, reattack, risk_flags)
        risk_score = min(100.0, max(0.0, 100.0 - score + len(risk_flags) * 5))
        indicators = {
            "limit_rule": asdict(event.rule),
            "limit_up_event": asdict(event),
            "pullback_valid": asdict(pullback) if pullback else None,
            "support_confirmed": asdict(support) if support else None,
            "reattack_trigger": asdict(reattack) if reattack else None,
            "volume_ratio_5": round(self._safe_float(last.get("volume_ratio_5")), 4),
            "pct_chg": round(self._safe_float(last.get("pct_chg")), 4),
        }
        reason = (
            "limit-up pullback failed support"
            if signal_subtype == "failed_pullback"
            else "limit-up pullback re-attack confirmed"
            if signal_subtype == "breakout_confirmed"
            else "limit-up pullback setup with support holding"
        )
        return {
            "schema_version": SIGNAL_SCHEMA_VERSION,
            "strategy_code": self.get_code(),
            "code": stock_code,
            "symbol": stock_code,
            "name": stock_name,
            "stock_name": stock_name,
            "market": market,
            "security_type": security_type or "stock",
            "bar_interval": bar_interval,
            "interval": bar_interval,
            "adjust": adjust,
            "signal_date": str(last.get("date")),
            "trade_date": str(last.get("date")),
            "date": str(last.get("date")),
            "signal": signal_name,
            "signal_type": "RISK" if signal_subtype == "failed_pullback" else "WATCH",
            "signal_subtype": signal_subtype,
            "reason_tag": signal_name,
            "signal_strength": 1 if signal_subtype == "failed_pullback" else 4 if signal_subtype == "breakout_confirmed" else 3,
            "score": score,
            "total_score": score,
            "risk_score": round(risk_score, 1),
            "risk_level": "high" if risk_score >= 70 else "medium" if risk_score >= 45 else "low",
            "risk_flags": risk_flags,
            "pick_price": round(self._safe_float(last.get("close")), 4),
            "last_price": round(self._safe_float(last.get("close")), 4),
            "price_ref": round(self._safe_float(last.get("close")), 4),
            "limit_up_date": event.trade_date,
            "limit_up_price": event.close,
            "support_price": indicators["support_confirmed"]["support_price"] if indicators["support_confirmed"] else None,
            "volume": self._safe_int(last.get("volume")),
            "turnover": round(self._safe_float(last.get("turnover")), 4),
            "indicators": indicators,
            "phase": {
                "LimitUpEvent": bool(event),
                "PullbackValid": bool(pullback),
                "SupportConfirmed": bool(support),
                "ReAttackTrigger": bool(reattack),
                "signal_subtype": signal_subtype,
            },
            "risk": {"risk_score": round(risk_score, 1), "risk_level": "high" if risk_score >= 70 else "medium" if risk_score >= 45 else "low", "risk_flags": risk_flags},
            "data": {
                "source": str(last.get("source") or "local"),
                "provider": str(last.get("source") or "local"),
                "data_quality": "primary",
                "fallback_used": False,
                "bar_count": int(len(df)),
                "latest_bar_time": str(last.get("date")),
            },
            "reason": reason,
            "note": reason,
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
        from backend.services.stock_data_service import get_stock_data_service

        return get_stock_data_service().get_stock_list()

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
        bar_interval = str(bar_interval or self.config["bar_interval"])
        adjust = str(adjust or self.config["adjust"])
        rule = infer_limit_up_rule(stock_code, stock_name, market, security_type)
        risk_flags = list(rule.risk_flags)
        try:
            df = self._calculate_indicators(self._get_hist(stock_code, target_date, bar_interval, adjust))
            if df is None or df.empty:
                return False, "no local history", {}
            if len(df) < int(self.config["min_bars"]):
                return False, "insufficient history", {}
            if float(self.config["price_limit"]) > 0 and self._safe_float(df.iloc[-1].get("close")) > float(self.config["price_limit"]):
                return False, "price above limit", {}
            if not rule.confirmed:
                risk_flags.append("limit_rule_unconfirmed")
            event = self._find_latest_limit_up_event(df, rule)
            if not event:
                return False, "no recent limit-up event", {}
            pullback = self._pullback_valid(df, event)
            failed = self._failed_pullback(df, event, pullback)
            support = self._support_confirmed(df, event, pullback) if pullback and not failed else None
            reattack = self._reattack_trigger(df, event, pullback) if pullback and not failed else None
            if failed:
                subtype = "failed_pullback"
                risk_flags.append("support_broken")
            elif reattack:
                subtype = "breakout_confirmed"
            elif pullback and support:
                subtype = "pullback_setup"
            else:
                return False, "pullback not valid", {}
            payload = self._build_payload(
                stock_code=stock_code,
                stock_name=stock_name,
                market=market,
                security_type=security_type,
                df=df,
                event=event,
                pullback=pullback,
                support=support,
                reattack=reattack,
                signal_subtype=subtype,
                risk_flags=sorted(set(risk_flags)),
                bar_interval=bar_interval,
                adjust=adjust,
            )
            return True, subtype, payload
        except Exception as exc:
            return False, f"strategy error:{exc}", {}

    def scan(self, date: str | None = None) -> list[dict[str, Any]]:
        if pd is None:
            return []
        stock_list = self._get_stock_list()
        if stock_list is None or getattr(stock_list, "empty", True):
            return []
        code_col = self._find_column(stock_list, ["code", "symbol", "stock_code"]) or self._find_column(stock_list, ["代码", "证券代码"])
        name_col = self._find_column(stock_list, ["name", "stock_name"]) or self._find_column(stock_list, ["名称", "证券简称"])
        market_col = self._find_column(stock_list, ["market", "exchange"])
        type_col = self._find_column(stock_list, ["security_type", "type"])
        columns = list(getattr(stock_list, "columns", []))
        if not code_col and columns:
            code_col = columns[0]
        if not name_col and len(columns) > 1:
            name_col = columns[1]
        if not code_col:
            return []
        limit = int(self.config["scan_limit"])
        if limit > 0 and len(stock_list) > limit:
            stock_list = stock_list.head(limit)
        results: list[dict[str, Any]] = []
        for _, row in stock_list.iterrows():
            code = str(row.get(code_col) or "").strip()
            if not code:
                continue
            name = str(row.get(name_col) or code).strip() if name_col else code
            market = str(row.get(market_col) or "").strip() if market_col else ""
            security_type = str(row.get(type_col) or "stock").strip().lower() if type_col else "stock"
            matched, _, payload = self._analyze_stock(
                code,
                name,
                market=market,
                target_date=date,
                security_type=security_type,
                bar_interval=str(self.config["bar_interval"]),
                adjust=str(self.config["adjust"]),
            )
            if matched:
                results.append(payload)
        results.sort(key=lambda item: (-self._safe_float(item.get("total_score")), self._safe_float(item.get("risk_score")), str(item.get("code"))))
        return results[: int(self.config["select_count"])]
