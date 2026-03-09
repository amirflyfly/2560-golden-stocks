import sqlite3
from pathlib import Path
import akshare as ak
import pandas as pd
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'data' / 'picks.db'
OUT_CSV = BASE_DIR / 'data' / 'review_metrics.csv'
OUT_MD = BASE_DIR / 'data' / 'review_metrics.md'
OUT_SUMMARY = BASE_DIR / 'data' / 'dashboard_summary.md'


def fetch_hist(code: str, start_date: str):
    try:
        df = ak.stock_zh_a_hist(symbol=code, period='daily', adjust='qfq', start_date=start_date)
        if df is None or df.empty:
            return pd.DataFrame()
        rename_map = {
            '日期': 'date', '开盘': 'open', '收盘': 'close', '最高': 'high', '最低': 'low',
            '成交量': 'volume', '成交额': 'amount', '振幅': 'amplitude', '涨跌幅': 'pct_chg',
            '涨跌额': 'chg_amt', '换手率': 'turnover'
        }
        return df.rename(columns=rename_map)
    except Exception:
        return pd.DataFrame()


def nth_close_pct(hist: pd.DataFrame, pick_price: float, n: int):
    if hist.empty or not pick_price or len(hist) < n:
        return None
    close_n = float(hist.iloc[n - 1]['close'])
    return round((close_n / pick_price - 1) * 100, 2)


def safe_num(v):
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    return v


def calc_metrics(pick_price: float, hist: pd.DataFrame):
    if hist.empty or not pick_price:
        return {
            'latest_close': None, 'latest_pct': None, 'max_close': None, 'max_pct': None,
            'min_close': None, 'min_pct': None, 'days_tracked': 0,
            'pct_3d': None, 'pct_5d': None, 'pct_10d': None,
        }
    latest_close = float(hist.iloc[-1]['close'])
    max_close = float(hist['high'].max()) if 'high' in hist.columns else float(hist['close'].max())
    min_close = float(hist['low'].min()) if 'low' in hist.columns else float(hist['close'].min())
    return {
        'latest_close': round(latest_close, 2),
        'latest_pct': round((latest_close / pick_price - 1) * 100, 2),
        'max_close': round(max_close, 2),
        'max_pct': round((max_close / pick_price - 1) * 100, 2),
        'min_close': round(min_close, 2),
        'min_pct': round((min_close / pick_price - 1) * 100, 2),
        'days_tracked': int(len(hist)),
        'pct_3d': nth_close_pct(hist, pick_price, 3),
        'pct_5d': nth_close_pct(hist, pick_price, 5),
        'pct_10d': nth_close_pct(hist, pick_price, 10),
    }


def mean_or_none(series):
    s = pd.to_numeric(series, errors='coerce').dropna()
    if s.empty:
        return None
    return round(float(s.mean()), 2)


def win_rate(series):
    s = pd.to_numeric(series, errors='coerce').dropna()
    if s.empty:
        return None
    return round(float((s > 0).mean() * 100), 2)


def fmt(v, suffix=''):
    if v is None:
        return '-'
    try:
        if pd.isna(v):
            return '-'
    except Exception:
        pass
    return f'{v}{suffix}'


def label_or_default(v, default='未标注'):
    if v is None:
        return default
    try:
        if pd.isna(v):
            return default
    except Exception:
        pass
    s = str(v).strip()
    return s if s else default


