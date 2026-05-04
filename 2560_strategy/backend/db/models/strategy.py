"""Strategy, scan and pick models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base
from backend.db.mixins import SoftDeleteMixin, TenantScopedMixin, TimestampMixin


class Strategy(TenantScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "strategies"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uk_strategies_tenant_code"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[int | None] = mapped_column(nullable=True)


class ScanTask(TenantScopedMixin, Base):
    __tablename__ = "scan_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), index=True, nullable=False)
    task_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="pending")
    params_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ScanResult(TenantScopedMixin, Base):
    __tablename__ = "scan_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scan_task_id: Mapped[int] = mapped_column(ForeignKey("scan_tasks.id"), index=True, nullable=False)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    stock_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    signals_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Pick(TenantScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "picks"
    __table_args__ = (UniqueConstraint("tenant_id", "trade_date", "symbol", "source", name="uk_picks_tenant_date_symbol_source"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    stock_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("strategies.id"), index=True, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    source_channel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    deal_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    return_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    max_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    drawdown_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    holding_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    watch_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_result: Mapped[str | None] = mapped_column(String(128), nullable=True)
    validation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    data_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    market_data_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    legacy_payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[int | None] = mapped_column(nullable=True)


class StrategyPool(Base):
    __tablename__ = "strategy_pools"
    __table_args__ = (UniqueConstraint("strategy_code", "code", name="uk_strategy_pools_strategy_code"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    strategy_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    add_date: Mapped[str] = mapped_column(String(16), nullable=False)
    add_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    strategy_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    start_date: Mapped[str] = mapped_column(String(16), nullable=False)
    end_date: Mapped[str] = mapped_column(String(16), nullable=False)
    total_trades: Mapped[int | None] = mapped_column(Integer, nullable=True)
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    avg_return: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    max_return: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    max_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    sharpe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    total_return: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    backtest_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ResearchReport(Base):
    __tablename__ = "research_reports"
    __table_args__ = (UniqueConstraint("pick_id", "analysis_date", name="uk_research_reports_pick_analysis"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pick_id: Mapped[int] = mapped_column(index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    pick_date: Mapped[str] = mapped_column(String(16), nullable=False)
    analysis_date: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    technical_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    momentum_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    risk_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    liquidity_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    timing_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    research_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    action_suggestion: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    risk_warning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    data_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
