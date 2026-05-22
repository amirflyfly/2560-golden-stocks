"""Trading and paper execution models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base
from backend.db.mixins import TenantScopedMixin, TimestampMixin


class PaperAccount(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "paper_accounts"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uk_paper_accounts_tenant_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="paper")
    broker_type: Mapped[str] = mapped_column(String(32), nullable=False, default="paper")
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="active")
    currency: Mapped[str] = mapped_column(String(16), nullable=False, default="CNY")
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False, default=Decimal("1000000"))
    cash: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False, default=Decimal("1000000"))
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class TradeSignal(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "trade_signals"
    __table_args__ = (UniqueConstraint("tenant_id", "source_hash", name="uk_trade_signals_source_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    strategy_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    strategy_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    security_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="stock")
    bar_interval: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="1d")
    signal_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    signal_type: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="BUY")
    score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    price_ref: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    data_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="open")
    source_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PaperPosition(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "paper_positions"
    __table_args__ = (UniqueConstraint("tenant_id", "account_id", "symbol", name="uk_paper_positions_account_symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    security_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="stock")
    bar_interval: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="1d")
    quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    market_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    market_value: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False, default=Decimal("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False, default=Decimal("0"))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False, default=Decimal("0"))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PaperOrder(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "paper_orders"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uk_paper_orders_idempotency"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(index=True, nullable=False)
    strategy_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    strategy_code: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    security_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="stock")
    bar_interval: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="1d")
    side: Mapped[str] = mapped_column(String(8), index=True, nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    order_type: Mapped[str] = mapped_column(String(32), nullable=False, default="market")
    requested_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="filled")
    filled_quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    avg_fill_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_signal_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PaperFill(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "paper_fills"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(index=True, nullable=False)
    order_id: Mapped[int] = mapped_column(index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    security_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="stock")
    bar_interval: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="1d")
    side: Mapped[str] = mapped_column(String(8), index=True, nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    filled_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)


class SignalReviewLink(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "signal_review_links"
    __table_args__ = (UniqueConstraint("tenant_id", "source_signal_hash", name="uk_signal_review_links_source_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_signal_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    trade_signal_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    pick_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    buy_order_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    sell_order_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    buy_fill_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    sell_fill_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="open")
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    realized_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
