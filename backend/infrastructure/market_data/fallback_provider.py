"""Fallback market data provider.

The fallback provider tries providers in order and only returns an error when all
providers fail. This keeps mootdx outages from breaking strategy workflows.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
import os
import queue
import threading
from typing import TypeVar

from .provider import AuctionSnapshot, DailyBar, HealthCheckResult, MarketDataProvider, QuoteSnapshot, StockInfo

T = TypeVar("T")


@dataclass(frozen=True)
class ProviderUsage:
    primary_provider: str
    actual_provider: str
    provider_chain: list[str]
    fallback_used: bool
    data_quality: str
    errors: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


class FallbackMarketDataProvider:
    name = "fallback"

    def __init__(self, providers: list[MarketDataProvider], timeout_seconds: float | None = None):
        if not providers:
            raise ValueError("at least one provider is required")
        self.providers = providers
        self.timeout_seconds = self._resolve_timeout(timeout_seconds)
        self.last_usage = ProviderUsage(
            primary_provider=providers[0].name,
            actual_provider=providers[0].name,
            provider_chain=[provider.name for provider in providers],
            fallback_used=False,
            data_quality="unknown",
            errors=[],
        )

    def _resolve_timeout(self, value: float | None) -> float:
        if value is None:
            raw = os.getenv("MARKET_DATA_PROVIDER_TIMEOUT_SECONDS", "15")
        else:
            raw = value
        try:
            timeout = float(raw)
        except (TypeError, ValueError):
            timeout = 15.0
        return max(0.1, min(timeout, 120.0))

    def _call_with_timeout(self, provider: MarketDataProvider, method_name: str, *args, **kwargs):
        method: Callable[..., T] = getattr(provider, method_name)
        result_queue: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

        def run():
            try:
                result_queue.put(("ok", method(*args, **kwargs)))
            except BaseException as exc:  # pragma: no cover - defensive wrapper for provider libraries.
                result_queue.put(("error", exc))

        thread = threading.Thread(target=run, name=f"market-data-{provider.name}-{method_name}", daemon=True)
        thread.start()
        thread.join(self.timeout_seconds)
        if thread.is_alive():
            raise TimeoutError(f"{method_name} timed out after {self.timeout_seconds:g}s")
        status, value = result_queue.get_nowait()
        if status == "error":
            raise value
        return value

    def _quality_for(self, provider_name: str, fallback_used: bool) -> str:
        if provider_name == "mock":
            raise RuntimeError("mock market data provider is disabled")
        if fallback_used:
            return "fallback"
        return "primary"

    def _record_usage(self, provider_name: str, errors: list[str]) -> ProviderUsage:
        primary_provider = self.providers[0].name
        fallback_used = provider_name != primary_provider
        self.last_usage = ProviderUsage(
            primary_provider=primary_provider,
            actual_provider=provider_name,
            provider_chain=[provider.name for provider in self.providers],
            fallback_used=fallback_used,
            data_quality=self._quality_for(provider_name, fallback_used),
            errors=list(errors),
        )
        return self.last_usage

    def usage_metadata(self) -> dict:
        return self.last_usage.to_dict()

    def _try_each(self, method_name: str, *args, **kwargs):
        errors: list[str] = []
        for provider in self.providers:
            try:
                result = self._call_with_timeout(provider, method_name, *args, **kwargs)
                if result:
                    self._record_usage(provider.name, errors)
                    return result
                errors.append(f"{provider.name}: empty result")
            except Exception as exc:
                errors.append(f"{provider.name}: {exc}")
        raise RuntimeError("all market data providers failed: " + " | ".join(errors))

    def get_stock_list(self) -> list[StockInfo]:
        return self._try_each("get_stock_list")

    def get_daily_bars(self, symbol: str, start_date: str, end_date: str, adjust: str = "qfq", interval: str = "1d") -> list[DailyBar]:
        return self._try_each("get_daily_bars", symbol, start_date, end_date, adjust, interval=interval)

    def get_quote_snapshots(self, symbols: list[str]) -> list[QuoteSnapshot]:
        return self._try_each("get_quote_snapshots", symbols)

    def get_auction_snapshots(self, symbols: list[str], trade_date: str | None = None) -> list[AuctionSnapshot]:
        return self._try_each("get_auction_snapshots", symbols, trade_date)

    def get_trading_dates(self, start_date: str, end_date: str) -> list[str]:
        return self._try_each("get_trading_dates", start_date, end_date)

    def health_check(self) -> HealthCheckResult:
        messages: list[str] = []
        errors: list[str] = []
        for provider in self.providers:
            try:
                result = self._call_with_timeout(provider, "health_check")
            except Exception as exc:
                result = HealthCheckResult(provider=provider.name, ok=False, message=str(exc))
            messages.append(f"{provider.name}={result.ok}")
            if result.ok:
                self._record_usage(provider.name, errors)
                return HealthCheckResult(provider=provider.name, ok=True, message="; ".join(messages))
            errors.append(f"{provider.name}: {result.message}")
        return HealthCheckResult(provider=self.name, ok=False, message="; ".join(messages))
