"""Market data provider contracts and normalized DTOs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class StockInfo:
    symbol: str
    name: str
    exchange: str = ""
    market: str = "A"

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

    def to_dict(self) -> dict:
        data = asdict(self)
        data["trade_date"] = self.trade_date.isoformat()
        for key in ("open", "high", "low", "close", "amount", "turnover_rate"):
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

    def get_daily_bars(self, symbol: str, start_date: str, end_date: str, adjust: str = "qfq") -> list[DailyBar]:
        raise NotImplementedError

    def get_trading_dates(self, start_date: str, end_date: str) -> list[str]:
        raise NotImplementedError

    def health_check(self) -> HealthCheckResult:
        raise NotImplementedError
