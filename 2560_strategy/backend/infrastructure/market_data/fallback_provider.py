"""Fallback market data provider.

The fallback provider tries providers in order and only returns an error when all
providers fail. This keeps mootdx outages from breaking strategy workflows.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import TypeVar

from .provider import DailyBar, HealthCheckResult, MarketDataProvider, QuoteSnapshot, StockInfo

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

    def __init__(self, providers: list[MarketDataProvider]):
        if not providers:
            raise ValueError("at least one provider is required")
        self.providers = providers
        self.last_usage = ProviderUsage(
            primary_provider=providers[0].name,
            actual_provider=providers[0].name,
            provider_chain=[provider.name for provider in providers],
            fallback_used=False,
            data_quality="unknown",
            errors=[],
        )

    def _quality_for(self, provider_name: str, fallback_used: bool) -> str:
        if provider_name == "mock":
            return "mock"
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
                method: Callable[..., T] = getattr(provider, method_name)
                result = method(*args, **kwargs)
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

    def get_trading_dates(self, start_date: str, end_date: str) -> list[str]:
        return self._try_each("get_trading_dates", start_date, end_date)

    def health_check(self) -> HealthCheckResult:
        messages: list[str] = []
        errors: list[str] = []
        for provider in self.providers:
            result = provider.health_check()
            messages.append(f"{provider.name}={result.ok}")
            if result.ok:
                self._record_usage(provider.name, errors)
                return HealthCheckResult(provider=provider.name, ok=True, message="; ".join(messages))
            errors.append(f"{provider.name}: {result.message}")
        return HealthCheckResult(provider=self.name, ok=False, message="; ".join(messages))
