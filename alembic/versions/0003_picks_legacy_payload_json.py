"""Add legacy payload JSON to picks.

Revision ID: 0003_picks_legacy_payload_json
Revises: 0002_picks_v1_contract_fields
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_picks_legacy_payload_json"
down_revision = "0002_picks_v1_contract_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("picks", sa.Column("legacy_payload_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("picks", "legacy_payload_json")
