"""Deterministic mock market data provider for tests and local development."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

from .provider import DailyBar, HealthCheckResult, QuoteSnapshot, StockInfo
from .utils import normalize_bar_interval, parse_date


class MockMarketDataProvider:
    name = "mock"

    def get_stock_list(self) -> list[StockInfo]:
        return [
            StockInfo(symbol="600000", name="浦发银行", exchange="SH"),
            StockInfo(symbol="600519", name="贵州茅台", exchange="SH"),
            StockInfo(symbol="000001", name="平安银行", exchange="SZ"),
            StockInfo(symbol="000002", name="万科A", exchange="SZ"),
            StockInfo(symbol="002594", name="比亚迪", exchange="SZ"),
        ]

    def get_daily_bars(self, symbol: str, start_date: str, end_date: str, adjust: str = "qfq", interval: str = "1d") -> list[DailyBar]:
        start = parse_date(start_date)
        end = parse_date(end_date)
        normalized_interval = normalize_bar_interval(interval)
        current = start
        bars: list[DailyBar] = []
        offset = 0
        while current <= end:
            if current.weekday() < 5:
                times = self._bar_times(normalized_interval)
                for bar_time in times:
                    base = Decimal("10") + Decimal(offset) / Decimal("10")
                    volume = 1000000 + offset * 1000
                    bars.append(
                        DailyBar(
                            symbol=symbol,
                            trade_date=current,
                            trade_time=datetime.combine(current, bar_time),
                            interval=normalized_interval,
                            open=base,
                            high=base + Decimal("0.50"),
                            low=base - Decimal("0.30"),
                            close=base + Decimal("0.10"),
                            volume=volume,
                            amount=(base + Decimal("0.10")) * Decimal(volume),
                            turnover_rate=Decimal("1.23"),
                            source=self.name,
                        )
                    )
                    offset += 1
            current += timedelta(days=1)
        return bars

    def _bar_times(self, interval: str) -> list[time]:
        if interval == "15m":
            return [
                time(9, 45), time(10, 0), time(10, 15), time(10, 30), time(10, 45), time(11, 0), time(11, 15), time(11, 30),
                time(13, 15), time(13, 30), time(13, 45), time(14, 0), time(14, 15), time(14, 30), time(14, 45), time(15, 0),
            ]
        if interval == "30m":
            return [time(10, 0), time(10, 30), time(11, 0), time(11, 30), time(13, 30), time(14, 0), time(14, 30), time(15, 0)]
        if interval == "5m":
            return [time(9, 35), time(9, 40), time(9, 45), time(9, 50), time(9, 55), time(10, 0)]
        if interval in {"1m", "1h"}:
            return [time(10, 30), time(11, 30), time(14, 0), time(15, 0)] if interval == "1h" else [time(9, 31), time(9, 32), time(9, 33), time(9, 34), time(9, 35)]
        return [time(0, 0)]

    def get_quote_snapshots(self, symbols: list[str]) -> list[QuoteSnapshot]:
        snapshots: list[QuoteSnapshot] = []
        for index, symbol in enumerate(symbols):
            base = Decimal("10") + Decimal(index) / Decimal("10")
            snapshots.append(
                QuoteSnapshot(
                    symbol=str(symbol),
                    trade_time=datetime.now(),
                    last_price=base + Decimal("0.10"),
                    open=base,
                    high=base + Decimal("0.50"),
                    low=base - Decimal("0.30"),
                    prev_close=base - Decimal("0.05"),
                    volume=1000000 + index * 1000,
                    amount=(base + Decimal("0.10")) * Decimal(1000000 + index * 1000),
                    bid_price=base + Decimal("0.09"),
                    ask_price=base + Decimal("0.11"),
                    source=self.name,
                )
            )
        return snapshots

    def get_trading_dates(self, start_date: str, end_date: str) -> list[str]:
        start = parse_date(start_date)
        end = parse_date(end_date)
        current = start
        dates: list[str] = []
        while current <= end:
            if current.weekday() < 5:
                dates.append(current.isoformat())
            current += timedelta(days=1)
        return dates

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(provider=self.name, ok=True)
