"""External push delivery audit models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base
from backend.db.mixins import TenantScopedMixin, TimestampMixin


class ExternalPushDelivery(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "external_push_deliveries"
    __table_args__ = (UniqueConstraint("tenant_id", "delivery_key", name="uk_external_push_deliveries_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(nullable=True)
    delivery_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="queued")
    task_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="")
    retry_count: Mapped[int] = mapped_column(nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False, default="")
    channel_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="")
    notification_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notification_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
