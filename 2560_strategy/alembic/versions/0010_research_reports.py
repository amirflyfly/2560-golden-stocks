"""Add MySQL legacy research reports table.

Revision ID: 0010_research_reports
Revises: 0009_strategy_legacy_fields
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010_research_reports"
down_revision = "0009_strategy_legacy_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pick_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("pick_date", sa.String(length=16), nullable=False),
        sa.Column("analysis_date", sa.String(length=16), nullable=False),
        sa.Column("technical_score", sa.Numeric(12, 4), nullable=True),
        sa.Column("momentum_score", sa.Numeric(12, 4), nullable=True),
        sa.Column("risk_score", sa.Numeric(12, 4), nullable=True),
        sa.Column("liquidity_score", sa.Numeric(12, 4), nullable=True),
        sa.Column("timing_score", sa.Numeric(12, 4), nullable=True),
        sa.Column("total_score", sa.Numeric(12, 4), nullable=True),
        sa.Column("research_summary", sa.Text(), nullable=False),
        sa.Column("action_suggestion", sa.String(length=128), nullable=False),
        sa.Column("risk_warning", sa.Text(), nullable=False),
        sa.Column("data_snapshot", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pick_id", "analysis_date", name="uk_research_reports_pick_analysis"),
    )
    op.create_index("ix_research_reports_pick_id", "research_reports", ["pick_id"])
    op.create_index("ix_research_reports_analysis_date", "research_reports", ["analysis_date"])
    op.create_index("ix_research_reports_code_date", "research_reports", ["code", "analysis_date"])


def downgrade() -> None:
    op.drop_index("ix_research_reports_code_date", table_name="research_reports")
    op.drop_index("ix_research_reports_analysis_date", table_name="research_reports")
    op.drop_index("ix_research_reports_pick_id", table_name="research_reports")
    op.drop_table("research_reports")
