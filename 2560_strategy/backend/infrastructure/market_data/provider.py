"""Market data provider contracts and normalized DTOs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True)
class MarketDataCapabilities:
    provider: str
    daily_bars: bool = True
    quote_snapshots: bool = True
    auction_snapshots: bool = False
    auction_source_quality: str = "unknown"
    auction_level2: bool = False
    auction_order_book_depth: int | None = None
    auction_withdrawal: bool = False
    auction_seal: bool = False
    auction_fields: list[str] | None = None
    notes: list[str] | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["auction_fields"] = list(self.auction_fields or [])
        data["notes"] = list(self.notes or [])
        return data


def derived_l1_capabilities(provider: str, *, note: str = "") -> MarketDataCapabilities:
    notes = [note] if note else []
    return MarketDataCapabilities(
        provider=provider,
        auction_snapshots=True,
        auction_source_quality="derived_l1",
        auction_level2=False,
        auction_order_book_depth=1,
        auction_withdrawal=False,
        auction_seal=False,
        auction_fields=[
            "indicative_price",
            "matched_volume",
            "matched_amount",
            "prev_close",
            "bid_price",
            "ask_price",
        ],
        notes=notes,
    )


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
class AuctionSnapshot:
    symbol: str
    trade_date: date | str
    auction_time: datetime | str
    indicative_price: Decimal | None
    matched_volume: int | None = None
    matched_amount: Decimal | None = None
    prev_close: Decimal | None = None
    unmatched_buy_volume: int | None = None
    unmatched_sell_volume: int | None = None
    bid_price: Decimal | None = None
    bid_volume: int | None = None
    ask_price: Decimal | None = None
    ask_volume: int | None = None
    order_book: dict[str, Any] | list[dict[str, Any]] | None = None
    withdrawal_buy_volume: int | None = None
    withdrawal_sell_volume: int | None = None
    withdrawal_buy_amount: Decimal | None = None
    withdrawal_sell_amount: Decimal | None = None
    seal_price: Decimal | None = None
    seal_volume: int | None = None
    seal_amount: Decimal | None = None
    seal_side: str | None = None
    source_quality: str = "unknown"
    capabilities: dict[str, Any] | None = None
    phase: str = "call_auction_0920_0925"
    source: str = "unknown"

    def to_dict(self) -> dict:
        data = asdict(self)
        if isinstance(self.trade_date, date):
            data["trade_date"] = self.trade_date.isoformat()
        if isinstance(self.auction_time, datetime):
            data["auction_time"] = self.auction_time.isoformat(timespec="seconds")
        for key in (
            "indicative_price",
            "matched_amount",
            "prev_close",
            "bid_price",
            "ask_price",
            "withdrawal_buy_amount",
            "withdrawal_sell_amount",
            "seal_price",
            "seal_amount",
        ):
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

    def get_auction_snapshots(self, symbols: list[str], trade_date: str | None = None) -> list[AuctionSnapshot]:
        raise NotImplementedError

    def get_trading_dates(self, start_date: str, end_date: str) -> list[str]:
        raise NotImplementedError

    def health_check(self) -> HealthCheckResult:
        raise NotImplementedError

    def get_capabilities(self) -> MarketDataCapabilities:
        raise NotImplementedError


class AuctionLevel2Provider(MarketDataProvider, Protocol):
    def get_capabilities(self) -> MarketDataCapabilities:
        raise NotImplementedError
