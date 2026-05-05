"""Add MySQL UI settings and saved filters tables.

Revision ID: 0006_ui_settings_saved_filters
Revises: 0005_audit_logs
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006_ui_settings_saved_filters"
down_revision = "0005_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_filters",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("query_string", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_saved_filters_created_at", "saved_filters", ["created_at"])

    op.create_table(
        "ui_settings",
        sa.Column("setting_key", sa.String(length=128), nullable=False),
        sa.Column("setting_value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("setting_key"),
    )


def downgrade() -> None:
    op.drop_table("ui_settings")
    op.drop_index("ix_saved_filters_created_at", table_name="saved_filters")
    op.drop_table("saved_filters")
