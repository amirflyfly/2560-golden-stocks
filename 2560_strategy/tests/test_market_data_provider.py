from datetime import date, datetime
from decimal import Decimal

import pytest

from backend.core.config import Settings
from backend.application.sync_api_service import SyncApiService
from backend.infrastructure.market_data.factory import create_auction_level2_provider
from backend.infrastructure.market_data.fallback_provider import FallbackMarketDataProvider
from backend.infrastructure.market_data.mootdx_provider import MootdxMarketDataProvider
from backend.infrastructure.market_data.provider import AuctionSnapshot, DailyBar, HealthCheckResult, MarketDataCapabilities, StockInfo


class BrokenProvider:
    name = "broken"

    def get_stock_list(self):
        raise RuntimeError("broken stock list")

    def get_daily_bars(self, symbol, start_date, end_date, adjust="qfq", interval="1d"):
        raise RuntimeError("broken daily bars")

    def get_trading_dates(self, start_date, end_date):
        raise RuntimeError("broken trading dates")

    def health_check(self):
        return HealthCheckResult(provider=self.name, ok=False, message="broken")


class WorkingProvider:
    name = "akshare"

    def get_stock_list(self):
        return []

    def get_daily_bars(self, symbol, start_date, end_date, adjust="qfq", interval="1d"):
        return [
            DailyBar(
                symbol=symbol,
                trade_date=date(2026, 4, 27),
                open=Decimal("10"),
                high=Decimal("10.5"),
                low=Decimal("9.8"),
                close=Decimal("10.1"),
                volume=1000,
                amount=Decimal("10100"),
                source=self.name,
                interval=interval,
            )
        ]

    def get_trading_dates(self, start_date, end_date):
        return [start_date]

    def health_check(self):
        return HealthCheckResult(provider=self.name, ok=True)


def test_fallback_provider_uses_next_provider_when_first_fails():
    provider = FallbackMarketDataProvider([BrokenProvider(), WorkingProvider()])

    bars = provider.get_daily_bars("000001", "2026-04-27", "2026-05-02")
    usage = provider.usage_metadata()

    assert bars
    assert bars[0].source == "akshare"
    assert usage["primary_provider"] == "broken"
    assert usage["actual_provider"] == "akshare"
    assert usage["fallback_used"] is True
    assert usage["data_quality"] == "fallback"
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


def test_mootdx_provider_get_stock_list_filters_to_a_share_stocks():
    class FakeMootdxClient:
        def __init__(self):
            self.calls = []

        def stocks(self, market):
            self.calls.append(market)
            if market == 0:
                return [
                    {"code": "000001", "name": "Ping An\x00"},
                    {"code": "300750", "name": "CATL"},
                    {"code": "430047", "name": "BSE Co"},
                    {"code": "000015", "name": "\u7ea2\u5229\u6307\u6570"},
                    {"code": "100609", "name": "Treasury Bond"},
                    {"code": "159001", "name": "ETF"},
                    {"code": "399001", "name": "Index"},
                ]
            return [
                {"code": "600519", "name": "Moutai"},
                {"code": "688001", "name": "STAR Co"},
                {"code": "510300", "name": "ETF"},
                {"code": "113001", "name": "Convertible Bond"},
            ]

    provider = MootdxMarketDataProvider()
    fake_client = FakeMootdxClient()
    provider._quotes_client = fake_client

    items = provider.get_stock_list()

    assert fake_client.calls == [0, 1]
    assert [item.symbol for item in items] == ["000001", "300750", "430047", "000015", "100609", "159001", "399001", "600519", "688001", "510300", "113001"]
    assert {item.symbol: item.exchange for item in items} == {
        "000001": "SZ",
        "300750": "SZ",
        "430047": "BJ",
        "000015": "SZ",
        "100609": "SH",
        "159001": "SZ",
        "399001": "SZ",
        "600519": "SH",
        "688001": "SH",
        "510300": "SH",
        "113001": "SH",
    }
    assert {item.symbol: item.security_type for item in items}["000015"] == "index"
    assert {item.symbol: item.security_type for item in items}["113001"] == "convertible_bond"
    assert {item.symbol: item.security_type for item in items}["510300"] == "etf"
    assert items[0].name == "Ping An"


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


