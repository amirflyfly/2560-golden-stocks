"""Deterministic mock market data provider for tests and local development."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from .provider import DailyBar, HealthCheckResult, StockInfo
from .utils import parse_date


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

    def get_daily_bars(self, symbol: str, start_date: str, end_date: str, adjust: str = "qfq") -> list[DailyBar]:
        start = parse_date(start_date)
        end = parse_date(end_date)
        current = start
        bars: list[DailyBar] = []
        offset = 0
        while current <= end:
            if current.weekday() < 5:
                base = Decimal("10") + Decimal(offset) / Decimal("10")
                bars.append(
                    DailyBar(
                        symbol=symbol,
                        trade_date=current,
                        open=base,
                        high=base + Decimal("0.50"),
                        low=base - Decimal("0.30"),
                        close=base + Decimal("0.10"),
                        volume=1000000 + offset * 1000,
                        amount=(base + Decimal("0.10")) * Decimal(1000000 + offset * 1000),
                        turnover_rate=Decimal("1.23"),
                        source=self.name,
                    )
                )
                offset += 1
            current += timedelta(days=1)
        return bars

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
