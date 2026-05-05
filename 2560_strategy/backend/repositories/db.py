"""Database access helpers.

Step 1 of the web_panel.py split: move sqlite connection + schema + basic query helpers here.

Keep this module dependency-light so web_panel.py can import it safely.
"""

import sqlite3
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / 'data'
DB_PATH = DATA_DIR / 'picks.db'


def _refuse_production_sqlite():
    if any((os.getenv(name) or "").strip().lower() in {"prod", "production"} for name in ("APP_ENV", "FLASK_ENV")):
        raise RuntimeError("Legacy SQLite repository helper is disabled in production")


def db_conn():
    _refuse_production_sqlite()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema():
    """Ensure DB schema exists and apply safe additive migrations."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = db_conn()
    try:
        cur = conn.cursor()

        cur.execute(
            """CREATE TABLE IF NOT EXISTS picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pick_date TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT,
                pick_price REAL,
                signal TEXT,
                ma25 REAL,
                vol_ratio REAL,
                source TEXT DEFAULT '2560',
                source_channel TEXT DEFAULT 'system',
                reason_tag TEXT DEFAULT '',
                note TEXT DEFAULT '',
                review_status TEXT DEFAULT '',
                review_comment TEXT DEFAULT '',
                content_title TEXT DEFAULT '',
                content_ref TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(pick_date, code, source)
            )"""
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_picks_code ON picks(code)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_picks_date ON picks(pick_date)')

        cols = [r['name'] for r in cur.execute("PRAGMA table_info(picks)").fetchall()]
        alter_sqls = []
        if 'archived' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN archived INTEGER DEFAULT 0")
        if 'result_grade' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN result_grade TEXT DEFAULT '待定'")
        if 'inquiry_count' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN inquiry_count INTEGER DEFAULT 0")
        if 'deal_status' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN deal_status TEXT DEFAULT '未成交'")
        if 'secondary_spread' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN secondary_spread TEXT DEFAULT '否'")
        if 'last_price' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN last_price REAL DEFAULT NULL")
        if 'return_pct' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN return_pct REAL DEFAULT NULL")
        if 'quote_time' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN quote_time TEXT DEFAULT ''")
        if 'max_return_pct' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN max_return_pct REAL DEFAULT NULL")
        if 'drawdown_pct' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN drawdown_pct REAL DEFAULT NULL")
        if 'holding_days' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN holding_days INTEGER DEFAULT NULL")
        if 'strategy_name' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN strategy_name TEXT DEFAULT '2560'")
        if 'first_board_time' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN first_board_time TEXT DEFAULT ''")
        if 'theme_reason' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN theme_reason TEXT DEFAULT ''")
        if 'second_board_expectation' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN second_board_expectation TEXT DEFAULT ''")
        if 'second_board_score' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN second_board_score INTEGER DEFAULT 0")
        if 'prediction_reason' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN prediction_reason TEXT DEFAULT ''")
        if 'watch_flag' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN watch_flag INTEGER DEFAULT 0")
        if 'validation_result' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN validation_result TEXT DEFAULT ''")
        if 'validation_note' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN validation_note TEXT DEFAULT ''")
        if 'validated_at' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN validated_at TEXT DEFAULT ''")
        if 'data_quality' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN data_quality TEXT DEFAULT ''")
        if 'market_data_source' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN market_data_source TEXT DEFAULT ''")
        if 'fallback_used' not in cols:
            alter_sqls.append("ALTER TABLE picks ADD COLUMN fallback_used INTEGER DEFAULT 0")
        for sql in alter_sqls:
            cur.execute(sql)

        cur.execute(
            """CREATE TABLE IF NOT EXISTS operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                target_ids TEXT DEFAULT '',
                detail TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        log_cols = [r['name'] for r in cur.execute("PRAGMA table_info(operation_logs)").fetchall()]
        log_alters = []
        if 'user_id' not in log_cols:
            log_alters.append("ALTER TABLE operation_logs ADD COLUMN user_id INTEGER DEFAULT NULL")
        if 'username' not in log_cols:
            log_alters.append("ALTER TABLE operation_logs ADD COLUMN username TEXT DEFAULT ''")
        if 'ip' not in log_cols:
            log_alters.append("ALTER TABLE operation_logs ADD COLUMN ip TEXT DEFAULT ''")
        if 'user_agent' not in log_cols:
            log_alters.append("ALTER TABLE operation_logs ADD COLUMN user_agent TEXT DEFAULT ''")
        for sql in log_alters:
            try:
                cur.execute(sql)
            except sqlite3.OperationalError:
                pass

        cur.execute(
            """CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT NULL,
                username TEXT DEFAULT '',
                tenant_id INTEGER DEFAULT NULL,
                action TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT DEFAULT '',
                result TEXT NOT NULL DEFAULT 'success',
                ip TEXT DEFAULT '',
                user_agent TEXT DEFAULT '',
                detail_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_created ON audit_logs(tenant_id, created_at)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_audit_logs_result ON audit_logs(result)')

        cur.execute(
            """CREATE TABLE IF NOT EXISTS saved_filters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                query_string TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS ui_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                is_active INTEGER NOT NULL DEFAULT 1,
                points INTEGER DEFAULT 0,
                last_checkin TEXT DEFAULT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')

        user_cols = [r['name'] for r in cur.execute("PRAGMA table_info(users)").fetchall()]
        user_alters = []
        if 'points' not in user_cols:
            user_alters.append("ALTER TABLE users ADD COLUMN points INTEGER DEFAULT 0")
        if 'last_checkin' not in user_cols:
            user_alters.append("ALTER TABLE users ADD COLUMN last_checkin TEXT DEFAULT NULL")
        for sql in user_alters:
            try:
                cur.execute(sql)
            except sqlite3.OperationalError:
                pass

        cur.execute(
            """CREATE TABLE IF NOT EXISTS tenants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                plan TEXT NOT NULL DEFAULT 'default',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status)')
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_tenants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                tenant_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'editor',
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, tenant_id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(tenant_id) REFERENCES tenants(id)
            )"""
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_user_tenants_user_id ON user_tenants(user_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_user_tenants_tenant_id ON user_tenants(tenant_id)')
        cur.execute("INSERT OR IGNORE INTO tenants (id, code, name, status, plan) VALUES (1, 'default', '默认租户', 'active', 'default')")
        cur.execute(
            """INSERT OR IGNORE INTO user_tenants (user_id, tenant_id, role, is_default)
            SELECT id, 1, role, 1 FROM users WHERE is_active=1"""
        )

        cur.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_token TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT NOT NULL,
                last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )"""
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)')

        cur.execute(
            """CREATE TABLE IF NOT EXISTS strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                category TEXT DEFAULT '',
                description TEXT DEFAULT '',
                config_json TEXT DEFAULT '{}',
                code_body TEXT DEFAULT '',
                source_type TEXT DEFAULT 'builtin',
                lifecycle_status TEXT DEFAULT 'deployed',
                version INTEGER DEFAULT 1,
                enabled INTEGER DEFAULT 1,
                is_active INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                deployed_at TEXT DEFAULT NULL,
                last_test_status TEXT DEFAULT '',
                last_test_message TEXT DEFAULT '',
                last_test_at TEXT DEFAULT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        strategy_cols = [r['name'] for r in cur.execute("PRAGMA table_info(strategies)").fetchall()]
        strategy_alters = []
        for column_name, ddl in [
            ("config_json", "ALTER TABLE strategies ADD COLUMN config_json TEXT DEFAULT '{}'"),
            ("code_body", "ALTER TABLE strategies ADD COLUMN code_body TEXT DEFAULT ''"),
            ("source_type", "ALTER TABLE strategies ADD COLUMN source_type TEXT DEFAULT 'builtin'"),
            ("lifecycle_status", "ALTER TABLE strategies ADD COLUMN lifecycle_status TEXT DEFAULT 'deployed'"),
            ("version", "ALTER TABLE strategies ADD COLUMN version INTEGER DEFAULT 1"),
            ("enabled", "ALTER TABLE strategies ADD COLUMN enabled INTEGER DEFAULT 1"),
            ("deployed_at", "ALTER TABLE strategies ADD COLUMN deployed_at TEXT DEFAULT NULL"),
            ("last_test_status", "ALTER TABLE strategies ADD COLUMN last_test_status TEXT DEFAULT ''"),
            ("last_test_message", "ALTER TABLE strategies ADD COLUMN last_test_message TEXT DEFAULT ''"),
            ("last_test_at", "ALTER TABLE strategies ADD COLUMN last_test_at TEXT DEFAULT NULL"),
        ]:
            if column_name not in strategy_cols:
                strategy_alters.append(ddl)
        for sql in strategy_alters:
            cur.execute(sql)
        if "enabled" in [*strategy_cols, "enabled"]:
            cur.execute("UPDATE strategies SET enabled = COALESCE(enabled, is_active, 1)")
        cur.execute('CREATE INDEX IF NOT EXISTS idx_strategies_active ON strategies(is_active)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_strategies_sort ON strategies(sort_order)')

        cur.execute(
            """CREATE TABLE IF NOT EXISTS strategy_pools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_code TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                add_date TEXT NOT NULL,
                add_price REAL,
                reason TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(strategy_code, code)
            )"""
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_strategy_pools_strategy ON strategy_pools(strategy_code)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_strategy_pools_status ON strategy_pools(status)')

        cur.execute(
            """CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_code TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                total_trades INTEGER,
                win_rate REAL,
                avg_return REAL,
                max_return REAL,
                max_drawdown REAL,
                sharpe_ratio REAL,
                total_return REAL,
                backtest_date TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_backtest_results_strategy ON backtest_results(strategy_code)')

        cur.execute(
            """CREATE TABLE IF NOT EXISTS research_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pick_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                pick_date TEXT NOT NULL,
                analysis_date TEXT NOT NULL,
                technical_score REAL DEFAULT 0,
                momentum_score REAL DEFAULT 0,
                risk_score REAL DEFAULT 0,
                liquidity_score REAL DEFAULT 0,
                timing_score REAL DEFAULT 0,
                total_score REAL DEFAULT 0,
                research_summary TEXT DEFAULT '',
                action_suggestion TEXT DEFAULT '',
                risk_warning TEXT DEFAULT '',
                data_snapshot TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(pick_id, analysis_date)
            )"""
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_research_reports_pick_id ON research_reports(pick_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_research_reports_analysis_date ON research_reports(analysis_date)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_research_reports_code_date ON research_reports(code, analysis_date)')

        default_strategies = [
            ('2560', '2560战法', '趋势策略', '25日均线+60日均量选股策略', 1, 10),
            ('first_limit_up', '首板涨停', '打板策略', '首板涨停识别与次日预期跟踪策略', 1, 20),
            ('LIMIT_UP_RETURN', '涨停回马枪', '短线策略', '涨停锚点、缩量回踩、支撑不破、放量再攻策略', 1, 30),
        ]
        cur.executemany(
            'INSERT OR IGNORE INTO strategies (code, name, category, description, is_active, sort_order) VALUES (?, ?, ?, ?, ?, ?)',
            default_strategies,
        )

        cur.execute(
            """CREATE TABLE IF NOT EXISTS stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL UNIQUE,
                exchange TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                market TEXT DEFAULT 'A',
                security_type TEXT NOT NULL DEFAULT 'stock',
                industry TEXT DEFAULT NULL,
                listing_date TEXT DEFAULT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                is_st INTEGER NOT NULL DEFAULT 0,
                board_type TEXT DEFAULT '',
                limit_rule_profile TEXT DEFAULT '{}',
                is_suspended INTEGER NOT NULL DEFAULT 0,
                is_delisting INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_stocks_exchange ON stocks(exchange)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_stocks_name ON stocks(name)')
        stock_cols = [r['name'] for r in cur.execute("PRAGMA table_info(stocks)").fetchall()]
        if 'security_type' not in stock_cols:
            cur.execute("ALTER TABLE stocks ADD COLUMN security_type TEXT NOT NULL DEFAULT 'stock'")
        if 'is_st' not in stock_cols:
            cur.execute("ALTER TABLE stocks ADD COLUMN is_st INTEGER NOT NULL DEFAULT 0")
        if 'board_type' not in stock_cols:
            cur.execute("ALTER TABLE stocks ADD COLUMN board_type TEXT DEFAULT ''")
        if 'limit_rule_profile' not in stock_cols:
            cur.execute("ALTER TABLE stocks ADD COLUMN limit_rule_profile TEXT DEFAULT '{}'")
        if 'is_suspended' not in stock_cols:
            cur.execute("ALTER TABLE stocks ADD COLUMN is_suspended INTEGER NOT NULL DEFAULT 0")
        if 'is_delisting' not in stock_cols:
            cur.execute("ALTER TABLE stocks ADD COLUMN is_delisting INTEGER NOT NULL DEFAULT 0")
        cur.execute('CREATE INDEX IF NOT EXISTS idx_stocks_security_type ON stocks(security_type)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_stocks_board_type ON stocks(board_type)')

        cur.execute(
            """CREATE TABLE IF NOT EXISTS limit_rule_calendar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL DEFAULT '',
                board_type TEXT NOT NULL DEFAULT 'main',
                security_type TEXT NOT NULL DEFAULT 'stock',
                risk_warning INTEGER NOT NULL DEFAULT 0,
                effective_from TEXT NOT NULL,
                effective_to TEXT DEFAULT NULL,
                limit_up_rate REAL DEFAULT NULL,
                limit_down_rate REAL DEFAULT NULL,
                no_limit_first_days INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(exchange, board_type, security_type, risk_warning, effective_from)
            )"""
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_limit_rule_calendar_profile ON limit_rule_calendar(exchange, board_type, security_type, risk_warning)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_limit_rule_calendar_effective ON limit_rule_calendar(effective_from, effective_to)')
        default_limit_rules = [
            ('SH', 'main', 'stock', 0, '1996-12-16', None, 0.10, 0.10, 0, 'active', '沪市主板普通股票默认涨跌幅'),
            ('SZ', 'main', 'stock', 0, '1996-12-16', None, 0.10, 0.10, 0, 'active', '深市主板普通股票默认涨跌幅'),
            ('SH', 'star', 'stock', 0, '2019-07-22', None, 0.20, 0.20, 5, 'active', '科创板普通股票涨跌幅'),
            ('SZ', 'chinext', 'stock', 0, '2020-08-24', None, 0.20, 0.20, 5, 'active', '创业板普通股票涨跌幅'),
            ('BJ', 'bse', 'stock', 0, '2021-11-15', None, 0.30, 0.30, 1, 'active', '北交所普通股票涨跌幅'),
            ('SH', 'main', 'stock', 1, '1996-12-16', '2026-07-05', 0.05, 0.05, 0, 'active', '沪市主板风险警示股票旧规则'),
            ('SZ', 'main', 'stock', 1, '1996-12-16', None, 0.05, 0.05, 0, 'active', '深市主板风险警示股票默认规则'),
            ('SH', 'star', 'stock', 1, '2019-07-22', None, 0.20, 0.20, 5, 'active', '科创板风险警示股票涨跌幅'),
            ('SZ', 'chinext', 'stock', 1, '2020-08-24', None, 0.20, 0.20, 5, 'active', '创业板风险警示股票涨跌幅'),
            ('BJ', 'bse', 'stock', 1, '2021-11-15', None, 0.30, 0.30, 1, 'active', '北交所风险警示股票涨跌幅'),
        ]
        cur.executemany(
            """INSERT OR IGNORE INTO limit_rule_calendar
            (exchange, board_type, security_type, risk_warning, effective_from, effective_to,
             limit_up_rate, limit_down_rate, no_limit_first_days, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            default_limit_rules,
        )

        cur.execute(
            """CREATE TABLE IF NOT EXISTS stock_daily_bars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                trade_time TEXT NOT NULL DEFAULT '',
                interval TEXT NOT NULL DEFAULT '1d',
                adjust TEXT NOT NULL DEFAULT 'qfq',
                open REAL DEFAULT NULL,
                high REAL DEFAULT NULL,
                low REAL DEFAULT NULL,
                close REAL DEFAULT NULL,
                volume INTEGER DEFAULT NULL,
                amount REAL DEFAULT NULL,
                turnover_rate REAL DEFAULT NULL,
                source TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, trade_date, trade_time, interval, source, adjust)
            )"""
        )
        bar_cols = [r['name'] for r in cur.execute("PRAGMA table_info(stock_daily_bars)").fetchall()]
        if 'adjust' not in bar_cols:
            cur.execute("ALTER TABLE stock_daily_bars ADD COLUMN adjust TEXT NOT NULL DEFAULT 'qfq'")
        if 'trade_time' not in bar_cols:
            cur.execute("ALTER TABLE stock_daily_bars ADD COLUMN trade_time TEXT NOT NULL DEFAULT ''")
            cur.execute("UPDATE stock_daily_bars SET trade_time = trade_date || 'T00:00:00' WHERE trade_time='' OR trade_time IS NULL")
        if 'interval' not in bar_cols:
            cur.execute("ALTER TABLE stock_daily_bars ADD COLUMN interval TEXT NOT NULL DEFAULT '1d'")
        unique_sets = []
        for index_row in cur.execute("PRAGMA index_list(stock_daily_bars)").fetchall():
            if int(index_row['unique'] or 0) != 1:
                continue
            cols = [info['name'] for info in cur.execute(f"PRAGMA index_info({index_row['name']})").fetchall()]
            unique_sets.append(cols)
        expected_unique = ['symbol', 'trade_date', 'trade_time', 'interval', 'source', 'adjust']
        if expected_unique not in unique_sets:
            cur.execute("ALTER TABLE stock_daily_bars RENAME TO stock_daily_bars_legacy")
            cur.execute(
                """CREATE TABLE stock_daily_bars (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    trade_time TEXT NOT NULL DEFAULT '',
                    interval TEXT NOT NULL DEFAULT '1d',
                    adjust TEXT NOT NULL DEFAULT 'qfq',
                    open REAL DEFAULT NULL,
                    high REAL DEFAULT NULL,
                    low REAL DEFAULT NULL,
                    close REAL DEFAULT NULL,
                    volume INTEGER DEFAULT NULL,
                    amount REAL DEFAULT NULL,
                    turnover_rate REAL DEFAULT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, trade_date, trade_time, interval, source, adjust)
                )"""
            )
            cur.execute(
                """INSERT OR REPLACE INTO stock_daily_bars
                (id, symbol, trade_date, trade_time, interval, adjust, open, high, low, close, volume, amount, turnover_rate, source, created_at, updated_at)
                SELECT id, symbol, trade_date, COALESCE(NULLIF(trade_time, ''), trade_date || 'T00:00:00'), COALESCE(NULLIF(interval, ''), '1d'), COALESCE(NULLIF(adjust, ''), 'none'), open, high, low, close,
                       volume, amount, turnover_rate, source, created_at, updated_at
                FROM stock_daily_bars_legacy"""
            )
            cur.execute("DROP TABLE stock_daily_bars_legacy")
        cur.execute('CREATE INDEX IF NOT EXISTS idx_stock_daily_bars_symbol ON stock_daily_bars(symbol)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_stock_daily_bars_trade_date ON stock_daily_bars(trade_date)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_stock_daily_bars_trade_time ON stock_daily_bars(trade_time)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_stock_daily_bars_interval ON stock_daily_bars(interval)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_stock_daily_bars_adjust ON stock_daily_bars(adjust)')

        cur.execute(
            """CREATE TABLE IF NOT EXISTS stock_price_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL UNIQUE,
                trade_time TEXT DEFAULT NULL,
                last_price REAL DEFAULT NULL,
                open REAL DEFAULT NULL,
                high REAL DEFAULT NULL,
                low REAL DEFAULT NULL,
                prev_close REAL DEFAULT NULL,
                volume INTEGER DEFAULT NULL,
                amount REAL DEFAULT NULL,
                bid_price REAL DEFAULT NULL,
                ask_price REAL DEFAULT NULL,
                source TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_stock_price_snapshots_trade_time ON stock_price_snapshots(trade_time)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_stock_price_snapshots_source ON stock_price_snapshots(source)')

        cur.execute(
            """CREATE TABLE IF NOT EXISTS market_sync_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                symbol TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'auto',
                adjust TEXT NOT NULL DEFAULT 'qfq',
                interval TEXT NOT NULL DEFAULT '1d',
                coverage_start_date TEXT DEFAULT NULL,
                coverage_end_date TEXT DEFAULT NULL,
                last_success_trade_date TEXT DEFAULT NULL,
                last_synced_at TEXT DEFAULT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                error_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant_id, symbol, source, adjust, interval)
            )"""
        )
        state_cols = [r['name'] for r in cur.execute("PRAGMA table_info(market_sync_states)").fetchall()]
        if 'interval' not in state_cols:
            cur.execute("ALTER TABLE market_sync_states ADD COLUMN interval TEXT NOT NULL DEFAULT '1d'")
        state_unique_sets = []
        for index_row in cur.execute("PRAGMA index_list(market_sync_states)").fetchall():
            if int(index_row['unique'] or 0) != 1:
                continue
            cols = [info['name'] for info in cur.execute(f"PRAGMA index_info({index_row['name']})").fetchall()]
            state_unique_sets.append(cols)
        expected_state_unique = ['tenant_id', 'symbol', 'source', 'adjust', 'interval']
        if expected_state_unique not in state_unique_sets:
            cur.execute("ALTER TABLE market_sync_states RENAME TO market_sync_states_legacy")
            cur.execute(
                """CREATE TABLE market_sync_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id INTEGER NOT NULL DEFAULT 1,
                    symbol TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'auto',
                    adjust TEXT NOT NULL DEFAULT 'qfq',
                    interval TEXT NOT NULL DEFAULT '1d',
                    coverage_start_date TEXT DEFAULT NULL,
                    coverage_end_date TEXT DEFAULT NULL,
                    last_success_trade_date TEXT DEFAULT NULL,
                    last_synced_at TEXT DEFAULT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    error_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(tenant_id, symbol, source, adjust, interval)
                )"""
            )
            cur.execute(
                """INSERT OR REPLACE INTO market_sync_states
                (id, tenant_id, symbol, source, adjust, interval, coverage_start_date, coverage_end_date,
                 last_success_trade_date, last_synced_at, status, error_count, last_error, created_at, updated_at)
                SELECT id, tenant_id, symbol, source, adjust, COALESCE(NULLIF(interval, ''), '1d'), coverage_start_date,
                       coverage_end_date, last_success_trade_date, last_synced_at, status, error_count, last_error,
                       created_at, updated_at
                FROM market_sync_states_legacy"""
            )
            cur.execute("DROP TABLE market_sync_states_legacy")
        cur.execute('CREATE INDEX IF NOT EXISTS idx_market_sync_states_symbol ON market_sync_states(symbol)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_market_sync_states_status ON market_sync_states(status)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_market_sync_states_coverage_end ON market_sync_states(coverage_end_date)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_market_sync_states_interval ON market_sync_states(interval)')

        cur.execute(
            """CREATE TABLE IF NOT EXISTS market_sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                run_no TEXT NOT NULL UNIQUE,
                mode TEXT NOT NULL DEFAULT 'incremental',
                source TEXT NOT NULL DEFAULT 'auto',
                adjust TEXT NOT NULL DEFAULT 'qfq',
                interval TEXT NOT NULL DEFAULT '1d',
                status TEXT NOT NULL DEFAULT 'running',
                requested_symbols INTEGER NOT NULL DEFAULT 0,
                synced_symbols INTEGER NOT NULL DEFAULT 0,
                failed_symbols INTEGER NOT NULL DEFAULT 0,
                persisted_bars INTEGER NOT NULL DEFAULT 0,
                started_at TEXT DEFAULT NULL,
                finished_at TEXT DEFAULT NULL,
                payload_json TEXT DEFAULT '{}',
                result_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        run_cols = [r['name'] for r in cur.execute("PRAGMA table_info(market_sync_runs)").fetchall()]
        if 'interval' not in run_cols:
            cur.execute("ALTER TABLE market_sync_runs ADD COLUMN interval TEXT NOT NULL DEFAULT '1d'")
        cur.execute('CREATE INDEX IF NOT EXISTS idx_market_sync_runs_tenant_created ON market_sync_runs(tenant_id, created_at)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_market_sync_runs_status ON market_sync_runs(status)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_market_sync_runs_interval ON market_sync_runs(interval)')
        cur.execute(
            """CREATE TABLE IF NOT EXISTS market_sync_run_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                run_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                start_date TEXT DEFAULT NULL,
                end_date TEXT DEFAULT NULL,
                bars INTEGER NOT NULL DEFAULT 0,
                persisted_bars INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'auto',
                adjust TEXT NOT NULL DEFAULT 'qfq',
                interval TEXT NOT NULL DEFAULT '1d',
                error TEXT DEFAULT '',
                started_at TEXT DEFAULT NULL,
                finished_at TEXT DEFAULT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        run_item_cols = [r['name'] for r in cur.execute("PRAGMA table_info(market_sync_run_items)").fetchall()]
        if 'interval' not in run_item_cols:
            cur.execute("ALTER TABLE market_sync_run_items ADD COLUMN interval TEXT NOT NULL DEFAULT '1d'")
        cur.execute('CREATE INDEX IF NOT EXISTS idx_market_sync_run_items_run ON market_sync_run_items(run_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_market_sync_run_items_symbol ON market_sync_run_items(symbol)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_market_sync_run_items_status ON market_sync_run_items(status)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_market_sync_run_items_interval ON market_sync_run_items(interval)')

        cur.execute(
            """CREATE TABLE IF NOT EXISTS trade_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                account_id INTEGER DEFAULT NULL,
                strategy_id INTEGER DEFAULT NULL,
                strategy_code TEXT NOT NULL,
                symbol TEXT NOT NULL,
                security_type TEXT NOT NULL DEFAULT 'stock',
                bar_interval TEXT NOT NULL DEFAULT '1d',
                signal_date TEXT DEFAULT NULL,
                signal_type TEXT NOT NULL DEFAULT 'BUY',
                score REAL DEFAULT NULL,
                price_ref REAL DEFAULT NULL,
                data_quality TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                source_hash TEXT NOT NULL,
                payload_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant_id, source_hash)
            )"""
        )
        signal_cols = [r['name'] for r in cur.execute("PRAGMA table_info(trade_signals)").fetchall()]
        if 'security_type' not in signal_cols:
            cur.execute("ALTER TABLE trade_signals ADD COLUMN security_type TEXT NOT NULL DEFAULT 'stock'")
        if 'bar_interval' not in signal_cols:
            cur.execute("ALTER TABLE trade_signals ADD COLUMN bar_interval TEXT NOT NULL DEFAULT '1d'")
        cur.execute('CREATE INDEX IF NOT EXISTS idx_trade_signals_account ON trade_signals(account_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_trade_signals_strategy ON trade_signals(strategy_code)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_trade_signals_symbol ON trade_signals(symbol)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_trade_signals_security_type ON trade_signals(security_type)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_trade_signals_bar_interval ON trade_signals(bar_interval)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_trade_signals_date ON trade_signals(signal_date)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_trade_signals_status ON trade_signals(status)')

        cur.execute(
            """CREATE TABLE IF NOT EXISTS paper_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                name TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'paper',
                broker_type TEXT NOT NULL DEFAULT 'paper',
                status TEXT NOT NULL DEFAULT 'active',
                currency TEXT NOT NULL DEFAULT 'CNY',
                initial_cash REAL NOT NULL DEFAULT 1000000,
                cash REAL NOT NULL DEFAULT 1000000,
                config_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant_id, name)
            )"""
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_paper_accounts_tenant ON paper_accounts(tenant_id)')
        cur.execute(
            """CREATE TABLE IF NOT EXISTS paper_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                account_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                security_type TEXT NOT NULL DEFAULT 'stock',
                bar_interval TEXT NOT NULL DEFAULT '1d',
                quantity INTEGER NOT NULL DEFAULT 0,
                avg_cost REAL NOT NULL DEFAULT 0,
                market_price REAL DEFAULT NULL,
                market_value REAL NOT NULL DEFAULT 0,
                realized_pnl REAL NOT NULL DEFAULT 0,
                unrealized_pnl REAL NOT NULL DEFAULT 0,
                opened_at TEXT DEFAULT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant_id, account_id, symbol)
            )"""
        )
        position_cols = [r['name'] for r in cur.execute("PRAGMA table_info(paper_positions)").fetchall()]
        if 'security_type' not in position_cols:
            cur.execute("ALTER TABLE paper_positions ADD COLUMN security_type TEXT NOT NULL DEFAULT 'stock'")
        if 'bar_interval' not in position_cols:
            cur.execute("ALTER TABLE paper_positions ADD COLUMN bar_interval TEXT NOT NULL DEFAULT '1d'")
        cur.execute('CREATE INDEX IF NOT EXISTS idx_paper_positions_account ON paper_positions(account_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_paper_positions_symbol ON paper_positions(symbol)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_paper_positions_security_type ON paper_positions(security_type)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_paper_positions_bar_interval ON paper_positions(bar_interval)')
        cur.execute(
            """CREATE TABLE IF NOT EXISTS paper_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                account_id INTEGER NOT NULL,
                strategy_id INTEGER DEFAULT NULL,
                strategy_code TEXT DEFAULT '',
                symbol TEXT NOT NULL,
                security_type TEXT NOT NULL DEFAULT 'stock',
                bar_interval TEXT NOT NULL DEFAULT '1d',
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                order_type TEXT NOT NULL DEFAULT 'market',
                requested_price REAL DEFAULT NULL,
                limit_price REAL DEFAULT NULL,
                status TEXT NOT NULL DEFAULT 'filled',
                filled_quantity INTEGER NOT NULL DEFAULT 0,
                avg_fill_price REAL DEFAULT NULL,
                idempotency_key TEXT NOT NULL,
                source_signal_hash TEXT DEFAULT '',
                reason TEXT DEFAULT '',
                metadata_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant_id, idempotency_key)
            )"""
        )
        order_cols = [r['name'] for r in cur.execute("PRAGMA table_info(paper_orders)").fetchall()]
        if 'security_type' not in order_cols:
            cur.execute("ALTER TABLE paper_orders ADD COLUMN security_type TEXT NOT NULL DEFAULT 'stock'")
        if 'bar_interval' not in order_cols:
            cur.execute("ALTER TABLE paper_orders ADD COLUMN bar_interval TEXT NOT NULL DEFAULT '1d'")
        cur.execute('CREATE INDEX IF NOT EXISTS idx_paper_orders_account ON paper_orders(account_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_paper_orders_symbol ON paper_orders(symbol)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_paper_orders_security_type ON paper_orders(security_type)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_paper_orders_bar_interval ON paper_orders(bar_interval)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_paper_orders_status ON paper_orders(status)')
        cur.execute(
            """CREATE TABLE IF NOT EXISTS paper_fills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                account_id INTEGER NOT NULL,
                order_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                security_type TEXT NOT NULL DEFAULT 'stock',
                bar_interval TEXT NOT NULL DEFAULT '1d',
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                amount REAL NOT NULL,
                fee REAL NOT NULL DEFAULT 0,
                filled_at TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        fill_cols = [r['name'] for r in cur.execute("PRAGMA table_info(paper_fills)").fetchall()]
        if 'security_type' not in fill_cols:
            cur.execute("ALTER TABLE paper_fills ADD COLUMN security_type TEXT NOT NULL DEFAULT 'stock'")
        if 'bar_interval' not in fill_cols:
            cur.execute("ALTER TABLE paper_fills ADD COLUMN bar_interval TEXT NOT NULL DEFAULT '1d'")
        cur.execute('CREATE INDEX IF NOT EXISTS idx_paper_fills_account ON paper_fills(account_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_paper_fills_order ON paper_fills(order_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_paper_fills_symbol ON paper_fills(symbol)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_paper_fills_security_type ON paper_fills(security_type)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_paper_fills_bar_interval ON paper_fills(bar_interval)')

        conn.commit()
    finally:
        conn.close()


def q(sql, params=()):
    conn = db_conn()
    try:
        cur = conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def q1(sql, params=()):
    conn = db_conn()
    try:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def execute(sql, params=()):
    conn = db_conn()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def execute_many(sql, seq_of_params):
    conn = db_conn()
    try:
        cur = conn.executemany(sql, seq_of_params)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
