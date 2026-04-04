"""Database access helpers.

Step 1 of the web_panel.py split: move sqlite connection + schema + basic query helpers here.

Keep this module dependency-light so web_panel.py can import it safely.
"""

import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]  # .../2560_strategy/
DATA_DIR = BASE_DIR / 'data'
DB_PATH = DATA_DIR / 'picks.db'


def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema():
    """Ensure DB schema exists and apply safe additive migrations.

    The upstream project also ships `init_tracker_db.py` which initializes the base `picks`
    table. To make `web_panel.py` runnable on a fresh deployment, we create the base table
    here as well (safe to run repeatedly).
    """

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = db_conn()
    try:
        cur = conn.cursor()

        # Base table
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
        # operation_logs: add user context columns if missing
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
        
        # Add points and last_checkin columns to users table if missing
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

        # Strategies table for multi-strategy support
        cur.execute(
            """CREATE TABLE IF NOT EXISTS strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                category TEXT DEFAULT '',
                description TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_strategies_active ON strategies(is_active)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_strategies_sort ON strategies(sort_order)')

        # Strategy pools table
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

        # Backtest results table
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

        # Insert default strategies if empty
        cur.execute("SELECT COUNT(*) as cnt FROM strategies")
        if cur.fetchone()['cnt'] == 0:
            default_strategies = [
                ('2560', '2560战法', '趋势策略', '25日均线+60日均量选股策略'),
                ('first_board', '首板涨停', '打板策略', '首板涨停接力策略'),
                ('trend_low', '趋势低吸', '趋势策略', '趋势股低吸策略'),
                ('breakout', '突破策略', '技术策略', '平台突破选股策略'),
                ('volume', '放量启动', '量能策略', '放量启动选股策略'),
            ]
            cur.executemany(
                "INSERT INTO strategies (code, name, category, description, sort_order) VALUES (?, ?, ?, ?, ?)",
                [(s[0], s[1], s[2], s[3], i) for i, s in enumerate(default_strategies)]
            )

        conn.commit()
    finally:
        conn.close()


def q(sql, args=()):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def q1(sql, args=()):
    rows = q(sql, args)
    return rows[0] if rows else None


def execute(sql, args=()):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, args)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def execute_many(sql, args_list):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.executemany(sql, args_list)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
