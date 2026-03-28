import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'data' / 'picks.db'

ALTERS = [
    "ALTER TABLE picks ADD COLUMN strategy_name TEXT DEFAULT '2560'",
    "ALTER TABLE picks ADD COLUMN first_board_time TEXT DEFAULT ''",
    "ALTER TABLE picks ADD COLUMN theme_reason TEXT DEFAULT ''",
    "ALTER TABLE picks ADD COLUMN second_board_expectation TEXT DEFAULT ''",
    "ALTER TABLE picks ADD COLUMN second_board_score INTEGER DEFAULT 0",
    "ALTER TABLE picks ADD COLUMN prediction_reason TEXT DEFAULT ''",
    "ALTER TABLE picks ADD COLUMN watch_flag INTEGER DEFAULT 0",
    "ALTER TABLE picks ADD COLUMN validation_result TEXT DEFAULT ''",
    "ALTER TABLE picks ADD COLUMN validation_note TEXT DEFAULT ''",
    "ALTER TABLE picks ADD COLUMN validated_at TEXT DEFAULT ''",
]


def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        for sql in ALTERS:
            try:
                cur.execute(sql)
            except sqlite3.OperationalError:
                pass
        conn.commit()
        print('extended schema ok')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
