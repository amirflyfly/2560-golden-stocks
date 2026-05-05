"""Add MySQL legacy operation logs table.

Revision ID: 0007_operation_logs
Revises: 0006_ui_settings_saved_filters
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007_operation_logs"
down_revision = "0006_ui_settings_saved_filters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operation_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target_ids", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("detail", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("ip", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operation_logs_created_at", "operation_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_operation_logs_created_at", table_name="operation_logs")
    op.drop_table("operation_logs")
