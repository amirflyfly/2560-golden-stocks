import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'data' / 'picks.db'
OUT_PATH = BASE_DIR / 'data' / 'first_limit_validate_report.txt'


def previous_trade_day():
    try:
        cal = ak.tool_trade_date_hist_sina()
        if isinstance(cal, pd.DataFrame) and not cal.empty:
            dates = pd.to_datetime(cal['date']).dt.date.tolist()
            today = datetime.now().date()
            prev = [d for d in dates if d < today]
            if prev:
                return prev[-1].strftime('%Y-%m-%d')
    except Exception:
        pass
    return (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')


def ensure_schema(conn):
    cur = conn.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(picks)").fetchall()]
    alters = []
    if 'validation_result' not in cols:
        alters.append("ALTER TABLE picks ADD COLUMN validation_result TEXT DEFAULT ''")
    if 'validation_note' not in cols:
        alters.append("ALTER TABLE picks ADD COLUMN validation_note TEXT DEFAULT ''")
    if 'validated_at' not in cols:
        alters.append("ALTER TABLE picks ADD COLUMN validated_at TEXT DEFAULT ''")
    for sql in alters:
        cur.execute(sql)
    conn.commit()


def fetch_today_limit_map():
    date_str = datetime.now().strftime('%Y%m%d')
    try:
        df = ak.stock_zt_pool_em(date=date_str)
        if df is None or df.empty:
            return {}
        code_col = '代码' if '代码' in df.columns else df.columns[0]
        return {str(x).strip(): True for x in df[code_col].tolist()}
    except Exception:
        return {}


def main():
    prev_day = previous_trade_day()
    today_limit = fetch_today_limit_map()
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_schema(conn)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        rows = cur.execute(
            """SELECT id, pick_date, code, name, second_board_expectation, second_board_score, prediction_reason
            FROM picks
            WHERE COALESCE(strategy_name,'')='首板涨停' AND COALESCE(watch_flag,0)=1 AND pick_date=?""",
            (prev_day,)
        ).fetchall()
        report = [f'首板次日验证简报｜{datetime.now().strftime("%Y-%m-%d %H:%M")}', f'验证日期来源：{prev_day}', '']
        success = 0
        total = len(rows)
        for r in rows:
            code = str(r['code'])
            hit = code in today_limit
            result = '晋级成功' if hit else '未晋级'
            note = '次日仍在涨停池，二板验证成功' if hit else '次日未进入涨停池，二板验证失败'
            if hit:
                success += 1
            cur.execute(
                'UPDATE picks SET validation_result=?, validation_note=?, validated_at=? WHERE id=?',
                (result, note, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), r['id'])
            )
            report.append(f"- {r['name']}（{code}）｜预期 {r['second_board_expectation']}｜评分 {r['second_board_score']}｜结果：{result}｜{note}")
        conn.commit()
        report.append('')
        report.append(f'观察池样本：{total} 只')
        report.append(f'晋级成功：{success} 只')
        report.append(f'晋级率：{round(success / total * 100, 2) if total else 0}%')
        OUT_PATH.write_text('\n'.join(report), encoding='utf-8')
        print('\n'.join(report))
    finally:
        conn.close()


if __name__ == '__main__':
    main()
