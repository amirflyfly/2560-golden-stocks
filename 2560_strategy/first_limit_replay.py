import json
import sqlite3
from pathlib import Path
from datetime import datetime

import akshare as ak
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
DB_PATH = DATA_DIR / 'picks.db'
JSON_PATH = DATA_DIR / 'first_limit_selection.json'
TXT_PATH = DATA_DIR / 'first_limit_report.txt'


def is_trading_day_today() -> bool:
    try:
        cal = ak.tool_trade_date_hist_sina()
        if isinstance(cal, pd.DataFrame) and not cal.empty:
            today = datetime.now().strftime('%Y-%m-%d')
            date_col = 'date' if 'date' in cal.columns else (cal.columns[0] if len(cal.columns) > 0 else None)
            if date_col:
                return today in set(cal[date_col].astype(str).tolist())
    except Exception:
        pass
    return datetime.now().weekday() < 5


def fetch_first_limit_candidates():
    date_str = datetime.now().strftime('%Y%m%d')
    df = ak.stock_zt_pool_em(date=date_str)
    if df is None or df.empty:
        return []

    cols = list(df.columns)
    code_col = '代码' if '代码' in cols else cols[0]
    name_col = '名称' if '名称' in cols else cols[1]
    price_col = '最新价' if '最新价' in cols else ('价格' if '价格' in cols else None)
    first_time_col = '首次封板时间' if '首次封板时间' in cols else None
    reason_col = '所属行业' if '所属行业' in cols else ('涨停原因' if '涨停原因' in cols else '')
    stat_col = '涨停统计' if '涨停统计' in cols else None
    turnover_col = '换手率' if '换手率' in cols else None
    amount_col = '成交额' if '成交额' in cols else None

    items = []
    for _, row in df.iterrows():
        stat_val = str(row.get(stat_col, '')) if stat_col else ''
        if not ('1天1板' in stat_val or stat_val.startswith('1/1') or stat_val.startswith('1板') or stat_val == '1'):
            continue
        items.append({
            '日期': datetime.now().strftime('%Y-%m-%d'),
            '代码': str(row.get(code_col, '')).strip(),
            '名称': str(row.get(name_col, '')).strip(),
            '价格': row.get(price_col) if price_col else '',
            '信号': '首板涨停',
            '首次封板时间': row.get(first_time_col, '') if first_time_col else '',
            '涨停统计': stat_val,
            '题材/行业': row.get(reason_col, '') if reason_col else '',
            '换手率': row.get(turnover_col, '') if turnover_col else '',
            '成交额': row.get(amount_col, '') if amount_col else '',
        })
    return items


def ensure_schema():
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cols = [r[1] for r in cur.execute("PRAGMA table_info(picks)").fetchall()]
        alters = []
        if 'strategy_name' not in cols:
            alters.append("ALTER TABLE picks ADD COLUMN strategy_name TEXT DEFAULT '2560'")
        if 'first_board_time' not in cols:
            alters.append("ALTER TABLE picks ADD COLUMN first_board_time TEXT DEFAULT ''")
        if 'theme_reason' not in cols:
            alters.append("ALTER TABLE picks ADD COLUMN theme_reason TEXT DEFAULT ''")
        for sql in alters:
            cur.execute(sql)
        conn.commit()
    finally:
        conn.close()


def ingest(items):
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        inserted = 0
        for item in items:
            cur.execute(
                '''INSERT OR IGNORE INTO picks
                (pick_date, code, name, pick_price, signal, source, source_channel, reason_tag, note, strategy_name, first_board_time, theme_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    item.get('日期'),
                    item.get('代码'),
                    item.get('名称'),
                    item.get('价格') if item.get('价格') not in (None, '') else None,
                    item.get('信号'),
                    'first_limit',
                    'limitup',
                    '首板涨停',
                    '首板复盘：关注次日是否晋级二板',
                    '首板涨停',
                    item.get('首次封板时间', ''),
                    item.get('题材/行业', ''),
                )
            )
            if cur.rowcount > 0:
                inserted += 1
        conn.commit()
        return inserted
    finally:
        conn.close()


def build_report(items):
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines = [f'首板涨停复盘简报｜{now}', '']
    lines.append('为什么要复盘首板：')
    lines.append('1. 首板是市场首次表态，最容易看清当天资金认可的方向；')
    lines.append('2. 复盘首板，可以筛出有题材、有换手、有封板质量的个股；')
    lines.append('3. 最终目标不是看首板本身，而是提前找到可能晋级二板的核心候选。')
    lines.append('')
    if not items:
        lines.append('今日暂无可复盘的首板涨停样本。')
        return '\n'.join(lines)
    lines.append(f'今日首板样本 {len(items)} 只：')
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. {item.get('名称')}（{item.get('代码')}）")
        lines.append(f"   - 最新价：{item.get('价格')}")
        lines.append(f"   - 首次封板时间：{item.get('首次封板时间')}")
        lines.append(f"   - 题材/行业：{item.get('题材/行业')}")
        lines.append(f"   - 复盘意义：观察次日是否有继续强势、是否具备二板晋级预期")
    lines.append('')
    lines.append('首板复盘最终想得到什么？')
    lines.append(' - 预判哪几只最有可能走出二板；')
    lines.append(' - 提前总结题材、封板时间、换手结构、市场情绪对晋级率的影响；')
    lines.append(' - 把“看热闹”变成“看规律”。')
    return '\n'.join(lines)


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ensure_schema()
    if not is_trading_day_today():
        JSON_PATH.write_text('[]', encoding='utf-8')
        TXT_PATH.write_text('首板涨停复盘简报\n\n非交易日，跳过。', encoding='utf-8')
        print('非交易日，跳过首板复盘')
        return
    items = fetch_first_limit_candidates()
    JSON_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    inserted = ingest(items)
    text = build_report(items)
    TXT_PATH.write_text(text, encoding='utf-8')
    print(text)
    print(f'入库完成，新增 {inserted} 条首板记录')


if __name__ == '__main__':
    main()
