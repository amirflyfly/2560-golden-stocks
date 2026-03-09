import pandas as pd
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
REVIEW_CSV = BASE_DIR / 'data' / 'review_metrics.csv'
OUT_CSV = BASE_DIR / 'data' / 'content_analytics.csv'
OUT_MD = BASE_DIR / 'data' / 'content_analytics.md'


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
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return '-'
    return f'{v}{suffix}'


def label(v, default='未绑定内容'):
    try:
        if pd.isna(v):
            return default
    except Exception:
        pass
    s = str(v).strip()
    return s if s and s != '-' else default


def main():
    if not REVIEW_CSV.exists():
        print('review_metrics.csv 不存在')
        return

    df = pd.read_csv(REVIEW_CSV)
    if df.empty:
        print('暂无复盘数据')
        return

    df['content_title'] = df.get('content_title', '').apply(lambda x: label(x, '未绑定内容'))
    df['content_ref'] = df.get('content_ref', '').apply(lambda x: label(x, '-'))

    rows = []
    for (title, ref), g in df.groupby(['content_title', 'content_ref']):
        rows.append({
            'content_title': title,
            'content_ref': ref,
            'count': len(g),
            'avg_latest_pct': mean_or_none(g['latest_pct']),
            'avg_max_pct': mean_or_none(g['max_pct']),
            'avg_min_pct': mean_or_none(g['min_pct']),
            'win_3d': win_rate(g['pct_3d']),
            'win_5d': win_rate(g['pct_5d']),
            'win_10d': win_rate(g['pct_10d']),
        })

    out = pd.DataFrame(rows).sort_values(['count', 'avg_latest_pct'], ascending=[False, False], na_position='last')
    out.to_csv(OUT_CSV, index=False, encoding='utf-8-sig')

    lines = ['# 内容联动统计', '']
    lines.append(f"更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append('')
    for _, r in out.iterrows():
        lines.append(
            f"- {r['content_title']} | ref {r['content_ref']} | 关联票数 {r['count']} | 平均截止今日涨幅 {fmt(r['avg_latest_pct'], '%')} | 平均最大涨幅 {fmt(r['avg_max_pct'], '%')} | 3日胜率 {fmt(r['win_3d'], '%')} | 5日胜率 {fmt(r['win_5d'], '%')} | 10日胜率 {fmt(r['win_10d'], '%')}"
        )
    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')
    print(f'内容联动统计已生成: {OUT_CSV} / {OUT_MD}')


if __name__ == '__main__':
    main()
