import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_JSON = BASE_DIR / 'data' / 'daily_selection.json'
DB_PATH = BASE_DIR / 'data' / 'picks.db'


def main():
    if not DATA_JSON.exists():
        print('没有 daily_selection.json，跳过入库')
        return

    with open(DATA_JSON, 'r', encoding='utf-8') as f:
        items = json.load(f)

    if not isinstance(items, list):
        print('结果格式异常，跳过入库')
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        inserted = 0
        for item in items:
            cur.execute(
                '''
                INSERT OR IGNORE INTO picks
                (pick_date, code, name, pick_price, signal, ma25, vol_ratio, source, source_channel, reason_tag, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    item.get('日期'),
                    item.get('代码'),
                    item.get('名称'),
                    item.get('价格'),
                    item.get('信号'),
                    item.get('25日线'),
                    item.get('量能比'),
                    '2560',
                    'system',
                    item.get('信号', ''),
                    ''
                )
            )
            if cur.rowcount > 0:
                inserted += 1
        conn.commit()
        print(f'入库完成，新增 {inserted} 条')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
