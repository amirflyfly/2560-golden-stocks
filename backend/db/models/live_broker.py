"""Live broker boundary persistence models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base
from backend.db.mixins import TenantScopedMixin, TimestampMixin


class LiveBrokerRequest(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "live_broker_requests"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uk_live_broker_requests_idempotency"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    adapter: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    account_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False, default="")
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="pending")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    client_order_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    response_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class LiveBrokerFill(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "live_broker_fills"
    __table_args__ = (UniqueConstraint("tenant_id", "fill_key", name="uk_live_broker_fills_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False, default="")
    broker_order_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    client_order_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="")
    side: Mapped[str] = mapped_column(String(8), index=True, nullable=False, default="")
    quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(24, 4), nullable=True)
    fee: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(16), nullable=False, default="CNY")
    filled_at: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)
    fill_key: Mapped[str] = mapped_column(String(180), nullable=False)
    source: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="callback")
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class LiveBrokerReconciliation(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "live_broker_reconciliations"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uk_live_broker_reconciliations_idempotency"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False, default="")
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="reconciled")
    differences_count: Mapped[int] = mapped_column(nullable=False, default=0)
    request_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
