import csv
import sqlite3
from pathlib import Path
import argparse

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'data' / 'picks.db'


def main():
    parser = argparse.ArgumentParser(description='从 CSV 导入宣传好票')
    parser.add_argument('--file', required=True, help='CSV 文件路径')
    args = parser.parse_args()

    csv_path = Path(args.file).resolve()
    if not csv_path.exists():
        print(f'文件不存在: {csv_path}')
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        inserted = 0
        with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                cur.execute(
                    '''
                    INSERT OR REPLACE INTO picks
                    (pick_date, code, name, pick_price, signal, source, source_channel, reason_tag, note, review_status, review_comment, content_title, content_ref)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        row.get('date', '').strip(),
                        row.get('code', '').strip(),
                        row.get('name', '').strip(),
                        float(row.get('price', 0) or 0),
                        row.get('signal', '').strip(),
                        row.get('source', 'manual').strip(),
                        row.get('channel', 'unknown').strip(),
                        row.get('reason_tag', '').strip(),
                        row.get('note', '').strip(),
                        row.get('review_status', '').strip(),
                        row.get('review_comment', '').strip(),
                        row.get('content_title', '').strip(),
                        row.get('content_ref', '').strip(),
                    )
                )
                if cur.rowcount > 0:
                    inserted += 1
        conn.commit()
        print(f'CSV 导入完成: {csv_path}，写入/更新 {inserted} 条')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