def test_mootdx_auction_snapshots_mark_derived_l1_without_fake_level2_fields():
    class FakeMootdxClient:
        def quotes(self, symbol):
            return [
                {
                    "code": "000001",
                    "datetime": "2026-05-06 09:24:00",
                    "open": "10.10",
                    "price": "10.12",
                    "last_close": "10.00",
                    "vol": "1200",
                    "amount": "12120",
                    "bid1": "10.11",
                    "ask1": "10.12",
                }
            ]

    provider = MootdxMarketDataProvider()
    provider._quotes_client = FakeMootdxClient()

    snapshots = provider.get_auction_snapshots(["000001"], "2026-05-06")

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.source_quality == "derived_l1"
    assert snapshot.capabilities["auction_level2"] is False
    assert snapshot.capabilities["auction_withdrawal"] is False
    assert snapshot.capabilities["auction_seal"] is False
    assert snapshot.order_book["source_quality"] == "derived_l1"
    assert snapshot.withdrawal_buy_volume is None
    assert snapshot.withdrawal_sell_volume is None
    assert snapshot.seal_volume is None
    assert snapshot.seal_amount is None


def test_sync_auction_result_exposes_source_quality_and_capabilities(monkeypatch):
    class RealAuctionLevel2Provider:
        name = "real_level2"

        def get_stock_list(self):
            return [StockInfo(symbol="000001", name="Ping An", exchange="SZ")]

        def get_capabilities(self):
            return MarketDataCapabilities(
                provider=self.name,
                auction_snapshots=True,
                auction_source_quality="level2_realtime",
                auction_level2=True,
                auction_order_book_depth=10,
                auction_withdrawal=True,
                auction_seal=True,
                auction_fields=["withdrawal_buy_volume", "seal_volume", "order_book"],
            )

        def get_auction_snapshots(self, symbols, trade_date=None):
            capabilities = self.get_capabilities().to_dict()
            return [
                AuctionSnapshot(
                    symbol=symbols[0],
                    trade_date=date(2026, 5, 6),
                    auction_time=datetime(2026, 5, 6, 9, 24),
                    indicative_price=Decimal("10.10"),
                    matched_volume=1000,
                    withdrawal_buy_volume=200,
                    withdrawal_sell_volume=50,
                    seal_price=Decimal("10.50"),
                    seal_volume=800,
                    seal_side="buy",
                    order_book={"bids": [{"price": "10.10", "volume": 1000}], "asks": []},
                    source_quality="level2_realtime",
                    capabilities=capabilities,
                    source=self.name,
                )
            ]

    monkeypatch.setattr(SyncApiService, "_auction_window_status", lambda self, trade_date=None: {"allowed": True, "reason": "test"})
    monkeypatch.setattr("backend.application.sync_api_service.market_data_repo.upsert_auction_snapshots", lambda snapshots: len(snapshots))
    monkeypatch.setattr("backend.application.sync_api_service.market_data_repo.auction_snapshot_summary", lambda security_type=None: {"snapshot_count": 1})

    result = SyncApiService(RealAuctionLevel2Provider())._sync_auction_snapshots(["000001"], "2026-05-06")

    assert result["status"] == "completed"
    assert result["source"] == "real_level2"
    assert result["source_quality"] == "level2_realtime"
    assert result["capabilities"]["auction_level2"] is True
    assert result["capabilities"]["auction_withdrawal"] is True
    assert result["capabilities"]["auction_seal"] is True


def test_factory_has_explicit_auction_level2_registry_boundary():
    with pytest.raises(ValueError, match="unsupported auction Level2 provider"):
        create_auction_level2_provider("akshare")
