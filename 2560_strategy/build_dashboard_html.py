import sqlite3
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'data' / 'picks.db'
OUT_HTML = BASE_DIR / 'data' / 'dashboard.html'


def fmt(v, suffix=''):
    if v is None or v == '' or str(v).lower() == 'nan':
        return '-'
    return f'{v}{suffix}'


def query_rows(conn, sql):
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(sql)
    return [dict(r) for r in cur.fetchall()]


def render_list(items, key1, key2):
    if not items:
        return '<li>暂无数据</li>'
    return ''.join([f"<li><strong>{i[key1]}</strong>：{i[key2]}</li>" for i in items])


def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        latest = query_rows(conn, "SELECT pick_date, code, name, source_channel, reason_tag, review_status, content_title FROM picks ORDER BY pick_date DESC, code ASC LIMIT 20")
        stats = query_rows(conn, "SELECT COUNT(*) AS total FROM picks")
        by_channel = query_rows(conn, "SELECT COALESCE(NULLIF(source_channel,''),'system') AS channel, COUNT(*) AS cnt FROM picks GROUP BY channel ORDER BY cnt DESC")
        by_status = query_rows(conn, "SELECT COALESCE(NULLIF(review_status,''),'未复盘') AS status, COUNT(*) AS cnt FROM picks GROUP BY status ORDER BY cnt DESC")
        by_tag = query_rows(conn, "SELECT COALESCE(NULLIF(reason_tag,''),'未标注') AS tag, COUNT(*) AS cnt FROM picks GROUP BY tag ORDER BY cnt DESC")
        by_content = query_rows(conn, "SELECT COALESCE(NULLIF(content_title,''),'未绑定内容') AS title, COUNT(*) AS cnt FROM picks GROUP BY title ORDER BY cnt DESC LIMIT 10")
    finally:
        conn.close()

    total = stats[0]['total'] if stats else 0
    latest_rows = ''.join([
        f"<tr><td>{fmt(r.get('pick_date'))}</td><td>{fmt(r.get('name'))}</td><td>{fmt(r.get('code'))}</td><td>{fmt(r.get('source_channel'))}</td><td>{fmt(r.get('reason_tag'))}</td><td>{fmt(r.get('review_status'))}</td><td>{fmt(r.get('content_title'))}</td></tr>"
        for r in latest
    ]) or '<tr><td colspan="7">暂无数据</td></tr>'

    html = f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>宣传票复盘系统 v3.1</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background:#f7f8fa; color:#1f2328; margin:0; padding:24px; }}
    .wrap {{ max-width: 1280px; margin: 0 auto; }}
    .grid {{ display:grid; grid-template-columns: repeat(4, 1fr); gap:16px; }}
    .grid2 {{ display:grid; grid-template-columns: repeat(2, 1fr); gap:16px; }}
    .card {{ background:#fff; border-radius:16px; padding:18px; box-shadow:0 4px 18px rgba(0,0,0,.06); }}
    h1,h2 {{ margin:0 0 12px; }}
    .muted {{ color:#667085; font-size:14px; }}
    .num {{ font-size:32px; font-weight:700; }}
    ul {{ margin:0; padding-left:18px; }}
    table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:16px; overflow:hidden; }}
    th,td {{ padding:12px 10px; border-bottom:1px solid #eee; text-align:left; font-size:14px; }}
    th {{ background:#fafafa; }}
    .section {{ margin-top:20px; }}
    .tag {{ display:inline-block; background:#eef2ff; color:#374151; border-radius:999px; padding:4px 10px; font-size:12px; margin-right:8px; margin-bottom:6px; }}
    .hint {{ background:#fffbeb; border:1px solid #fde68a; color:#92400e; padding:10px 12px; border-radius:12px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>宣传票复盘系统 v3.1</h1>
    <div class="muted">更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}</div>

    <div class="grid section">
      <div class="card"><div class="muted">累计记录</div><div class="num">{total}</div></div>
      <div class="card"><div class="muted">渠道数</div><div class="num">{len(by_channel)}</div></div>
      <div class="card"><div class="muted">标签数</div><div class="num">{len(by_tag)}</div></div>
      <div class="card"><div class="muted">复盘状态数</div><div class="num">{len(by_status)}</div></div>
    </div>

    <div class="grid2 section">
      <div class="card"><h2>渠道分布</h2><ul>{render_list(by_channel, 'channel', 'cnt')}</ul></div>
      <div class="card"><h2>内容联动 Top10</h2><ul>{render_list(by_content, 'title', 'cnt')}</ul></div>
    </div>

    <div class="grid2 section">
      <div class="card"><h2>标签分布</h2><ul>{render_list(by_tag, 'tag', 'cnt')}</ul></div>
      <div class="card"><h2>人工复盘</h2><ul>{render_list(by_status, 'status', 'cnt')}</ul></div>
    </div>

    <div class="section card">
      <h2>批量编辑入口说明</h2>
      <div class="hint">可先编辑 data/review_edit_template.csv，再运行 bulk_update_reviews.py 批量回写数据库。适合集中补渠道、标签、人工复盘与内容标题。</div>
    </div>

    <div class="section card">
      <h2>最新记录</h2>
      <table>
        <thead>
          <tr><th>日期</th><th>股票</th><th>代码</th><th>渠道</th><th>标签</th><th>复盘结论</th><th>内容标题</th></tr>
        </thead>
        <tbody>
          {latest_rows}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>'''

    OUT_HTML.write_text(html, encoding='utf-8')
    print(f'可视化面板已生成: {OUT_HTML}')


if __name__ == '__main__':
    main()
