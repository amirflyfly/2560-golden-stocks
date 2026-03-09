import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import html
import json
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'data' / 'picks.db'
PORT = 8765


def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def q(sql, args=()):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def execute(sql, args=()):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, args)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def label(v, default='-'):
    if v is None:
        return default
    s = str(v).strip()
    return s if s and s.lower() != 'nan' else default


def esc(v):
    return html.escape(label(v, ''))


def render_dashboard():
    stats = q('SELECT COUNT(*) AS total FROM picks')
    total = stats[0]['total'] if stats else 0
    by_channel = q("SELECT COALESCE(NULLIF(source_channel,''),'system') AS name, COUNT(*) AS cnt FROM picks GROUP BY name ORDER BY cnt DESC")
    by_tag = q("SELECT COALESCE(NULLIF(reason_tag,''),'未标注') AS name, COUNT(*) AS cnt FROM picks GROUP BY name ORDER BY cnt DESC")
    by_status = q("SELECT COALESCE(NULLIF(review_status,''),'未复盘') AS name, COUNT(*) AS cnt FROM picks GROUP BY name ORDER BY cnt DESC")
    by_content = q("SELECT COALESCE(NULLIF(content_title,''),'未绑定内容') AS name, COUNT(*) AS cnt FROM picks GROUP BY name ORDER BY cnt DESC LIMIT 10")
    latest = q("SELECT pick_date, code, name, pick_price, source_channel, reason_tag, review_status, content_title FROM picks ORDER BY pick_date DESC, code ASC LIMIT 20")

    def lis(rows):
        if not rows:
            return '<li>暂无数据</li>'
        return ''.join([f"<li><strong>{esc(r['name'])}</strong>：{r['cnt']}</li>" for r in rows])

    latest_rows = ''.join([
        f"<tr><td>{esc(r['pick_date'])}</td><td>{esc(r['name'])}</td><td>{esc(r['code'])}</td><td>{esc(r['pick_price'])}</td><td>{esc(r['source_channel'])}</td><td>{esc(r['reason_tag'])}</td><td>{esc(r['review_status'])}</td><td>{esc(r['content_title'])}</td></tr>"
        for r in latest
    ]) or '<tr><td colspan="8">暂无数据</td></tr>'

    return f'''<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>宣传票复盘系统 v3.2</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f6f7fb;color:#1f2937;margin:0;padding:24px}}
.wrap{{max-width:1280px;margin:0 auto}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}}
.grid2{{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}}
.card{{background:#fff;border-radius:16px;padding:18px;box-shadow:0 6px 20px rgba(0,0,0,.06)}}
h1,h2{{margin:0 0 12px}} .muted{{color:#6b7280;font-size:14px}} .num{{font-size:32px;font-weight:700}}
ul{{margin:0;padding-left:18px}} table{{width:100%;border-collapse:collapse}} th,td{{padding:10px;border-bottom:1px solid #eee;text-align:left;font-size:14px}} th{{background:#fafafa}}
.section{{margin-top:20px}} input,select,textarea{{width:100%;padding:10px;border:1px solid #d1d5db;border-radius:10px;box-sizing:border-box}} textarea{{min-height:90px}} .formgrid{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}} button{{background:#111827;color:#fff;border:0;border-radius:10px;padding:10px 16px;cursor:pointer}} .hint{{font-size:13px;color:#6b7280}}
a.btn{{display:inline-block;background:#111827;color:#fff;text-decoration:none;padding:10px 16px;border-radius:10px}}
</style></head><body><div class="wrap">
<h1>宣传票复盘系统 v3.2</h1>
<div class="muted">更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} · 本地服务端口 {PORT}</div>
<div class="grid section">
<div class="card"><div class="muted">累计记录</div><div class="num">{total}</div></div>
<div class="card"><div class="muted">渠道数</div><div class="num">{len(by_channel)}</div></div>
<div class="card"><div class="muted">标签数</div><div class="num">{len(by_tag)}</div></div>
<div class="card"><div class="muted">复盘状态数</div><div class="num">{len(by_status)}</div></div>
</div>
<div class="grid2 section">
<div class="card"><h2>渠道分布</h2><ul>{lis(by_channel)}</ul></div>
<div class="card"><h2>内容联动 Top10</h2><ul>{lis(by_content)}</ul></div>
</div>
<div class="grid2 section">
<div class="card"><h2>标签分布</h2><ul>{lis(by_tag)}</ul></div>
<div class="card"><h2>人工复盘状态</h2><ul>{lis(by_status)}</ul></div>
</div>
<div class="section card">
<h2>录入 / 编辑入口</h2>
<form method="post" action="/add">
<div class="formgrid">
<div><label>日期</label><input name="pick_date" value="{datetime.now().strftime('%Y-%m-%d')}" required></div>
<div><label>股票代码</label><input name="code" required></div>
<div><label>股票名称</label><input name="name" required></div>
<div><label>推荐价</label><input name="pick_price" required></div>
<div><label>信号</label><input name="signal"></div>
<div><label>渠道</label><input name="source_channel" placeholder="douyin/xhs/live/community"></div>
<div><label>标签</label><input name="reason_tag" placeholder="趋势突破/缩量回踩"></div>
<div><label>复盘结论</label><select name="review_status"><option>未复盘</option><option>值得复讲</option><option>逻辑一般</option><option>不建议再提</option></select></div>
<div><label>内容标题</label><input name="content_title"></div>
<div><label>内容编号/链接</label><input name="content_ref"></div>
</div>
<div style="margin-top:12px"><label>备注/复盘评论</label><textarea name="note"></textarea></div>
<div style="margin-top:12px"><button type="submit">保存到系统</button></div>
<div class="hint" style="margin-top:8px">提交后会写入 picks.db，可继续用 CSV 批量维护。</div>
</form>
</div>
<div class="section card">
<h2>快捷入口</h2>
<p><a class="btn" href="/export">导出当前记录 JSON</a></p>
</div>
<div class="section card">
<h2>最新记录</h2>
<table><thead><tr><th>日期</th><th>股票</th><th>代码</th><th>推荐价</th><th>渠道</th><th>标签</th><th>复盘结论</th><th>内容标题</th></tr></thead><tbody>{latest_rows}</tbody></table>
</div>
</div></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, content_type='text/html; charset=utf-8'):
        body_bytes = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/':
            self._send(200, render_dashboard())
        elif parsed.path == '/health':
            self._send(200, 'ok', 'text/plain; charset=utf-8')
        elif parsed.path == '/export':
            rows = q('SELECT * FROM picks ORDER BY pick_date DESC, code ASC')
            self._send(200, json.dumps(rows, ensure_ascii=False, indent=2), 'application/json; charset=utf-8')
        else:
            self._send(404, 'not found', 'text/plain; charset=utf-8')

    def do_POST(self):
        if self.path != '/add':
            self._send(404, 'not found', 'text/plain; charset=utf-8')
            return
        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length).decode('utf-8')
        data = {k: v[0] for k, v in parse_qs(raw).items()}
        execute(
            '''INSERT OR REPLACE INTO picks
            (pick_date, code, name, pick_price, signal, source, source_channel, reason_tag, note, review_status, review_comment, content_title, content_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                data.get('pick_date',''), data.get('code',''), data.get('name',''), float(data.get('pick_price','0') or 0),
                data.get('signal',''), 'webform', data.get('source_channel','web'), data.get('reason_tag',''), data.get('note',''),
                data.get('review_status','未复盘'), data.get('note',''), data.get('content_title',''), data.get('content_ref','')
            )
        )
        self.send_response(303)
        self.send_header('Location', '/')
        self.end_headers()


if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f'v3.2 server running on http://0.0.0.0:{PORT}')
    server.serve_forever()
