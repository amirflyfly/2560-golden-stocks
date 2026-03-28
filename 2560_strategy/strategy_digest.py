import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'data' / 'picks.db'
OUT_AM = BASE_DIR / 'data' / 'strategy_digest_am.txt'
OUT_PM = BASE_DIR / 'data' / 'strategy_digest_pm.txt'


def fetch_rows(sql, args=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def prev_day():
    return (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')


def build_am():
    today = datetime.now().strftime('%Y-%m-%d')
    yesterday = prev_day()
    y_rows = fetch_rows("SELECT COALESCE(strategy_name,'2560') AS strategy_name, COUNT(*) AS cnt FROM picks WHERE pick_date=? GROUP BY strategy_name", (yesterday,))
    watch_rows = fetch_rows("SELECT name, code, second_board_score, prediction_reason FROM picks WHERE COALESCE(watch_flag,0)=1 ORDER BY pick_date DESC, COALESCE(second_board_score,0) DESC LIMIT 5")
    lines = [f'早盘策略重点汇报｜{datetime.now().strftime("%Y-%m-%d %H:%M")}', '']
    lines.append(f'昨天（{yesterday}）复盘概况：')
    if y_rows:
        for r in y_rows:
            lines.append(f"- {r['strategy_name']}：{r['cnt']} 条")
    else:
        lines.append('- 昨日暂无入库记录')
    lines.append('')
    lines.append(f'今日（{today}）重点关注：')
    if watch_rows:
        for i, r in enumerate(watch_rows, 1):
            lines.append(f"{i}. {r['name']}（{r['code']}）｜评分 {r['second_board_score']}｜{r['prediction_reason']}")
    else:
        lines.append('暂无重点观察池样本')
    return '\n'.join(lines)


def build_pm():
    today = datetime.now().strftime('%Y-%m-%d')
    rows = fetch_rows("SELECT COALESCE(strategy_name,'2560') AS strategy_name, COUNT(*) AS cnt FROM picks WHERE pick_date=? GROUP BY strategy_name", (today,))
    validate_rows = fetch_rows("SELECT validation_result, COUNT(*) AS cnt FROM picks WHERE pick_date<? AND COALESCE(strategy_name,'')='首板涨停' GROUP BY validation_result", (today,))
    lines = [f'尾盘策略运行汇总｜{datetime.now().strftime("%Y-%m-%d %H:%M")}', '']
    lines.append(f'今日（{today}）策略运行情况：')
    if rows:
        for r in rows:
            lines.append(f"- {r['strategy_name']}：新增 {r['cnt']} 条")
    else:
        lines.append('- 今日暂无新增记录')
    lines.append('')
    lines.append('首板验证结果汇总：')
    if validate_rows:
        for r in validate_rows:
            lines.append(f"- {r.get('validation_result') or '待验证'}：{r['cnt']} 条")
    else:
        lines.append('- 暂无验证结果')
    return '\n'.join(lines)


def main(mode='am'):
    if mode == 'am':
        text = build_am()
        OUT_AM.write_text(text, encoding='utf-8')
    else:
        text = build_pm()
        OUT_PM.write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else 'am')
