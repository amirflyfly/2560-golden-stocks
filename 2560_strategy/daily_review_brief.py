import pandas as pd
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
REVIEW_CSV = BASE_DIR / 'data' / 'review_metrics.csv'
OUT_TXT = BASE_DIR / 'data' / 'daily_review_brief.txt'


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


def main():
    if not REVIEW_CSV.exists():
        OUT_TXT.write_text('暂无复盘数据', encoding='utf-8')
        print('暂无复盘数据')
        return

    df = pd.read_csv(REVIEW_CSV)
    today = datetime.now().strftime('%Y-%m-%d')
    today_df = df[df['pick_date'] == today] if 'pick_date' in df.columns else pd.DataFrame()

    lines = [f'宣传票日报｜{datetime.now().strftime("%Y-%m-%d %H:%M")}', '']
    lines.append(f'今日记录数：{len(today_df)}')
    lines.append('')

    if today_df.empty:
        lines.append('今天还没有新记录。')
    else:
        for _, r in today_df.iterrows():
            lines.append(f"- {r['name']}({r['code']}) | 渠道 {label_or_default(r['source_channel'])} | 标签 {label_or_default(r['reason_tag'])} | 今日涨幅 {fmt(r['latest_pct'])} | 最大涨幅 {fmt(r['max_pct'])} | 最大回撤 {fmt(r['min_pct'])}")

    OUT_TXT.write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
