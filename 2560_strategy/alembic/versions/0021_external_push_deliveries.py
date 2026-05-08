"""Add external push delivery audit records.

Revision ID: 0021_external_push_deliveries
Revises: 0020_live_broker_boundary
Create Date: 2026-05-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0021_external_push_deliveries"
down_revision = "0020_live_broker_boundary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_push_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("delivery_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("task_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("channel_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("channel_type", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("notification_summary", sa.JSON(), nullable=True),
        sa.Column("notification_payload", sa.JSON(), nullable=True),
        sa.Column("queued_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("failed_at", sa.DateTime(), nullable=True),
        sa.Column("skipped_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("tenant_id", "delivery_key", name="uk_external_push_deliveries_key"),
    )
    op.create_index("ix_external_push_deliveries_tenant_id", "external_push_deliveries", ["tenant_id"])
    op.create_index("ix_external_push_deliveries_status", "external_push_deliveries", ["status"])
    op.create_index("ix_external_push_deliveries_task_id", "external_push_deliveries", ["task_id"])
    op.create_index("ix_external_push_deliveries_channel_id", "external_push_deliveries", ["channel_id"])
    op.create_index("ix_external_push_deliveries_channel_type", "external_push_deliveries", ["channel_type"])
    op.create_index("ix_external_push_deliveries_tenant_created", "external_push_deliveries", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_external_push_deliveries_tenant_created", table_name="external_push_deliveries")
    op.drop_index("ix_external_push_deliveries_channel_type", table_name="external_push_deliveries")
    op.drop_index("ix_external_push_deliveries_channel_id", table_name="external_push_deliveries")
    op.drop_index("ix_external_push_deliveries_task_id", table_name="external_push_deliveries")
    op.drop_index("ix_external_push_deliveries_status", table_name="external_push_deliveries")
    op.drop_index("ix_external_push_deliveries_tenant_id", table_name="external_push_deliveries")
    op.drop_table("external_push_deliveries")
