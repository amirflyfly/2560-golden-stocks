import pandas as pd
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
REVIEW_CSV = BASE_DIR / 'data' / 'review_metrics.csv'
OUT_CSV = BASE_DIR / 'data' / 'master_ledger.csv'
OUT_MD = BASE_DIR / 'data' / 'master_ledger.md'
OUT_WEEKLY = BASE_DIR / 'data' / 'weekly_summary.md'
OUT_MONTHLY = BASE_DIR / 'data' / 'monthly_summary.md'


def fmt(v, suffix=''):
    try:
        if pd.isna(v):
            return '-'
    except Exception:
        pass
    return f'{v}{suffix}'


def label_or_default(v):
    try:
        if pd.isna(v):
            return '未标注'
    except Exception:
        pass
    s = str(v).strip()
    return s if s else '未标注'


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


def write_period_summary(df, out_path, title):
    lines = [f'# {title}', '']
    lines.append(f"更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append('')
    if df.empty:
        lines.append('暂无数据')
        out_path.write_text('\n'.join(lines), encoding='utf-8')
        return
    lines.append(f"- 记录数：{len(df)}")
    lines.append(f"- 平均截止今日涨幅：{fmt(mean_or_none(df['latest_pct']), '%')}")
    lines.append(f"- 平均最大涨幅：{fmt(mean_or_none(df['max_pct']), '%')}")
    lines.append(f"- 3日胜率：{fmt(win_rate(df['pct_3d']), '%')}")
    lines.append(f"- 5日胜率：{fmt(win_rate(df['pct_5d']), '%')}")
    lines.append('')
    lines.append('## 渠道表现')
    for channel, d in df.groupby('source_channel'):
        lines.append(f"- {label_or_default(channel)}：{len(d)} 只，平均涨幅 {fmt(mean_or_none(d['latest_pct']), '%')}")
    lines.append('')
    lines.append('## 标签表现')
    for tag, d in df.groupby('reason_tag'):
        lines.append(f"- {label_or_default(tag)}：{len(d)} 只，平均涨幅 {fmt(mean_or_none(d['latest_pct']), '%')}")
    out_path.write_text('\n'.join(lines), encoding='utf-8')


def main():
    if not REVIEW_CSV.exists():
        print('review_metrics.csv 不存在')
        return

    df = pd.read_csv(REVIEW_CSV)
    if 'pick_date' in df.columns:
        df['pick_date_dt'] = pd.to_datetime(df['pick_date'], errors='coerce')
    else:
        df['pick_date_dt'] = pd.NaT

    sort_cols = [c for c in ['pick_date', 'source_channel', 'code'] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=[False, True, True][:len(sort_cols)])
    df.to_csv(OUT_CSV, index=False, encoding='utf-8-sig')

    lines = ['# 宣传票总台账', '']
    lines.append(f"更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append('')
    for _, r in df.iterrows():
        lines.append(
            f"- {fmt(r.get('pick_date'))} | {fmt(r.get('name'))}({fmt(r.get('code'))}) | 渠道 {label_or_default(r.get('source_channel'))} | 标签 {label_or_default(r.get('reason_tag'))} | 入选价 {fmt(r.get('pick_price'))} | 截止今日涨幅 {fmt(r.get('latest_pct'), '%')} | 最大涨幅 {fmt(r.get('max_pct'), '%')} | 最大回撤 {fmt(r.get('min_pct'), '%')}"
        )
    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')

    now = pd.Timestamp.now()
    week_start = now.normalize() - pd.Timedelta(days=now.weekday())
    month_start = now.normalize().replace(day=1)
    weekly_df = df[df['pick_date_dt'] >= week_start]
    monthly_df = df[df['pick_date_dt'] >= month_start]
    write_period_summary(weekly_df, OUT_WEEKLY, '本周复盘汇总')
    write_period_summary(monthly_df, OUT_MONTHLY, '本月复盘汇总')

    print(f'总台账已生成: {OUT_CSV} / {OUT_MD} / {OUT_WEEKLY} / {OUT_MONTHLY}')


if __name__ == '__main__':
    main()
