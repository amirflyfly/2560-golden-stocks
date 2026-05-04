from datetime import date

import pytest

from backend.core.config import Settings
from backend.infrastructure.market_data.fallback_provider import FallbackMarketDataProvider
from backend.infrastructure.market_data.mock_provider import MockMarketDataProvider
from backend.infrastructure.market_data.mootdx_provider import MootdxMarketDataProvider
from backend.infrastructure.market_data.provider import HealthCheckResult


class BrokenProvider:
    name = "broken"

    def get_stock_list(self):
        raise RuntimeError("broken stock list")

    def get_daily_bars(self, symbol, start_date, end_date, adjust="qfq"):
        raise RuntimeError("broken daily bars")

    def get_trading_dates(self, start_date, end_date):
        raise RuntimeError("broken trading dates")

    def health_check(self):
        return HealthCheckResult(provider=self.name, ok=False, message="broken")


def test_mock_provider_returns_normalized_daily_bars():
    provider = MockMarketDataProvider()
    bars = provider.get_daily_bars("000001", "2026-04-27", "2026-05-02")

    assert bars
    assert bars[0].symbol == "000001"
    assert bars[0].trade_date == date(2026, 4, 27)
    assert bars[0].source == "mock"
    assert "open" in bars[0].to_dict()


def test_fallback_provider_uses_next_provider_when_first_fails():
    provider = FallbackMarketDataProvider([BrokenProvider(), MockMarketDataProvider()])

    bars = provider.get_daily_bars("000001", "2026-04-27", "2026-05-02")
    usage = provider.usage_metadata()

    assert bars
    assert bars[0].source == "mock"
    assert usage["primary_provider"] == "broken"
    assert usage["actual_provider"] == "mock"
    assert usage["fallback_used"] is True
    assert usage["data_quality"] == "mock"
    assert usage["errors"] == ["broken: broken daily bars"]
    assert provider.health_check().ok is True


def test_fallback_provider_raises_when_all_providers_fail():
    provider = FallbackMarketDataProvider([BrokenProvider()])

    with pytest.raises(RuntimeError):
        provider.get_stock_list()


def test_mootdx_provider_health_check_does_not_raise_when_unavailable():
    provider = MootdxMarketDataProvider()
    result = provider.health_check()

    assert result.provider == "mootdx"
    assert isinstance(result.ok, bool)


def test_production_rejects_mock_market_data_provider(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_DEBUG", "0")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://strategy:strong-password@mysql:3306/strategy_2560")
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "mock")
    monkeypatch.setenv("MARKET_DATA_FALLBACKS", "akshare")

    with pytest.raises(RuntimeError, match="MARKET_DATA_PROVIDER=mock"):
        Settings.from_env()


def test_production_rejects_mock_market_data_fallback(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_DEBUG", "0")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://strategy:strong-password@mysql:3306/strategy_2560")
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "mootdx")
    monkeypatch.setenv("MARKET_DATA_FALLBACKS", "akshare,mock")

    with pytest.raises(RuntimeError, match="MARKET_DATA_FALLBACKS"):
        Settings.from_env()


def test_parse_date_accepts_datetime_text_from_mootdx():
    from backend.infrastructure.market_data.utils import parse_date

    parsed = parse_date("2023-01-09 15:00")

    assert parsed == date(2023, 1, 9)
