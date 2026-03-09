import csv
import sqlite3
from pathlib import Path
import argparse

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'data' / 'picks.db'

UPDATABLE_FIELDS = [
    'review_status', 'review_comment', 'content_title', 'content_ref',
    'source_channel', 'reason_tag', 'note'
]


def main():
    parser = argparse.ArgumentParser(description='批量更新人工复盘与内容联动字段')
    parser.add_argument('--file', required=True, help='CSV 文件路径')
    args = parser.parse_args()

    csv_path = Path(args.file).resolve()
    if not csv_path.exists():
        print(f'文件不存在: {csv_path}')
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        updated = 0
        with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                pick_date = (row.get('pick_date') or row.get('date') or '').strip()
                code = (row.get('code') or '').strip()
                if not pick_date or not code:
                    continue
                fields = []
                values = []
                for field in UPDATABLE_FIELDS:
                    if field in row and row[field] is not None:
                        fields.append(f"{field} = ?")
                        values.append(row[field].strip())
                if not fields:
                    continue
                values.extend([pick_date, code])
                sql = f"UPDATE picks SET {', '.join(fields)} WHERE pick_date = ? AND code = ?"
                cur.execute(sql, values)
                updated += cur.rowcount
        conn.commit()
        print(f'批量更新完成: {csv_path}，更新 {updated} 条')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
