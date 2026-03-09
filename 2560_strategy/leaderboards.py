import pandas as pd
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
REVIEW_CSV = BASE_DIR / 'data' / 'review_metrics.csv'
OUT_MD = BASE_DIR / 'data' / 'leaderboards.md'


def fmt(v):
    try:
        if pd.isna(v):
            return '-'
    except Exception:
        pass
    return f'{round(float(v), 2)}%'


def label_or_default(v):
    try:
        if pd.isna(v):
            return '未标注'
    except Exception:
        pass
    s = str(v).strip()
    return s if s else '未标注'


def section(title, df, metric):
    lines = [f'## {title}']
    if df.empty:
        lines.append('- 暂无数据')
        lines.append('')
        return lines
    for _, r in df.iterrows():
        lines.append(f"- {r['pick_date']} | {r['name']}({r['code']}) | 渠道 {label_or_default(r['source_channel'])} | 标签 {label_or_default(r['reason_tag'])} | {metric} {fmt(r[metric])}")
    lines.append('')
    return lines


def rate_section(title, series_name, df, group_col):
    lines = [f'## {title}']
    valid = df.copy()
    valid[series_name] = pd.to_numeric(valid[series_name], errors='coerce')
    valid = valid[valid[series_name].notna()]
    if valid.empty:
        lines.append('- 暂无数据')
        lines.append('')
        return lines
    agg = valid.groupby(group_col)[series_name].apply(lambda s: round(float((s > 0).mean() * 100), 2)).sort_values(ascending=False)
    for k, v in agg.items():
        lines.append(f'- {label_or_default(k)}：{v}%')
    lines.append('')
    return lines


def main():
    if not REVIEW_CSV.exists():
        print('review_metrics.csv 不存在')
        return

    df = pd.read_csv(REVIEW_CSV)
    lines = ['# 宣传好票复盘榜单', '']
    lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append('')

    valid_latest = df[pd.to_numeric(df['latest_pct'], errors='coerce').notna()].copy()
    valid_max = df[pd.to_numeric(df['max_pct'], errors='coerce').notna()].copy()
    valid_drawdown = df[pd.to_numeric(df['min_pct'], errors='coerce').notna()].copy()

    top_latest = valid_latest.sort_values('latest_pct', ascending=False).head(10)
    top_max = valid_max.sort_values('max_pct', ascending=False).head(10)
    low_drawdown = valid_drawdown.sort_values('min_pct', ascending=False).head(10)

    lines += section('截止今日涨幅 TOP10', top_latest, 'latest_pct')
    lines += section('最大涨幅 TOP10', top_max, 'max_pct')
    lines += section('回撤最小 TOP10', low_drawdown, 'min_pct')
    lines += rate_section('按渠道 3日胜率', 'pct_3d', df, 'source_channel')
    lines += rate_section('按渠道 5日胜率', 'pct_5d', df, 'source_channel')
    lines += rate_section('按标签 3日胜率', 'pct_3d', df, 'reason_tag')
    lines += rate_section('按标签 5日胜率', 'pct_5d', df, 'reason_tag')

    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')
    print(f'榜单已生成: {OUT_MD}')


if __name__ == '__main__':
    main()
