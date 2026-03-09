import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(__file__)
DATA_JSON = os.path.join(BASE_DIR, 'data', 'daily_selection.json')
OUT_TXT = os.path.join(BASE_DIR, 'data', 'daily_report.txt')


def build_report(items):
    today = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines = []
    lines.append(f"2560战法扫描简报｜{today}")
    lines.append("")
    if not items:
        lines.append("今日无符合严格 2560 战法特征的标的，建议空仓观望。")
        return "\n".join(lines)

    lines.append(f"今日入选 {len(items)} 只：")
    for i, item in enumerate(items, 1):
        signal = item.get('信号', '-')
        code = item.get('代码', '-')
        name = item.get('名称', '-')
        price = item.get('价格', '-')
        ma25 = item.get('25日线', '-')
        vol_ratio = item.get('量能比', '-')
        reason = []
        if signal == '缩量回踩':
            reason.append('价格在25日线附近')
            reason.append('缩量回踩，趋势未坏')
        elif signal == '放量突破':
            reason.append('站上25日线')
            reason.append('放量突破，关注持续性')
        if vol_ratio not in ('-', None):
            reason.append(f"量能比 {vol_ratio}")
        lines.append(f"{i}. {name}（{code}）")
        lines.append(f"   - 现价：{price}")
        lines.append(f"   - 信号：{signal}")
        lines.append(f"   - 25日线：{ma25}")
        lines.append(f"   - 入选原因：{'；'.join(reason)}")
    lines.append("")
    lines.append("风险提示：仅为技术筛选结果，不构成投资建议。")
    return "\n".join(lines)


def main():
    if not os.path.exists(DATA_JSON):
        text = f"2560战法扫描简报｜{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n暂无结果文件。"
    else:
        with open(DATA_JSON, 'r', encoding='utf-8') as f:
            items = json.load(f)
        text = build_report(items)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, 'w', encoding='utf-8') as f:
        f.write(text)
    print(text)


if __name__ == '__main__':
    main()
