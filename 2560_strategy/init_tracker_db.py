import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'data' / 'picks.db'

SCHEMA = '''
CREATE TABLE IF NOT EXISTS picks (
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
);

CREATE INDEX IF NOT EXISTS idx_picks_code ON picks(code);
CREATE INDEX IF NOT EXISTS idx_picks_date ON picks(pick_date);
'''

ALTERS = [
    "ALTER TABLE picks ADD COLUMN source_channel TEXT DEFAULT 'system'",
    "ALTER TABLE picks ADD COLUMN reason_tag TEXT DEFAULT ''",
    "ALTER TABLE picks ADD COLUMN note TEXT DEFAULT ''",
    "ALTER TABLE picks ADD COLUMN review_status TEXT DEFAULT ''",
    "ALTER TABLE picks ADD COLUMN review_comment TEXT DEFAULT ''",
    "ALTER TABLE picks ADD COLUMN content_title TEXT DEFAULT ''",
    "ALTER TABLE picks ADD COLUMN content_ref TEXT DEFAULT ''",
]


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA)
        cur = conn.cursor()
        for sql in ALTERS:
            try:
                cur.execute(sql)
            except sqlite3.OperationalError:
                pass
        conn.commit()
        print(f'数据库已初始化/升级: {DB_PATH}')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