def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        picks = pd.read_sql_query(
            'SELECT pick_date, code, name, pick_price, signal, ma25, vol_ratio, source, source_channel, reason_tag, note, review_status, review_comment, content_title, content_ref FROM picks ORDER BY pick_date DESC, code ASC',
            conn
        )
    finally:
        conn.close()

    if picks.empty:
        print('数据库暂无记录')
        return

    rows = []
    for _, row in picks.iterrows():
        pick_date = str(row['pick_date'])
        code = str(row['code'])
        hist = fetch_hist(code, pick_date.replace('-', ''))
        metrics = calc_metrics(float(row['pick_price']), hist)
        rows.append({
            'pick_date': pick_date,
            'code': code,
            'name': row['name'],
            'pick_price': row['pick_price'],
            'signal': row['signal'],
            'source': row['source'],
            'source_channel': label_or_default(row['source_channel'], 'system'),
            'reason_tag': label_or_default(row['reason_tag']),
            'review_status': label_or_default(row['review_status'], '未复盘'),
            'review_comment': label_or_default(row['review_comment'], '-'),
            'content_title': label_or_default(row['content_title'], '-'),
            'content_ref': label_or_default(row['content_ref'], '-'),
            'latest_close': safe_num(metrics['latest_close']),
            'latest_pct': safe_num(metrics['latest_pct']),
            'max_close': safe_num(metrics['max_close']),
            'max_pct': safe_num(metrics['max_pct']),
            'min_close': safe_num(metrics['min_close']),
            'min_pct': safe_num(metrics['min_pct']),
            'days_tracked': metrics['days_tracked'],
            'pct_3d': safe_num(metrics['pct_3d']),
            'pct_5d': safe_num(metrics['pct_5d']),
            'pct_10d': safe_num(metrics['pct_10d']),
            'vol_ratio': row['vol_ratio'],
            'note': label_or_default(row['note'], '-'),
        })

    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False, encoding='utf-8-sig')

    md_lines = ['# 好票复盘指标', '']
    md_lines.append(f'生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}')
    md_lines.append('')
    top = out.sort_values(by=['latest_pct'], ascending=False, na_position='last')
    for _, r in top.iterrows():
        md_lines.append(
            f"- {r['pick_date']} | {r['name']}({r['code']}) | 渠道 {r['source_channel']} | 标签 {r['reason_tag']} | 复盘 {r['review_status']} | 内容 {r['content_title']} | 截止今日涨幅 {fmt(r['latest_pct'], '%')} | 最大涨幅 {fmt(r['max_pct'], '%')} | 最大回撤 {fmt(r['min_pct'], '%')} | 3日 {fmt(r['pct_3d'], '%')} | 5日 {fmt(r['pct_5d'], '%')} | 10日 {fmt(r['pct_10d'], '%')}"
        )
    OUT_MD.write_text('\n'.join(md_lines), encoding='utf-8')

    summary = []
    summary.append('# 宣传好票复盘看板')
    summary.append('')
    summary.append(f'更新时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}')
    summary.append('')
    summary.append(f"- 累计记录数：{len(out)}")
    summary.append(f"- 截止今日平均涨幅：{fmt(mean_or_none(out['latest_pct']), '%')}")
    summary.append(f"- 平均最大涨幅：{fmt(mean_or_none(out['max_pct']), '%')}")
    summary.append(f"- 平均最大回撤：{fmt(mean_or_none(out['min_pct']), '%')}")
    summary.append(f"- 3日胜率：{fmt(win_rate(out['pct_3d']), '%')}")
    summary.append(f"- 5日胜率：{fmt(win_rate(out['pct_5d']), '%')}")
    summary.append(f"- 10日胜率：{fmt(win_rate(out['pct_10d']), '%')}")
    summary.append('')
    summary.append('## 人工复盘结论')
    for status, dfr in out.groupby('review_status'):
        summary.append(f"- {status}：{len(dfr)} 只")
    summary.append('')
    summary.append('## 渠道统计')
    for channel, dfc in out.groupby('source_channel'):
        summary.append(f"- {channel}：{len(dfc)} 只，平均截止今日涨幅 {fmt(mean_or_none(dfc['latest_pct']), '%')}，3日胜率 {fmt(win_rate(dfc['pct_3d']), '%')}，5日胜率 {fmt(win_rate(dfc['pct_5d']), '%')}")
    summary.append('')
    summary.append('## 标签统计')
    for tag, dft in out.groupby('reason_tag'):
        summary.append(f"- {tag}：{len(dft)} 只，平均截止今日涨幅 {fmt(mean_or_none(dft['latest_pct']), '%')}，3日胜率 {fmt(win_rate(dft['pct_3d']), '%')}，5日胜率 {fmt(win_rate(dft['pct_5d']), '%')}")
    OUT_SUMMARY.write_text('\n'.join(summary), encoding='utf-8')

    print(f'复盘文件已生成: {OUT_CSV} / {OUT_MD} / {OUT_SUMMARY}')


if __name__ == '__main__':
    main()
