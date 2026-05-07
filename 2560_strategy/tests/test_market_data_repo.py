from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from backend.infrastructure.market_data.provider import AuctionSnapshot, DailyBar, QuoteSnapshot, StockInfo
from backend.repositories import market_data_repo


@pytest.fixture
def temp_market_db(tmp_path, monkeypatch):
    import backend.repositories.db as db_module

    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = tmp_path / "picks.db"
    monkeypatch.setenv("MARKET_DATA_REPOSITORY_BACKEND", "sqlite")
    db_module.ensure_schema()
    try:
        yield
    finally:
        db_module.DB_PATH = original_db_path


def test_market_data_repo_classifies_security_types(temp_market_db):
    inserted = market_data_repo.upsert_stocks(
        [
            StockInfo("000001", "Ping An\x00", "SZ"),
            StockInfo("600519", "Moutai", "SH"),
            StockInfo("430047", "BSE Co", "BJ"),
            StockInfo("000015", "\u7ea2\u5229\u6307\u6570", "SZ"),
            StockInfo("100609", "Treasury Bond", ""),
            StockInfo("159001", "ETF", "SZ"),
            StockInfo("399001", "Index", "SZ"),
        ]
    )

    listed = market_data_repo.list_stocks(limit=500)
    symbols = [item["symbol"] for item in listed["items"]]
    stock_only = market_data_repo.list_stocks(limit=500, security_type="stock")
    summary = market_data_repo.coverage_summary()

    assert inserted == 7
    assert listed["total"] == 7
    assert symbols == ["000001", "000015", "100609", "159001", "399001", "430047", "600519"]
    assert listed["items"][0]["name"] == "Ping An"
    assert {item["symbol"]: item["security_type"] for item in listed["items"]} == {
        "000001": "stock",
        "000015": "index",
        "100609": "bond",
        "159001": "etf",
        "399001": "index",
        "430047": "stock",
        "600519": "stock",
    }
    assert [item["symbol"] for item in stock_only["items"]] == ["000001", "430047", "600519"]
    assert summary["security_count"] == 7
    assert summary["stock_count"] == 3
    assert summary["security_type_counts"]["index"] == 2


def test_market_data_repo_persists_non_stock_market_payloads_with_intervals(temp_market_db):
    persisted_bars = market_data_repo.upsert_daily_bars(
        [
            DailyBar("000001", date(2026, 5, 4), Decimal("1"), Decimal("2"), Decimal("1"), Decimal("2"), 100, Decimal("200"), source="unit"),
            DailyBar(
                "100609",
                date(2026, 5, 4),
                Decimal("1"),
                Decimal("2"),
                Decimal("1"),
                Decimal("2"),
                100,
                Decimal("200"),
                source="unit",
                interval="15m",
                trade_time=datetime(2026, 5, 4, 9, 45, 0),
            ),
        ],
        adjust="qfq",
    )
    persisted_snapshots = market_data_repo.upsert_quote_snapshots(
        [
            QuoteSnapshot("000001", datetime(2026, 5, 4, 15, 0, 0), Decimal("2"), Decimal("1"), Decimal("2"), Decimal("1"), source="unit"),
            QuoteSnapshot("510300", datetime(2026, 5, 4, 15, 0, 0), Decimal("2"), Decimal("1"), Decimal("2"), Decimal("1"), source="unit"),
        ]
    )

    intraday_bars = market_data_repo.get_daily_bars("100609", "2026-05-04", "2026-05-04", interval="15m")
    intraday_coverage = market_data_repo.list_coverage(security_type="bond", interval="15m")

    assert persisted_bars == 2
    assert persisted_snapshots == 2
    assert intraday_bars[0]["interval"] == "15m"
    assert intraday_bars[0]["trade_time"].startswith("2026-05-04T09:45:00")
    assert intraday_coverage["items"][0]["symbol"] == "100609"
    assert intraday_coverage["items"][0]["intervals"] == ["15m"]
    assert intraday_coverage["items"][0]["adjusts"] == ["qfq"]
    assert intraday_coverage["items"][0]["sources"] == ["unit"]
    assert intraday_coverage["items"][0]["last_trade_time"].startswith("2026-05-04T09:45:00")
    assert market_data_repo.get_symbol_coverage("100609", interval="15m")["last_trade_time"].startswith("2026-05-04T09:45:00")
    assert market_data_repo.coverage_summary()["synced_symbols"] == 2
    assert market_data_repo.coverage_summary(interval="15m")["synced_symbols"] == 1
    assert market_data_repo.snapshot_summary()["snapshot_count"] == 2


def test_market_data_repo_persists_auction_snapshots(temp_market_db):
    persisted = market_data_repo.upsert_auction_snapshots(
        [
            AuctionSnapshot(
                symbol="000001",
                trade_date=date(2026, 5, 6),
                auction_time=datetime(2026, 5, 6, 9, 25, 0),
                prev_close=Decimal("11.00"),
                indicative_price=Decimal("11.42"),
                matched_volume=280,
                matched_amount=Decimal("3900000"),
                unmatched_buy_volume=900,
                unmatched_sell_volume=120,
                order_book={"bid1": {"price": "11.42", "volume": 900}},
                withdrawal_buy_volume=40,
                withdrawal_sell_volume=20,
                seal_price=Decimal("11.42"),
                seal_volume=600,
                seal_amount=Decimal("6852000"),
                seal_side="buy",
                source="unit",
            )
        ]
    )

    latest = market_data_repo.get_latest_auction_snapshot("000001")
    summary = market_data_repo.auction_snapshot_summary(security_type="stock")

    assert persisted == 1
    assert latest["phase"] == "call_auction_0920_0925"
    assert latest["indicative_price"] == 11.42
    assert latest["matched_amount"] == 3900000
    assert latest["order_book"]["bid1"]["volume"] == 900
    assert latest["withdrawal_sell_volume"] == 20
    assert latest["seal_side"] == "buy"
    assert summary["snapshot_count"] == 1


def test_market_data_repo_tracks_sync_state_per_interval(temp_market_db):
    market_data_repo.upsert_daily_bars(
        [
            DailyBar(
                "123001",
                date(2026, 5, 4),
                Decimal("1"),
                Decimal("2"),
                Decimal("1"),
                Decimal("2"),
                100,
                Decimal("200"),
                source="unit",
                interval="15m",
                trade_time=datetime(2026, 5, 4, 9, 45, 0),
            ),
        ],
        adjust="none",
    )

    state = market_data_repo.upsert_sync_state(
        1,
        symbol="123001",
        source="unit",
        adjust="none",
        interval="15m",
        status="success",
    )
    listed = market_data_repo.list_sync_states(1, interval="15m")

    assert state["interval"] == "15m"
    assert listed["summary"]["interval"] == "15m"
    assert listed["items"][0]["symbol"] == "123001"
