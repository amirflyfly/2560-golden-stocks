"""Market data models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base
from backend.db.mixins import TenantScopedMixin, TimestampMixin


class Stock(TimestampMixin, Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    market: Mapped[str | None] = mapped_column(String(32), nullable=True)
    security_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="stock")
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    listing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    is_st: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    board_type: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    limit_rule_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_delisting: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class LimitRuleCalendar(TimestampMixin, Base):
    __tablename__ = "limit_rule_calendar"
    __table_args__ = (
        UniqueConstraint("exchange", "board_type", "security_type", "risk_warning", "effective_from", name="uk_limit_rule_calendar_profile_start"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="")
    board_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="main")
    security_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="stock")
    risk_warning: Mapped[bool] = mapped_column(Boolean, index=True, nullable=False, default=False)
    effective_from: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    limit_up_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    limit_down_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    no_limit_first_days: Mapped[int] = mapped_column(nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="active")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class StockDailyBar(Base):
    __tablename__ = "stock_daily_bars"
    __table_args__ = (UniqueConstraint("symbol", "trade_date", "trade_time", "interval", "source", "adjust", name="uk_bar_symbol_time_interval_source_adjust"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    trade_time: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    interval: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="1d")
    adjust: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="qfq")
    open: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    high: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    low: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    close: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    volume: Mapped[int | None] = mapped_column(nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    turnover_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)


class StockPriceSnapshot(TimestampMixin, Base):
    __tablename__ = "stock_price_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False, unique=True)
    trade_time: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    open: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    high: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    low: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    prev_close: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    volume: Mapped[int | None] = mapped_column(nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    bid_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    ask_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    source: Mapped[str] = mapped_column(String(32), index=True, nullable=False)


class MarketSyncState(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "market_sync_states"
    __table_args__ = (
        UniqueConstraint("tenant_id", "symbol", "source", "adjust", "interval", name="uk_market_sync_state_symbol_source_adjust_interval"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="auto")
    adjust: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="qfq")
    interval: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="1d")
    coverage_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    coverage_end_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    last_success_trade_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="pending")
    error_count: Mapped[int] = mapped_column(nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class MarketSyncRun(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "market_sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_no: Mapped[str] = mapped_column(String(64), index=True, nullable=False, unique=True)
    mode: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="incremental")
    source: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="auto")
    adjust: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="qfq")
    interval: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="1d")
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="running")
    requested_symbols: Mapped[int] = mapped_column(nullable=False, default=0)
    synced_symbols: Mapped[int] = mapped_column(nullable=False, default=0)
    failed_symbols: Mapped[int] = mapped_column(nullable=False, default=0)
    persisted_bars: Mapped[int] = mapped_column(nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class MarketSyncRunItem(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "market_sync_run_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="running")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    bars: Mapped[int] = mapped_column(nullable=False, default=0)
    persisted_bars: Mapped[int] = mapped_column(nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="auto")
    adjust: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="qfq")
    interval: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="1d")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
