"""Factory for market data providers."""

from __future__ import annotations

from backend.core.config import get_settings

from .akshare_provider import AkShareMarketDataProvider
from .fallback_provider import FallbackMarketDataProvider
from .mootdx_provider import MootdxMarketDataProvider
from .provider import AuctionLevel2Provider, MarketDataProvider


PROVIDERS = {
    "akshare": AkShareMarketDataProvider,
    "mootdx": MootdxMarketDataProvider,
}

AUCTION_LEVEL2_PROVIDERS: dict[str, type[AuctionLevel2Provider]] = {}


def create_market_data_provider(name: str | None = None) -> MarketDataProvider:
    settings = get_settings()
    provider_name = (name or settings.market_data_provider or "mootdx").lower()
    provider_cls = PROVIDERS.get(provider_name)
    if provider_cls is None:
        raise ValueError(f"unsupported market data provider: {provider_name}")
    return provider_cls()


def create_auction_level2_provider(name: str) -> AuctionLevel2Provider:
    provider_name = str(name or "").lower()
    provider_cls = AUCTION_LEVEL2_PROVIDERS.get(provider_name)
    if provider_cls is None:
        raise ValueError(f"unsupported auction Level2 provider: {provider_name}")
    return provider_cls()


def create_fallback_market_data_provider(names: list[str] | None = None) -> FallbackMarketDataProvider:
    settings = get_settings()
    ordered_names = names or [settings.market_data_provider, *settings.market_data_fallbacks]
    providers = []
    seen = set()
    for provider_name in ordered_names:
        normalized = provider_name.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        providers.append(create_market_data_provider(normalized))
    return FallbackMarketDataProvider(providers)
