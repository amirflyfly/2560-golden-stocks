import os
import sys
import sqlite3
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, 'data', 'picks.db')
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.maintenance.legacy_sqlite_guard import refuse_production

refuse_production("strategy_digest.py")

from backend.services.research_service import analyze_watchlist


def fetchall(sql, params=()):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(sql, params).fetchall()
    con.close()
    return rows


def print_rows(title, rows, formatter):
    print(f'\n=== {title} ({len(rows)}) ===')
    if not rows:
        print('暂无')
        return
    for row in rows:
        print(formatter(row))


def morning_digest():
    today = datetime.now().strftime('%Y-%m-%d')
    analyze_watchlist(limit=30, analysis_date=today)
    watch_rows = fetchall(
        "SELECT pick_date, code, name, COALESCE(second_board_score,0) AS score, COALESCE(prediction_reason,'') AS reason FROM picks WHERE COALESCE(watch_flag,0)=1 ORDER BY COALESCE(second_board_score,0) DESC, pick_date DESC LIMIT 10"
    )
    print_rows('重点观察池', watch_rows, lambda r: f"[{r['pick_date']}] {r['code']} {r['name']} | 研究分={r['score']} | {r['reason']}")



def afternoon_digest():
    today = datetime.now().strftime('%Y-%m-%d')
    analyze_watchlist(limit=30, analysis_date=today)
    rows = fetchall(
        "SELECT pick_date, code, name, COALESCE(validation_result,'待验证') AS validation_result, COALESCE(prediction_reason,'') AS reason FROM picks WHERE COALESCE(watch_flag,0)=1 ORDER BY pick_date DESC LIMIT 10"
    )
    print_rows('自选股午后跟踪', rows, lambda r: f"[{r['pick_date']}] {r['code']} {r['name']} | 验证={r['validation_result']} | {r['reason']}")


if __name__ == '__main__':
    mode = (sys.argv[1] if len(sys.argv) > 1 else 'am').lower()
    if mode == 'pm':
        afternoon_digest()
    else:
        morning_digest()
