"""Market data provider contracts and normalized DTOs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class StockInfo:
    symbol: str
    name: str
    exchange: str = ""
    market: str = "A"
    security_type: str = "stock"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DailyBar:
    symbol: str
    trade_date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: int | None
    amount: Decimal | None
    turnover_rate: Decimal | None = None
    source: str = "unknown"
    interval: str = "1d"
    trade_time: datetime | str | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["trade_date"] = self.trade_date.isoformat()
        if isinstance(self.trade_time, datetime):
            data["trade_time"] = self.trade_time.isoformat(timespec="seconds")
        for key in ("open", "high", "low", "close", "amount", "turnover_rate"):
            value = data[key]
            data[key] = str(value) if value is not None else None
        return data


@dataclass(frozen=True)
class QuoteSnapshot:
    symbol: str
    trade_time: datetime | str
    last_price: Decimal | None
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    prev_close: Decimal | None = None
    volume: int | None = None
    amount: Decimal | None = None
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None
    source: str = "unknown"

    def to_dict(self) -> dict:
        data = asdict(self)
        if isinstance(self.trade_time, datetime):
            data["trade_time"] = self.trade_time.isoformat(timespec="seconds")
        for key in ("last_price", "open", "high", "low", "prev_close", "amount", "bid_price", "ask_price"):
            value = data[key]
            data[key] = str(value) if value is not None else None
        return data


@dataclass(frozen=True)
class HealthCheckResult:
    provider: str
    ok: bool
    message: str = "ok"

    def to_dict(self) -> dict:
        return asdict(self)


class MarketDataProvider(Protocol):
    name: str

    def get_stock_list(self) -> list[StockInfo]:
        raise NotImplementedError

    def get_daily_bars(self, symbol: str, start_date: str, end_date: str, adjust: str = "qfq", interval: str = "1d") -> list[DailyBar]:
        raise NotImplementedError

    def get_quote_snapshots(self, symbols: list[str]) -> list[QuoteSnapshot]:
        raise NotImplementedError

    def get_trading_dates(self, start_date: str, end_date: str) -> list[str]:
        raise NotImplementedError

    def health_check(self) -> HealthCheckResult:
        raise NotImplementedError
