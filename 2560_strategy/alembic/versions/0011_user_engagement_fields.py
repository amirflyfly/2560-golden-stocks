"""Add MySQL user engagement fields.

Revision ID: 0011_user_engagement_fields
Revises: 0010_research_reports
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0011_user_engagement_fields"
down_revision = "0010_research_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("points", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("last_checkin", sa.String(length=16), nullable=True))
    op.alter_column("users", "points", server_default=None, existing_type=sa.Integer())


def downgrade() -> None:
    op.drop_column("users", "last_checkin")
    op.drop_column("users", "points")
