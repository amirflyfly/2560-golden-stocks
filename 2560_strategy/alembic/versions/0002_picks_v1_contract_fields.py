"""Add v1 contract fields to picks.

Revision ID: 0002_picks_v1_contract_fields
Revises: 0001_initial_mysql_schema
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_picks_v1_contract_fields"
down_revision = "0001_initial_mysql_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("picks", sa.Column("source_channel", sa.String(length=64), nullable=True))
    op.add_column("picks", sa.Column("review_comment", sa.Text(), nullable=True))
    op.add_column("picks", sa.Column("risk_level", sa.String(length=32), nullable=True))
    op.add_column("picks", sa.Column("deal_status", sa.String(length=32), nullable=True))
    op.add_column("picks", sa.Column("return_pct", sa.Numeric(12, 4), nullable=True))
    op.add_column("picks", sa.Column("max_return_pct", sa.Numeric(12, 4), nullable=True))
    op.add_column("picks", sa.Column("drawdown_pct", sa.Numeric(12, 4), nullable=True))
    op.add_column("picks", sa.Column("holding_days", sa.Integer(), nullable=True))
    op.add_column("picks", sa.Column("watch_flag", sa.Boolean(), server_default=sa.text("0"), nullable=False))
    op.add_column("picks", sa.Column("validation_result", sa.String(length=128), nullable=True))
    op.add_column("picks", sa.Column("validation_note", sa.Text(), nullable=True))
    op.add_column("picks", sa.Column("validated_at", sa.DateTime(), nullable=True))
    op.add_column("picks", sa.Column("data_quality", sa.String(length=32), nullable=True))
    op.add_column("picks", sa.Column("market_data_source", sa.String(length=64), nullable=True))
    op.add_column("picks", sa.Column("fallback_used", sa.Boolean(), server_default=sa.text("0"), nullable=False))
    op.create_unique_constraint(
        "uk_picks_tenant_date_symbol_source",
        "picks",
        ["tenant_id", "trade_date", "symbol", "source"],
    )


def downgrade() -> None:
    op.drop_constraint("uk_picks_tenant_date_symbol_source", "picks", type_="unique")
    op.drop_column("picks", "fallback_used")
    op.drop_column("picks", "market_data_source")
    op.drop_column("picks", "data_quality")
    op.drop_column("picks", "validated_at")
    op.drop_column("picks", "validation_note")
    op.drop_column("picks", "validation_result")
    op.drop_column("picks", "watch_flag")
    op.drop_column("picks", "holding_days")
    op.drop_column("picks", "drawdown_pct")
    op.drop_column("picks", "max_return_pct")
    op.drop_column("picks", "return_pct")
    op.drop_column("picks", "deal_status")
    op.drop_column("picks", "risk_level")
    op.drop_column("picks", "review_comment")
    op.drop_column("picks", "source_channel")
