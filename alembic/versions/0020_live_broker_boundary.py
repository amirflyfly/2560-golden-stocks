"""Add live broker boundary persistence.

Revision ID: 0020_live_broker_boundary
Revises: 0019_auction_snapshots
Create Date: 2026-05-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0020_live_broker_boundary"
down_revision = "0019_auction_snapshots"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    ]


def upgrade() -> None:
    op.create_table(
        "live_broker_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("adapter", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("request_hash", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("broker_order_id", sa.String(length=128), nullable=True),
        sa.Column("client_order_id", sa.String(length=128), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("response_json", sa.JSON(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uk_live_broker_requests_idempotency"),
    )
    op.create_index("ix_live_broker_requests_tenant_id", "live_broker_requests", ["tenant_id"])
    op.create_index("ix_live_broker_requests_action", "live_broker_requests", ["action"])
    op.create_index("ix_live_broker_requests_adapter", "live_broker_requests", ["adapter"])
    op.create_index("ix_live_broker_requests_account_id", "live_broker_requests", ["account_id"])
    op.create_index("ix_live_broker_requests_status", "live_broker_requests", ["status"])
    op.create_index("ix_live_broker_requests_broker_order_id", "live_broker_requests", ["broker_order_id"])
    op.create_index("ix_live_broker_requests_client_order_id", "live_broker_requests", ["client_order_id"])
    op.create_index("ix_live_broker_requests_created_at", "live_broker_requests", ["created_at"])
    op.create_index("ix_live_broker_requests_rate_window", "live_broker_requests", ["tenant_id", "action", "created_at"])

    op.create_table(
        "live_broker_fills",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("broker_order_id", sa.String(length=128), nullable=True),
        sa.Column("client_order_id", sa.String(length=128), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("side", sa.String(length=8), nullable=False, server_default=""),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price", sa.Numeric(18, 4), nullable=True),
        sa.Column("amount", sa.Numeric(24, 4), nullable=True),
        sa.Column("fee", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=False, server_default="CNY"),
        sa.Column("filled_at", sa.DateTime(), nullable=True),
        sa.Column("fill_key", sa.String(length=180), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="callback"),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "fill_key", name="uk_live_broker_fills_key"),
    )
    op.create_index("ix_live_broker_fills_tenant_id", "live_broker_fills", ["tenant_id"])
    op.create_index("ix_live_broker_fills_account_id", "live_broker_fills", ["account_id"])
    op.create_index("ix_live_broker_fills_broker_order_id", "live_broker_fills", ["broker_order_id"])
    op.create_index("ix_live_broker_fills_client_order_id", "live_broker_fills", ["client_order_id"])
    op.create_index("ix_live_broker_fills_symbol", "live_broker_fills", ["symbol"])
    op.create_index("ix_live_broker_fills_side", "live_broker_fills", ["side"])
    op.create_index("ix_live_broker_fills_filled_at", "live_broker_fills", ["filled_at"])
    op.create_index("ix_live_broker_fills_source", "live_broker_fills", ["source"])
    op.create_index("ix_live_broker_fills_account_created", "live_broker_fills", ["tenant_id", "account_id", "created_at"])

    op.create_table(
        "live_broker_reconciliations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="reconciled"),
        sa.Column("differences_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_json", sa.JSON(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uk_live_broker_reconciliations_idempotency"),
    )
    op.create_index("ix_live_broker_reconciliations_tenant_id", "live_broker_reconciliations", ["tenant_id"])
    op.create_index("ix_live_broker_reconciliations_account_id", "live_broker_reconciliations", ["account_id"])
    op.create_index("ix_live_broker_reconciliations_status", "live_broker_reconciliations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_live_broker_reconciliations_status", table_name="live_broker_reconciliations")
    op.drop_index("ix_live_broker_reconciliations_account_id", table_name="live_broker_reconciliations")
    op.drop_index("ix_live_broker_reconciliations_tenant_id", table_name="live_broker_reconciliations")
    op.drop_table("live_broker_reconciliations")

    op.drop_index("ix_live_broker_fills_source", table_name="live_broker_fills")
    op.drop_index("ix_live_broker_fills_account_created", table_name="live_broker_fills")
    op.drop_index("ix_live_broker_fills_filled_at", table_name="live_broker_fills")
    op.drop_index("ix_live_broker_fills_side", table_name="live_broker_fills")
    op.drop_index("ix_live_broker_fills_symbol", table_name="live_broker_fills")
    op.drop_index("ix_live_broker_fills_client_order_id", table_name="live_broker_fills")
    op.drop_index("ix_live_broker_fills_broker_order_id", table_name="live_broker_fills")
    op.drop_index("ix_live_broker_fills_account_id", table_name="live_broker_fills")
    op.drop_index("ix_live_broker_fills_tenant_id", table_name="live_broker_fills")
    op.drop_table("live_broker_fills")

    op.drop_index("ix_live_broker_requests_created_at", table_name="live_broker_requests")
    op.drop_index("ix_live_broker_requests_rate_window", table_name="live_broker_requests")
    op.drop_index("ix_live_broker_requests_client_order_id", table_name="live_broker_requests")
    op.drop_index("ix_live_broker_requests_broker_order_id", table_name="live_broker_requests")
    op.drop_index("ix_live_broker_requests_status", table_name="live_broker_requests")
    op.drop_index("ix_live_broker_requests_account_id", table_name="live_broker_requests")
    op.drop_index("ix_live_broker_requests_adapter", table_name="live_broker_requests")
    op.drop_index("ix_live_broker_requests_action", table_name="live_broker_requests")
    op.drop_index("ix_live_broker_requests_tenant_id", table_name="live_broker_requests")
    op.drop_table("live_broker_requests")
