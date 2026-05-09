"""2560 strategy implementation.

The strategy is expressed as an explainable signal model:

- MA25 describes the medium-term price trend.
- MAVOL5/MAVOL60 describes short-term volume activity against a 60-bar base.
- MA60 is an added platform filter for trend quality and risk, not the original
  folk-strategy definition.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any

from backend.strategies import BaseStrategy, register_strategy

try:
    import akshare as ak
except ModuleNotFoundError:  # pragma: no cover - local test fallback
    ak = None
try:
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover - local test fallback
    np = None
try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - local test fallback
    pd = None


SIGNAL_SCHEMA_VERSION = "strategy-signal/2560/v1"


@register_strategy
class Strategy2560(BaseStrategy):
    """25/60 volume-and-trend strategy."""

    essential_cols = ["date", "open", "close", "high", "low", "volume"]

    def __init__(self):
        super().__init__()
        self.config = self._load_config()

    def get_code(self) -> str:
        return "2560"

    def get_name(self) -> str:
        return "2560战法"

    def get_description(self) -> str:
        return "基于MA25趋势、MAVOL5/MAVOL60量能阶段、MA60趋势过滤的可解释选股策略"

    def get_category(self) -> str:
        return "趋势量能策略"

    def get_parameters(self) -> dict[str, Any]:
        return {
            "vol_ratio": {
                "name": "量能基准倍数",
                "type": "float",
                "default": 1.0,
                "min": 0.5,
                "max": 3.0,
                "description": "MAVOL5相对MAVOL60的最低倍数",
            },
            "price_limit": {
                "name": "价格上限",
                "type": "float",
                "default": 30.0,
                "min": 1.0,
                "max": 1000.0,
                "description": "选股价格上限，0表示不限制",
            },
            "near_ma_threshold": {
                "name": "贴近MA25阈值",
                "type": "float",
                "default": 0.05,
                "min": 0.01,
                "max": 0.15,
                "description": "收盘价偏离MA25的最大比例",
            },
            "breakout_vol_ratio": {
                "name": "突破放量倍数",
                "type": "float",
                "default": 1.3,
                "min": 1.0,
                "max": 5.0,
                "description": "突破时当日成交量相对MAVOL60的最低倍数",
            },
            "bar_interval": {
                "name": "K线周期",
                "type": "string",
                "default": "1d",
                "description": "默认日K；可转债等策略可使用15m/30m独立模板",
            },
            "adjust": {
                "name": "复权口径",
                "type": "string",
                "default": "qfq",
                "description": "日K默认前复权，分钟线默认none",
            },
        }

    def _load_config(self) -> dict[str, Any]:
        default_config = {
            "strategy": {
                "vol_ratio": 1.0,
                "price_limit": 30.0,
                "exclude_st": True,
                "exclude_kechuang": False,
                "select_count": 5,
                "scan_limit": 500,
                "ma_period": 25,
                "ma_long_period": 60,
                "vol_short_period": 5,
                "vol_long_period": 60,
                "near_ma_threshold": 0.05,
                "breakout_vol_ratio": 1.3,
                "strong_breakout_vol_ratio": 1.5,
                "extreme_vol_ratio": 3.0,
                "min_data_days": 65,
                "min_score": 55,
                "bar_interval": "1d",
                "adjust": "qfq",
                "include_risk_signals": False,
                "risk_score_enabled": True,
            },
            "output": {"file_path": "data/daily_selection.json"},
        }
        config_path = "config.json"
        if not os.path.exists(config_path):
            return default_config
        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                loaded_config = json.load(handle)
        except Exception as exc:
            print(f"加载2560配置失败，使用默认配置: {exc}")
            return default_config

        for section, defaults in default_config.items():
            loaded_config.setdefault(section, defaults)
            if isinstance(defaults, dict) and isinstance(loaded_config.get(section), dict):
                for key, value in defaults.items():
                    loaded_config[section].setdefault(key, value)
        return loaded_config

    def _strategy_config(self) -> dict[str, Any]:
        return self.config.setdefault("strategy", {})

    def _float_config(self, key: str, default: float) -> float:
        try:
            return float(self._strategy_config().get(key, default))
        except (TypeError, ValueError):
            return default

    def _int_config(self, key: str, default: int) -> int:
        try:
            return int(self._strategy_config().get(key, default))
        except (TypeError, ValueError):
            return default

    def _normalize_hist_cols(self, df):
        if df is None or getattr(df, "empty", True):
            return df
        if pd is None:
            return df

        aliases = {
            "date": ["date", "trade_date", "datetime", "日期", "交易日期"],
            "open": ["open", "开盘", "开盘价"],
            "close": ["close", "收盘", "收盘价", "最新价"],
            "high": ["high", "最高", "最高价"],
            "low": ["low", "最低", "最低价"],
            "volume": ["volume", "vol", "成交量", "成交量(手)"],
            "amount": ["amount", "成交额", "成交额(元)"],
            "turnover": ["turnover", "turnover_rate", "换手率"],
            "source": ["source", "数据源"],
            "adjust": ["adjust", "复权"],
            "interval": ["interval", "bar_interval", "周期"],
        }
        rename_map: dict[str, str] = {}
        lower_to_col = {str(col).strip().lower(): col for col in df.columns}
        for target, candidates in aliases.items():
            for candidate in candidates:
                original = lower_to_col.get(str(candidate).strip().lower())
                if original is not None:
                    rename_map[original] = target
                    break
        normalized = df.rename(columns=rename_map).copy()

        for col in self.essential_cols:
            if col not in normalized.columns:
                normalized[col] = None
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
        normalized = normalized.dropna(subset=["date"]).sort_values("date")
        normalized["date"] = normalized["date"].dt.strftime("%Y-%m-%d")

        for col in ["open", "close", "high", "low", "volume", "amount", "turnover"]:
            if col in normalized.columns:
                normalized[col] = pd.to_numeric(normalized[col], errors="coerce")
        normalized = normalized.dropna(subset=["open", "close", "high", "low", "volume"])
        normalized = normalized.drop_duplicates(subset=["date"], keep="last")
        if "amount" not in normalized.columns or normalized["amount"].isna().all():
            normalized["amount"] = normalized["close"] * normalized["volume"]
        if "turnover" not in normalized.columns:
            normalized["turnover"] = 0.0
        return normalized.reset_index(drop=True)

    def _calculate_indicators(self, df):
        if pd is None or df is None or df.empty:
            return df

        config = self._strategy_config()
        ma_period = int(config.get("ma_period", 25))
        ma_long = int(config.get("ma_long_period", 60))
        vol_short = int(config.get("vol_short_period", 5))
        vol_long = int(config.get("vol_long_period", 60))

        df = self._normalize_hist_cols(df)
        if df is None or df.empty:
            return df

        safe_mavol60 = df["volume"].rolling(window=vol_long, min_periods=vol_long).mean()
        safe_mavol60 = safe_mavol60.replace(0, np.nan if np is not None else None)

        df["ma25"] = df["close"].rolling(window=ma_period, min_periods=ma_period).mean()
        df["ma60"] = df["close"].rolling(window=ma_long, min_periods=ma_long).mean()
        df["mavol5"] = df["volume"].rolling(window=vol_short, min_periods=vol_short).mean()
        df["mavol60"] = safe_mavol60
        df["ma5_vol"] = df["mavol5"]
        df["ma60_vol"] = df["mavol60"]
        df["vr5_60"] = df["mavol5"] / df["mavol60"]
        df["vr1_60"] = df["volume"] / df["mavol60"]
        df["vol_ratio"] = df["vr5_60"]
        df["dist25"] = (df["close"] - df["ma25"]) / df["ma25"]
        df["dist60"] = (df["close"] - df["ma60"]) / df["ma60"]
        df["price_to_ma25"] = df["dist25"]
        df["ma25_slope_5"] = (df["ma25"] / df["ma25"].shift(5)) - 1
        df["ma60_slope_10"] = (df["ma60"] / df["ma60"].shift(10)) - 1
        df["high20"] = df["high"].shift(1).rolling(window=20, min_periods=20).max()
        df["amount_ma20"] = df["amount"].rolling(window=20, min_periods=1).mean()
        df["volume_cross_up"] = (df["mavol5"] >= df["mavol60"]) & (df["mavol5"].shift(1) < df["mavol60"].shift(1))
        df["max_vr5_60_20"] = df["vr5_60"].rolling(window=20, min_periods=1).max()
        df["close_center_10"] = df["close"].rolling(window=10, min_periods=1).mean()
        df["close_center_20"] = df["close"].rolling(window=20, min_periods=1).mean()
        df["up_volume"] = df["volume"].where(df["close"] >= df["close"].shift(1), 0)
        df["down_volume"] = df["volume"].where(df["close"] < df["close"].shift(1), 0)
        df["up_down_volume_10"] = (
            df["up_volume"].rolling(window=10, min_periods=1).sum()
            / df["down_volume"].rolling(window=10, min_periods=1).sum().replace(0, np.nan if np is not None else None)
        )
        df["volatility_20"] = df["close"].pct_change().rolling(window=20, min_periods=5).std()
        return df

    def _bool_at(self, df, column: str, tail_count: int = 1) -> bool:
        if column not in df.columns or df.empty:
            return False
        return bool(df[column].tail(tail_count).fillna(False).any())

    def _is_valid_number(self, value: Any) -> bool:
        if pd is not None:
            return bool(pd.notna(value))
        return value not in (None, "")

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            if pd is not None and pd.isna(value):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            if value is None:
                return default
            if pd is not None and pd.isna(value):
                return default
            return int(float(value))
        except (TypeError, ValueError):
            return default

    def _near_ma25(self, last, threshold: float) -> bool:
        ma25 = self._safe_float(last.get("ma25"))
        if ma25 <= 0:
            return False
        close = self._safe_float(last.get("close"))
        low = self._safe_float(last.get("low"))
        dist25 = abs(self._safe_float(last.get("dist25")))
        return low <= ma25 * (1 + threshold) and close >= ma25 * 0.985 and dist25 <= threshold

    def _failed_breakout(self, df) -> bool:
        if len(df) < 7:
            return False
        prior = df.iloc[-6:-1]
        current_close = self._safe_float(df.iloc[-1].get("close"))
        breakout_rows = prior[
            (prior["close"] > prior["high20"] * 1.01)
            & (prior["vr1_60"] >= self._float_config("breakout_vol_ratio", 1.3))
        ]
        if breakout_rows.empty:
            return False
        breakout_price = self._safe_float(breakout_rows.iloc[-1].get("high20"))
        return breakout_price > 0 and current_close < breakout_price * 0.99

    def _classify_signal(self, df) -> dict[str, Any]:
        config = self._strategy_config()
        last = df.iloc[-1]
        near_threshold = self._float_config("near_ma_threshold", 0.05)
        breakout_ratio = self._float_config("breakout_vol_ratio", 1.3)
        strong_breakout_ratio = self._float_config("strong_breakout_vol_ratio", 1.5)
        extreme_ratio = self._float_config("extreme_vol_ratio", 3.0)
        min_score = self._float_config("min_score", 55)

        close = self._safe_float(last.get("close"))
        high = self._safe_float(last.get("high"))
        ma25 = self._safe_float(last.get("ma25"))
        ma60 = self._safe_float(last.get("ma60"))
        mavol5 = self._safe_float(last.get("mavol5"))
        mavol60 = self._safe_float(last.get("mavol60"))
        vr5_60 = self._safe_float(last.get("vr5_60"))
        vr1_60 = self._safe_float(last.get("vr1_60"))
        dist25 = self._safe_float(last.get("dist25"))
        high20 = self._safe_float(last.get("high20"))
        ma25_slope_5 = self._safe_float(last.get("ma25_slope_5"))
        ma60_slope_10 = self._safe_float(last.get("ma60_slope_10"))

        trend_core = ma25 > 0 and ma25_slope_5 > 0 and close >= ma25 * 0.985
        trend_strong = trend_core and ma60 > 0 and close > ma60 and ma25 >= ma60
        volume_base_ok = mavol60 > 0 and mavol5 >= mavol60 * self._float_config("vol_ratio", 1.0)
        near_ma25 = self._near_ma25(last, near_threshold)
        failed_breakout = self._failed_breakout(df)
        volume_impulse = self._bool_at(df, "volume_cross_up", 3) and close >= ma25 * 0.985 and trend_core
        volume_build = (
            self._safe_float(last.get("max_vr5_60_20")) >= 1.05
            and 0.85 <= vr5_60 <= 1.25
            and close >= ma25 * 0.985
            and ma25_slope_5 > 0
        )
        lock_shrink = (
            trend_core
            and near_ma25
            and int((df["vr5_60"].tail(10) >= 1.0).sum()) >= 5
            and self._safe_float(last.get("volume")) <= self._safe_float(df["volume"].tail(5).min()) * 1.05
            and close >= ma25
        )
        pullback_shrink = trend_core and near_ma25 and self._safe_float(last.get("volume")) <= mavol5 and vr1_60 <= 1.0
        breakout_volume = trend_core and high20 > 0 and close > high20 * 1.01 and vr1_60 >= breakout_ratio and close >= high * 0.97

        if failed_breakout:
            volume_phase = "failed_breakout"
        elif vr1_60 >= extreme_ratio:
            volume_phase = "extreme_risk"
        elif lock_shrink or pullback_shrink:
            volume_phase = "lock_shrink"
        elif breakout_volume:
            volume_phase = "breakout_expand"
        elif volume_impulse:
            volume_phase = "impulse"
        elif volume_build:
            volume_phase = "build"
        elif volume_base_ok:
            volume_phase = "active"
        else:
            volume_phase = "insufficient"

        if failed_breakout:
            signal_subtype = "failed_breakout"
            signal = "失败突破"
            signal_type = "RISK"
            signal_strength = 0
        elif lock_shrink or pullback_shrink:
            signal_subtype = "volume_lock_shrink"
            signal = "缩量回踩"
            signal_type = "WATCH"
            signal_strength = 4
        elif breakout_volume:
            signal_subtype = "breakout_volume"
            signal = "放量突破"
            signal_type = "WATCH"
            signal_strength = 3 if vr1_60 < strong_breakout_ratio else 4
        elif volume_build and volume_base_ok:
            signal_subtype = "volume_build"
            signal = "做量蓄势"
            signal_type = "WATCH"
            signal_strength = 3
        elif volume_impulse:
            signal_subtype = "volume_impulse"
            signal = "冲量启动"
            signal_type = "WATCH"
            signal_strength = 2
        elif trend_core and volume_base_ok and close >= ma25:
            signal_subtype = "mild_breakout"
            signal = "温和突破"
            signal_type = "WATCH"
            signal_strength = 1
        else:
            signal_subtype = ""
            signal = ""
            signal_type = "NONE"
            signal_strength = 0

        risk_flags = []
        if failed_breakout:
            risk_flags.append("failed_breakout")
        if vr1_60 >= extreme_ratio:
            risk_flags.append("extreme_volume")
        if dist25 >= 0.12:
            risk_flags.append("overextended_ma25")
        if ma60 > 0 and close < ma60:
            risk_flags.append("below_ma60")
        if self._safe_float(last.get("amount_ma20")) < 20_000_000:
            risk_flags.append("low_liquidity")

        total_score = self._score_signal(last, signal_subtype, trend_core, trend_strong, volume_phase, risk_flags)
        risk_score = self._calculate_risk_score(df, risk_flags)
        risk_level = "high" if risk_score >= 70 else "medium" if risk_score >= 45 else "low"
        matched = bool(signal_subtype and signal_type != "RISK" and total_score >= min_score)
        if signal_type == "RISK" and bool(config.get("include_risk_signals", False)):
            matched = True

        return {
            "matched": matched,
            "signal": signal,
            "signal_type": signal_type,
            "signal_subtype": signal_subtype,
            "signal_strength": signal_strength,
            "volume_phase": volume_phase,
            "trend_core": trend_core,
            "trend_strong": trend_strong,
            "volume_base_ok": volume_base_ok,
            "near_ma25": near_ma25,
            "failed_breakout": failed_breakout,
            "breakout_confirmed": breakout_volume,
            "risk_flags": risk_flags,
            "risk_score": round(risk_score, 1),
            "risk_level": risk_level,
            "total_score": round(total_score, 1),
        }

    def _score_signal(self, last, signal_subtype: str, trend_core: bool, trend_strong: bool, volume_phase: str, risk_flags: list[str]) -> float:
        score = 0.0

        if trend_core:
            score += 14
        if trend_strong:
            score += 10
        score += min(max(self._safe_float(last.get("ma25_slope_5")) * 600, 0), 6)

        vr5_60 = self._safe_float(last.get("vr5_60"))
        vr1_60 = self._safe_float(last.get("vr1_60"))
        if vr5_60 >= 1.0:
            score += min(16, 8 + (vr5_60 - 1.0) * 12)
        if vr1_60 >= 1.0:
            score += min(9, (vr1_60 - 1.0) * 8 + 4)

        phase_score = {
            "lock_shrink": 20,
            "breakout_expand": 17,
            "build": 15,
            "impulse": 11,
            "active": 7,
            "extreme_risk": 3,
            "failed_breakout": 0,
        }
        score += phase_score.get(volume_phase, 0)

        subtype_score = {
            "volume_lock_shrink": 10,
            "breakout_volume": 8,
            "volume_build": 7,
            "volume_impulse": 5,
            "mild_breakout": 3,
        }
        score += subtype_score.get(signal_subtype, 0)

        amount_ma20 = self._safe_float(last.get("amount_ma20"))
        if amount_ma20 >= 100_000_000:
            score += 10
        elif amount_ma20 >= 20_000_000:
            score += 6
        else:
            score += 2

        score += 5
        if "extreme_volume" in risk_flags:
            score -= 10
        if "overextended_ma25" in risk_flags:
            score -= 10
        if "failed_breakout" in risk_flags:
            score -= 25
        if "below_ma60" in risk_flags:
            score -= 5
        if "low_liquidity" in risk_flags:
            score -= 6
        return max(0.0, min(100.0, score))

    def _calculate_risk_score(self, df, risk_flags: list[str] | None = None) -> float:
        if df is None or len(df) < 30:
            return 50.0
        risk_flags = risk_flags or []
        last = df.iloc[-1]
        volatility = self._safe_float(last.get("volatility_20"))
        dist25 = abs(self._safe_float(last.get("dist25")))
        dist60 = abs(self._safe_float(last.get("dist60")))
        score = 20.0 + min(volatility * 500, 25) + min(dist25 * 120, 20) + min(dist60 * 60, 15)
        if "extreme_volume" in risk_flags:
            score += 15
        if "failed_breakout" in risk_flags:
            score += 25
        if "low_liquidity" in risk_flags:
            score += 10
        if "below_ma60" in risk_flags:
            score += 8
        return max(0.0, min(100.0, score))

    def _build_reason(self, signal: dict[str, Any], last) -> str:
        if signal["signal_subtype"] == "volume_lock_shrink":
            return "MA25上行，MAVOL5高于MAVOL60，近端缩量回踩MA25且未有效跌破。"
        if signal["signal_subtype"] == "breakout_volume":
            return "MA25上行，收盘突破20日平台高点，并出现相对MAVOL60的放量确认。"
        if signal["signal_subtype"] == "volume_build":
            return "前期短期均量站上60日均量，当前量能回到合理区间，价格仍守住MA25。"
        if signal["signal_subtype"] == "volume_impulse":
            return "MAVOL5近期上穿MAVOL60，价格保持在MA25附近或上方，属于冲量启动。"
        if signal["signal_subtype"] == "failed_breakout":
            return "近期放量突破后快速跌回突破位下方，属于失败突破风险。"
        return "MA25趋势和量能条件达到最低观察要求。"

    def _signal_payload(
        self,
        *,
        stock_code: str,
        stock_name: str,
        security_type: str,
        bar_interval: str,
        adjust: str,
        df,
        signal: dict[str, Any],
    ) -> dict[str, Any]:
        last = df.iloc[-1]
        price_change_5d = 0.0
        price_change_20d = 0.0
        if len(df) >= 6:
            base = self._safe_float(df.iloc[-6].get("close"))
            price_change_5d = ((self._safe_float(last.get("close")) - base) / base * 100) if base else 0.0
        if len(df) >= 21:
            base = self._safe_float(df.iloc[-21].get("close"))
            price_change_20d = ((self._safe_float(last.get("close")) - base) / base * 100) if base else 0.0

        indicators = {
            "ma25": round(self._safe_float(last.get("ma25")), 4),
            "ma60": round(self._safe_float(last.get("ma60")), 4),
            "ma25_slope_5": round(self._safe_float(last.get("ma25_slope_5")), 6),
            "ma60_slope_10": round(self._safe_float(last.get("ma60_slope_10")), 6),
            "mavol5": round(self._safe_float(last.get("mavol5")), 2),
            "mavol60": round(self._safe_float(last.get("mavol60")), 2),
            "ma5_vol": round(self._safe_float(last.get("ma5_vol")), 2),
            "ma60_vol": round(self._safe_float(last.get("ma60_vol")), 2),
            "vol_ratio": round(self._safe_float(last.get("vol_ratio")), 4),
            "vr5_60": round(self._safe_float(last.get("vr5_60")), 4),
            "vr1_60": round(self._safe_float(last.get("vr1_60")), 4),
            "dist25": round(self._safe_float(last.get("dist25")), 6),
            "dist60": round(self._safe_float(last.get("dist60")), 6),
            "price_to_ma25": round(self._safe_float(last.get("dist25")) * 100, 2),
            "high20": round(self._safe_float(last.get("high20")), 4),
            "amount": round(self._safe_float(last.get("amount")), 2),
            "amount_ma20": round(self._safe_float(last.get("amount_ma20")), 2),
            "turnover_rate": round(self._safe_float(last.get("turnover")), 4),
        }
        phase = {
            "volume_phase": signal["volume_phase"],
            "trend_core": signal["trend_core"],
            "trend_strong": signal["trend_strong"],
            "volume_base_ok": signal["volume_base_ok"],
            "near_ma25": signal["near_ma25"],
            "failed_breakout": signal["failed_breakout"],
            "breakout_confirmed": signal["breakout_confirmed"],
        }
        risk = {
            "risk_score": signal["risk_score"],
            "risk_level": signal["risk_level"],
            "risk_flags": signal["risk_flags"],
        }
        data_meta = {
            "source": str(last.get("source") or "local"),
            "provider": str(last.get("source") or "local"),
            "data_quality": "primary",
            "fallback_used": False,
            "bar_count": int(len(df)),
            "latest_bar_time": str(last.get("date")),
        }
        reason = self._build_reason(signal, last)
        payload = {
            "schema_version": SIGNAL_SCHEMA_VERSION,
            "strategy_code": self.get_code(),
            "symbol": stock_code,
            "code": stock_code,
            "name": stock_name,
            "stock_name": stock_name,
            "security_type": security_type or "stock",
            "bar_interval": bar_interval,
            "interval": bar_interval,
            "adjust": adjust,
            "signal_date": str(last.get("date")),
            "trade_date": str(last.get("date")),
            "date": str(last.get("date")),
            "signal_type": signal["signal_type"],
            "signal_subtype": signal["signal_subtype"],
            "signal": signal["signal"],
            "reason_tag": signal["signal"],
            "signal_strength": signal["signal_strength"],
            "score": signal["total_score"],
            "total_score": signal["total_score"],
            "price_ref": round(self._safe_float(last.get("close")), 4),
            "pick_price": round(self._safe_float(last.get("close")), 4),
            "last_price": round(self._safe_float(last.get("close")), 4),
            "ma25": indicators["ma25"],
            "ma60": indicators["ma60"],
            "ma5_vol": indicators["ma5_vol"],
            "ma60_vol": indicators["ma60_vol"],
            "vol_ratio": indicators["vol_ratio"],
            "vr5_60": indicators["vr5_60"],
            "vr1_60": indicators["vr1_60"],
            "ma25_slope_5": indicators["ma25_slope_5"],
            "ma60_slope_10": indicators["ma60_slope_10"],
            "price_to_ma25": indicators["price_to_ma25"],
            "risk_score": signal["risk_score"],
            "risk_level": signal["risk_level"],
            "risk_flags": signal["risk_flags"],
            "volume_phase": signal["volume_phase"],
            "price_change_5d": round(price_change_5d, 2),
            "price_change_20d": round(price_change_20d, 2),
            "volume": self._safe_int(last.get("volume")),
            "turnover": indicators["turnover_rate"],
            "indicators": indicators,
            "phase": phase,
            "risk": risk,
            "data": data_meta,
            "reason": reason,
            "note": reason,
        }
        return payload

    def _get_hist(self, stock_code: str, target_date: str | None, bar_interval: str, adjust: str):
        from backend.services.stock_data_service import get_stock_data_service

        end_date = datetime.strptime(target_date, "%Y-%m-%d") if target_date else datetime.now()
        start_date = end_date - timedelta(days=240)
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
                symbol=stock_code,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                adjust=adjust,
            )

    def _analyze_stock(
        self,
        stock_code: str,
        stock_name: str,
        market: str,
        target_date: str | None = None,
        security_type: str = "stock",
        bar_interval: str | None = None,
        adjust: str | None = None,
    ) -> tuple[bool, str, dict[str, Any]]:
        if pd is None:
            return False, "pandas不可用", {}

        config = self._strategy_config()
        bar_interval = str(bar_interval or config.get("bar_interval") or "1d")
        adjust = str(adjust or config.get("adjust") or ("qfq" if bar_interval == "1d" else "none")).lower()
        if bar_interval != "1d":
            adjust = "none"

        try:
            df = self._get_hist(stock_code, target_date, bar_interval, adjust)
            if df is None or getattr(df, "empty", True):
                return False, "no historical market data", {}
            df = self._calculate_indicators(df)
            if df is None or df.empty:
                return False, "无有效K线数据", {}

            min_days = self._int_config("min_data_days", 65)
            if len(df) < min_days:
                return False, "历史K线样本不足", {}

            last = df.iloc[-1]
            required = ["ma25", "ma60", "mavol5", "mavol60", "vr5_60", "vr1_60"]
            if any(not self._is_valid_number(last.get(col)) for col in required):
                return False, "指标计算样本不足", {}

            price_limit = self._float_config("price_limit", 30.0)
            if price_limit > 0 and self._safe_float(last.get("close")) > price_limit:
                return False, "价格超过上限", {}

            signal = self._classify_signal(df)
            if not signal["matched"]:
                return False, signal["signal"] or "未达到2560信号阈值", {}

            result = self._signal_payload(
                stock_code=stock_code,
                stock_name=stock_name,
                security_type=security_type,
                bar_interval=bar_interval,
                adjust=adjust,
                df=df,
                signal=signal,
            )
            return True, result["signal"], result
        except Exception as exc:
            return False, f"策略分析异常:{exc}", {}

    def scan(self, date: str | None = None) -> list[dict[str, Any]]:
        if pd is None:
            return []
        print(f"启动2560战法扫描: {datetime.now().isoformat(timespec='seconds')}")
        config = self._strategy_config()
        stock_list = self._get_stock_list()
        if stock_list is None or getattr(stock_list, "empty", True):
            print("未获取到证券列表")
            return []

        code_col = self._find_column(stock_list, ["代码", "证券代码", "symbol", "code", "浠ｇ爜"])
        name_col = self._find_column(stock_list, ["名称", "证券简称", "name", "stock_name", "鍚嶇О"])
        type_col = self._find_column(stock_list, ["security_type", "type", "证券类型", "类型"])
        if not code_col or not name_col:
            print("证券列表缺少代码或名称字段")
            return []

        scan_limit = self._int_config("scan_limit", 500)
        if scan_limit > 0 and len(stock_list) > scan_limit:
            stock_list = stock_list.head(scan_limit)

        selected: list[dict[str, Any]] = []
        for _, row in stock_list.iterrows():
            code = str(row.get(code_col) or "").strip()
            name = str(row.get(name_col) or code).strip()
            security_type = str(row.get(type_col) or "stock").strip().lower() if type_col else "stock"
            if not code or self._should_exclude(code, name, security_type):
                continue
            matched, reason, result = self._analyze_stock(
                code,
                name,
                "sh" if code.startswith("6") else "sz",
                date,
                security_type=security_type,
                bar_interval=str(config.get("bar_interval") or "1d"),
                adjust=str(config.get("adjust") or "qfq"),
            )
            if matched:
                selected.append(result)
            elif len(selected) < 3:
                print(f"跳过 {code} {name}: {reason}")

        selected = self._sort_and_filter(selected)
        self._save_results(selected, date)
        print(f"2560扫描完成: 命中 {len(selected)} 条")
        return selected

    def _find_column(self, df, candidates: list[str]) -> str | None:
        lower_to_col = {str(col).strip().lower(): col for col in df.columns}
        for candidate in candidates:
            col = lower_to_col.get(str(candidate).strip().lower())
            if col is not None:
                return col
        return None

    def _get_stock_list(self):
        from backend.services.stock_data_service import get_stock_data_service

        return get_stock_data_service().get_stock_list()

    def _should_exclude(self, code: str, name: str, security_type: str = "stock") -> bool:
        config = self._strategy_config()
        upper_name = str(name or "").upper()
        if config.get("exclude_st", True) and ("ST" in upper_name or "退" in upper_name):
            return True
        if config.get("exclude_kechuang", False) and code.startswith("688"):
            return True
        return False

    def _sort_and_filter(self, stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        stocks.sort(
            key=lambda item: (
                -self._safe_float(item.get("total_score")),
                self._safe_float(item.get("risk_score")),
                -self._safe_float(item.get("vol_ratio")),
                str(item.get("code") or ""),
            )
        )
        return stocks[: self._int_config("select_count", 5)]

    def _save_results(self, stocks: list[dict[str, Any]], date: str | None = None):
        os.makedirs("data", exist_ok=True)
        out_json = self.config.get("output", {}).get("file_path", "data/daily_selection.json")
        with open(out_json, "w", encoding="utf-8") as handle:
            json.dump(stocks, handle, ensure_ascii=False, indent=2)
        if stocks and pd is not None:
            pd.DataFrame(stocks).to_csv(out_json.replace(".json", ".csv"), index=False, encoding="utf-8-sig")

    def backtest(self, start_date: str, end_date: str) -> dict[str, Any]:
        print(f"开始2560策略信号回测: {start_date} 至 {end_date}")
        trade_dates = self._trading_dates(start_date, end_date)
        all_signals: list[dict[str, Any]] = []
        daily_results: list[dict[str, Any]] = []
        for trade_date in trade_dates:
            signals = self.scan(trade_date)
            daily_results.append({"date": trade_date, "count": len(signals), "signals": signals})
            all_signals.extend(signals)
        signal_types: dict[str, int] = {}
        signal_subtypes: dict[str, int] = {}
        for item in all_signals:
            signal_types[item.get("signal") or ""] = signal_types.get(item.get("signal") or "", 0) + 1
            signal_subtypes[item.get("signal_subtype") or ""] = signal_subtypes.get(item.get("signal_subtype") or "", 0) + 1
        avg_risk = sum(self._safe_float(item.get("risk_score")) for item in all_signals) / len(all_signals) if all_signals else 0
        avg_score = sum(self._safe_float(item.get("total_score")) for item in all_signals) / len(all_signals) if all_signals else 0
        return {
            "start_date": start_date,
            "end_date": end_date,
            "total_trading_days": len(trade_dates),
            "total_signals": len(all_signals),
            "avg_signals_per_day": round(len(all_signals) / len(trade_dates), 2) if trade_dates else 0,
            "signal_types": signal_types,
            "signal_subtypes": signal_subtypes,
            "avg_risk_score": round(avg_risk, 2),
            "avg_total_score": round(avg_score, 2),
            "daily_results": daily_results,
        }

    def _trading_dates(self, start_date: str, end_date: str) -> list[str]:
        try:
            if ak is None:
                raise RuntimeError("akshare unavailable")
            cal = ak.tool_trade_date_hist_sina()
            dates = cal[cal["trade_date"] >= start_date]["trade_date"].tolist()
            return [item for item in dates if item <= end_date]
        except Exception:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            dates = []
            current = start
            while current <= end:
                if current.weekday() < 5:
                    dates.append(current.strftime("%Y-%m-%d"))
                current += timedelta(days=1)
            return dates
