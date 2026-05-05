"""Helpers for normalizing market data provider values."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

SZ_A_SHARE_PREFIXES = ("000", "001", "002", "003", "300", "301")
SH_A_SHARE_PREFIXES = ("600", "601", "603", "605", "688", "689")
BJ_A_SHARE_PREFIXES = (
    "430",
    "830",
    "831",
    "832",
    "833",
    "834",
    "835",
    "836",
    "837",
    "838",
    "839",
    "870",
    "871",
    "872",
    "873",
    "920",
)
A_SHARE_STOCK_PREFIXES = SZ_A_SHARE_PREFIXES + SH_A_SHARE_PREFIXES + BJ_A_SHARE_PREFIXES
CONVERTIBLE_BOND_PREFIXES = ("110", "111", "113", "118", "123", "127", "128")
ETF_PREFIXES = ("159", "510", "511", "512", "513", "515", "516", "517", "518", "560", "561", "562", "563", "588", "589")
INDEX_PREFIXES = ("399",)
BOND_PREFIXES = ("100", "101", "102", "103", "104", "105", "106", "107", "108", "109", "112", "120", "121", "122", "124", "129")
B_SHARE_PREFIXES = ("200", "900")
BAR_INTERVAL_ALIASES = {
    "1d": "1d",
    "d": "1d",
    "day": "1d",
    "daily": "1d",
    "dk": "1d",
    "15": "15m",
    "15m": "15m",
    "15min": "15m",
    "30": "30m",
    "30m": "30m",
    "30min": "30m",
    "5": "5m",
    "5m": "5m",
    "5min": "5m",
    "1h": "1h",
    "60m": "1h",
    "60min": "1h",
    "1m": "1m",
    "1min": "1m",
}


def parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unsupported date value: {value}")


def to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def infer_exchange(symbol: str) -> str:
    text = str(symbol or "").strip()
    if text.startswith(("5", "9", "100", "110", "111", "113", "118", "132")):
        return "SH"
    if text.startswith(("11", "12", "15", "16", "18", "20")):
        return "SZ"
    if text.startswith(("4", "8", "920")):
        return "BJ"
    if text.startswith(("6",)):
        return "SH"
    if text.startswith(("0", "2", "3")):
        return "SZ"
    return ""


def is_a_share_stock_symbol(symbol: str, exchange: str | None = None) -> bool:
    text = str(symbol or "").strip()
    if len(text) != 6 or not text.isdigit():
        return False
    normalized_exchange = str(exchange or "").strip().upper()
    if normalized_exchange in {"SZ", "SSE-SZ", "SHENZHEN", "深市", "深圳"}:
        return text.startswith(SZ_A_SHARE_PREFIXES)
    if normalized_exchange in {"SH", "SSE", "SHANGHAI", "沪市", "上海"}:
        return text.startswith(SH_A_SHARE_PREFIXES)
    if normalized_exchange in {"BJ", "BSE", "BEIJING", "北交所", "北京"}:
        return text.startswith(BJ_A_SHARE_PREFIXES)
    return text.startswith(A_SHARE_STOCK_PREFIXES)


def clean_security_name(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def is_risk_warning_name(name: Any) -> bool:
    text = clean_security_name(name).upper().replace(" ", "")
    return text.startswith(("*ST", "ST")) or "退" in text or "RISK" in text


def is_a_share_stock_name(name: Any) -> bool:
    text = clean_security_name(name).lower()
    return not any(
        keyword in text
        for keyword in ("转债", "可转", "指数", "b股", "ｂ股", "b share", "etf", "基金", "lof", "reit", "债", "bond", "abs")
    )


def is_a_share_stock(symbol: str, name: Any = "", exchange: str | None = None) -> bool:
    return infer_security_type(symbol, name) == "stock" and is_a_share_stock_symbol(symbol, exchange=exchange)


def infer_security_type(symbol: str, name: Any = "") -> str:
    code = str(symbol or "").strip()
    text = clean_security_name(name).lower()
    if "转债" in text or "可转" in text or code.startswith(CONVERTIBLE_BOND_PREFIXES):
        return "convertible_bond"
    if "指数" in text or code.startswith(INDEX_PREFIXES):
        return "index"
    if "b股" in text or "ｂ股" in text or "b share" in text or code.startswith(B_SHARE_PREFIXES):
        return "b_share"
    if "etf" in text or code.startswith(ETF_PREFIXES):
        return "etf"
    if "基金" in text or "lof" in text or "reit" in text:
        return "fund"
    if "债" in text or "bond" in text or "abs" in text or code.startswith(BOND_PREFIXES):
        return "bond"
    if is_a_share_stock_symbol(code):
        return "stock"
    return "other"


def infer_board_type(symbol: str, exchange: str | None = None, security_type: str | None = None) -> str:
    code = str(symbol or "").strip()
    normalized_type = str(security_type or infer_security_type(code)).strip().lower()
    normalized_exchange = str(exchange or infer_exchange(code)).strip().upper()
    if normalized_type == "convertible_bond":
        return "convertible_bond"
    if normalized_type not in {"stock", ""}:
        return normalized_type
    if normalized_exchange == "BJ" or code.startswith(BJ_A_SHARE_PREFIXES):
        return "bse"
    if code.startswith(("300", "301")):
        return "chinext"
    if code.startswith(("688", "689")):
        return "star"
    if code.startswith(A_SHARE_STOCK_PREFIXES):
        return "main"
    return normalized_type or "other"


def infer_limit_rate(
    symbol: str,
    name: Any = "",
    *,
    exchange: str | None = None,
    security_type: str | None = None,
    is_st: bool | None = None,
    trade_date: date | str | None = None,
) -> Decimal | None:
    """Infer the daily A-share price limit rate when no rule-calendar row is available.

    This is a conservative fallback. Production strategies should prefer a persisted
    limit-rule calendar because rule dates and special cases can change.
    """

    normalized_type = str(security_type or infer_security_type(symbol, name)).strip().lower()
    if normalized_type == "convertible_bond":
        return None
    if normalized_type != "stock":
        return None
    if is_st is None:
        is_st = is_risk_warning_name(name)
    if is_st:
        # Main-board risk-warning limits change in 2026. Without an exchange-specific
        # calendar, keep the long-standing conservative 5% fallback and surface a risk flag.
        return Decimal("0.05")
    board_type = infer_board_type(symbol, exchange=exchange, security_type=normalized_type)
    if board_type == "bse":
        return Decimal("0.30")
    if board_type in {"chinext", "star"}:
        return Decimal("0.20")
    if board_type == "main":
        return Decimal("0.10")
    return None


def limit_price(prev_close: Any, rate: Decimal | float | str | None, *, direction: str = "up") -> Decimal | None:
    close = to_decimal(prev_close)
    if close is None or close <= 0 or rate is None:
        return None
    normalized_rate = to_decimal(rate)
    if normalized_rate is None:
        return None
    multiplier = Decimal("1") + normalized_rate if direction == "up" else Decimal("1") - normalized_rate
    return (close * multiplier).quantize(Decimal("0.01"))


def is_limit_up_price(price: Any, prev_close: Any, rate: Decimal | float | str | None, *, tolerance: Decimal = Decimal("0.01")) -> bool:
    value = to_decimal(price)
    target = limit_price(prev_close, rate, direction="up")
    return bool(value is not None and target is not None and value >= target - tolerance)


def is_limit_down_price(price: Any, prev_close: Any, rate: Decimal | float | str | None, *, tolerance: Decimal = Decimal("0.01")) -> bool:
    value = to_decimal(price)
    target = limit_price(prev_close, rate, direction="down")
    return bool(value is not None and target is not None and value <= target + tolerance)


def normalize_bar_interval(value: Any = "1d") -> str:
    text = str(value or "1d").strip().lower()
    return BAR_INTERVAL_ALIASES.get(text, text or "1d")
