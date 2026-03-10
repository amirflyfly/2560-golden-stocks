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
