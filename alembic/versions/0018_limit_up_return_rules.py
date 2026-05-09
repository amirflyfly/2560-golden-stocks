"""Add limit-up return strategy data rules.

Revision ID: 0018_limit_up_return_rules
Revises: 0017_trading_security_type_interval
Create Date: 2026-05-05
"""

from __future__ import annotations

from datetime import date

from alembic import op
import sqlalchemy as sa


revision = "0018_limit_up_return_rules"
down_revision = "0017_trading_security_type_interval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stocks", sa.Column("is_st", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("stocks", sa.Column("board_type", sa.String(length=32), nullable=True))
    op.add_column("stocks", sa.Column("limit_rule_profile", sa.JSON(), nullable=True))
    op.add_column("stocks", sa.Column("is_suspended", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("stocks", sa.Column("is_delisting", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.create_index("ix_stocks_board_type", "stocks", ["board_type"])

    op.create_table(
        "limit_rule_calendar",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("exchange", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("board_type", sa.String(length=32), nullable=False, server_default="main"),
        sa.Column("security_type", sa.String(length=32), nullable=False, server_default="stock"),
        sa.Column("risk_warning", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("limit_up_rate", sa.Numeric(8, 4), nullable=True),
        sa.Column("limit_down_rate", sa.Numeric(8, 4), nullable=True),
        sa.Column("no_limit_first_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("exchange", "board_type", "security_type", "risk_warning", "effective_from", name="uk_limit_rule_calendar_profile_start"),
    )
    op.create_index("ix_limit_rule_calendar_profile", "limit_rule_calendar", ["exchange", "board_type", "security_type", "risk_warning"])
    op.create_index("ix_limit_rule_calendar_effective_from", "limit_rule_calendar", ["effective_from", "effective_to"])
    op.bulk_insert(
        sa.table(
            "limit_rule_calendar",
            sa.column("exchange", sa.String),
            sa.column("board_type", sa.String),
            sa.column("security_type", sa.String),
            sa.column("risk_warning", sa.Boolean),
            sa.column("effective_from", sa.Date),
            sa.column("effective_to", sa.Date),
            sa.column("limit_up_rate", sa.Numeric),
            sa.column("limit_down_rate", sa.Numeric),
            sa.column("no_limit_first_days", sa.Integer),
            sa.column("status", sa.String),
            sa.column("notes", sa.Text),
        ),
        [
            {"exchange": "SH", "board_type": "main", "security_type": "stock", "risk_warning": False, "effective_from": date(1996, 12, 16), "effective_to": None, "limit_up_rate": 0.10, "limit_down_rate": 0.10, "no_limit_first_days": 0, "status": "active", "notes": "沪市主板普通股票默认涨跌幅"},
            {"exchange": "SZ", "board_type": "main", "security_type": "stock", "risk_warning": False, "effective_from": date(1996, 12, 16), "effective_to": None, "limit_up_rate": 0.10, "limit_down_rate": 0.10, "no_limit_first_days": 0, "status": "active", "notes": "深市主板普通股票默认涨跌幅"},
            {"exchange": "SH", "board_type": "star", "security_type": "stock", "risk_warning": False, "effective_from": date(2019, 7, 22), "effective_to": None, "limit_up_rate": 0.20, "limit_down_rate": 0.20, "no_limit_first_days": 5, "status": "active", "notes": "科创板普通股票涨跌幅"},
            {"exchange": "SZ", "board_type": "chinext", "security_type": "stock", "risk_warning": False, "effective_from": date(2020, 8, 24), "effective_to": None, "limit_up_rate": 0.20, "limit_down_rate": 0.20, "no_limit_first_days": 5, "status": "active", "notes": "创业板普通股票涨跌幅"},
            {"exchange": "BJ", "board_type": "bse", "security_type": "stock", "risk_warning": False, "effective_from": date(2021, 11, 15), "effective_to": None, "limit_up_rate": 0.30, "limit_down_rate": 0.30, "no_limit_first_days": 1, "status": "active", "notes": "北交所普通股票涨跌幅"},
            {"exchange": "SH", "board_type": "main", "security_type": "stock", "risk_warning": True, "effective_from": date(1996, 12, 16), "effective_to": date(2026, 7, 5), "limit_up_rate": 0.05, "limit_down_rate": 0.05, "no_limit_first_days": 0, "status": "active", "notes": "沪市主板风险警示股票旧规则"},
            {"exchange": "SZ", "board_type": "main", "security_type": "stock", "risk_warning": True, "effective_from": date(1996, 12, 16), "effective_to": None, "limit_up_rate": 0.05, "limit_down_rate": 0.05, "no_limit_first_days": 0, "status": "active", "notes": "深市主板风险警示股票默认规则"},
            {"exchange": "SH", "board_type": "star", "security_type": "stock", "risk_warning": True, "effective_from": date(2019, 7, 22), "effective_to": None, "limit_up_rate": 0.20, "limit_down_rate": 0.20, "no_limit_first_days": 5, "status": "active", "notes": "科创板风险警示股票涨跌幅"},
            {"exchange": "SZ", "board_type": "chinext", "security_type": "stock", "risk_warning": True, "effective_from": date(2020, 8, 24), "effective_to": None, "limit_up_rate": 0.20, "limit_down_rate": 0.20, "no_limit_first_days": 5, "status": "active", "notes": "创业板风险警示股票涨跌幅"},
            {"exchange": "BJ", "board_type": "bse", "security_type": "stock", "risk_warning": True, "effective_from": date(2021, 11, 15), "effective_to": None, "limit_up_rate": 0.30, "limit_down_rate": 0.30, "no_limit_first_days": 1, "status": "active", "notes": "北交所风险警示股票涨跌幅"},
        ],
    )
    op.execute(
        """INSERT INTO strategies (tenant_id, code, name, category, description, config_json, code_body,
           source_type, lifecycle_status, version, enabled, is_active, sort_order)
           SELECT 1, 'LIMIT_UP_RETURN', '涨停回马枪', '短线策略',
                  '涨停锚点、缩量回踩、支撑不破、放量再攻策略', '{}', '',
                  'builtin', 'deployed', 1, 1, 1, 30
           WHERE NOT EXISTS (SELECT 1 FROM strategies WHERE tenant_id=1 AND code='LIMIT_UP_RETURN')"""
    )


def downgrade() -> None:
    op.execute("DELETE FROM strategies WHERE tenant_id=1 AND code='LIMIT_UP_RETURN'")
    op.drop_index("ix_limit_rule_calendar_effective_from", table_name="limit_rule_calendar")
    op.drop_index("ix_limit_rule_calendar_profile", table_name="limit_rule_calendar")
    op.drop_table("limit_rule_calendar")
    op.drop_index("ix_stocks_board_type", table_name="stocks")
    op.drop_column("stocks", "is_delisting")
    op.drop_column("stocks", "is_suspended")
    op.drop_column("stocks", "limit_rule_profile")
    op.drop_column("stocks", "board_type")
    op.drop_column("stocks", "is_st")
