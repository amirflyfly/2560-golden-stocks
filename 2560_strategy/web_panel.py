import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import html
import json
from datetime import datetime
import secrets

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
DB_PATH = DATA_DIR / 'picks.db'
SECRET_PATH = DATA_DIR / 'web_panel_secret.txt'
PORT = 8765
COOKIE_NAME = 'promo_panel_auth'


def ensure_secret():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SECRET_PATH.exists():
        return SECRET_PATH.read_text(encoding='utf-8').strip()
    secret = secrets.token_urlsafe(8)
    SECRET_PATH.write_text(secret, encoding='utf-8')
    return secret


PANEL_PASSWORD = ensure_secret()


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


def parse_cookies(header):
    cookies = {}
    if not header:
        return cookies
    for part in header.split(';'):
        if '=' in part:
            k, v = part.strip().split('=', 1)
            cookies[k] = v
    return cookies


def bar_html(rows, label_key='name', value_key='cnt', color='#4f46e5'):
    if not rows:
        return '<div class="muted">暂无数据</div>'
    maxv = max([r.get(value_key, 0) or 0 for r in rows]) or 1
    items = []
    for r in rows:
        name = esc(r.get(label_key))
        val = r.get(value_key, 0) or 0
        width = max(8, int(val / maxv * 100))
        items.append(f'''<div class="bar-row"><div class="bar-label">{name}</div><div class="bar-track"><div class="bar-fill" style="width:{width}%;background:{color}"></div></div><div class="bar-value">{val}</div></div>''')
    return ''.join(items)


def filter_where(params):
    wheres = []
    args = []
    keyword = (params.get('keyword', [''])[0] or '').strip()
    channel = (params.get('channel', [''])[0] or '').strip()
    tag = (params.get('tag', [''])[0] or '').strip()
    status = (params.get('status', [''])[0] or '').strip()
    date_from = (params.get('date_from', [''])[0] or '').strip()
    date_to = (params.get('date_to', [''])[0] or '').strip()

    if keyword:
        wheres.append('(code LIKE ? OR name LIKE ? OR content_title LIKE ? OR content_ref LIKE ?)')
        kw = f'%{keyword}%'
        args += [kw, kw, kw, kw]
    if channel:
        wheres.append("COALESCE(NULLIF(source_channel,''),'system') = ?")
        args.append(channel)
    if tag:
        wheres.append("COALESCE(NULLIF(reason_tag,''),'未标注') = ?")
        args.append(tag)
    if status:
        wheres.append("COALESCE(NULLIF(review_status,''),'未复盘') = ?")
        args.append(status)
    if date_from:
        wheres.append('pick_date >= ?')
        args.append(date_from)
    if date_to:
        wheres.append('pick_date <= ?')
        args.append(date_to)

    sql_where = (' WHERE ' + ' AND '.join(wheres)) if wheres else ''
    return sql_where, args


def render_dashboard(params=None, flash=''):
    params = params or {}
    stats = q('SELECT COUNT(*) AS total FROM picks')
    total = stats[0]['total'] if stats else 0
    by_channel = q("SELECT COALESCE(NULLIF(source_channel,''),'system') AS name, COUNT(*) AS cnt FROM picks GROUP BY name ORDER BY cnt DESC")
    by_tag = q("SELECT COALESCE(NULLIF(reason_tag,''),'未标注') AS name, COUNT(*) AS cnt FROM picks GROUP BY name ORDER BY cnt DESC")
    by_status = q("SELECT COALESCE(NULLIF(review_status,''),'未复盘') AS name, COUNT(*) AS cnt FROM picks GROUP BY name ORDER BY cnt DESC")
    by_content = q("SELECT COALESCE(NULLIF(content_title,''),'未绑定内容') AS name, COUNT(*) AS cnt FROM picks GROUP BY name ORDER BY cnt DESC LIMIT 10")

    where, args = filter_where(params)
    latest = q(f"SELECT pick_date, code, name, pick_price, source_channel, reason_tag, review_status, content_title FROM picks {where} ORDER BY pick_date DESC, code ASC LIMIT 50", args)
    filter_count = q(f"SELECT COUNT(*) AS cnt FROM picks {where}", args)[0]['cnt']

    channel_opts = ''.join([f"<option value='{esc(r['name'])}' {'selected' if (params.get('channel',[''])[0] == r['name']) else ''}>{esc(r['name'])}</option>" for r in by_channel])
    tag_opts = ''.join([f"<option value='{esc(r['name'])}' {'selected' if (params.get('tag',[''])[0] == r['name']) else ''}>{esc(r['name'])}</option>" for r in by_tag])
    status_opts = ''.join([f"<option value='{esc(r['name'])}' {'selected' if (params.get('status',[''])[0] == r['name']) else ''}>{esc(r['name'])}</option>" for r in by_status])

    latest_rows = ''.join([
        f"<tr><td>{esc(r['pick_date'])}</td><td>{esc(r['name'])}</td><td>{esc(r['code'])}</td><td>{esc(r['pick_price'])}</td><td>{esc(r['source_channel'])}</td><td>{esc(r['reason_tag'])}</td><td>{esc(r['review_status'])}</td><td>{esc(r['content_title'])}</td></tr>"
        for r in latest
    ]) or '<tr><td colspan="8">暂无数据</td></tr>'

    flash_html = f'<div class="flash">{esc(flash)}</div>' if flash else ''
    keyword = esc((params.get('keyword', [''])[0] or '').strip())
    date_from = esc((params.get('date_from', [''])[0] or '').strip())
    date_to = esc((params.get('date_to', [''])[0] or '').strip())

    return f'''<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>宣传票复盘系统 v3.3</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f6f7fb;color:#1f2937;margin:0;padding:24px}}
.wrap{{max-width:1280px;margin:0 auto}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}}
.grid2{{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}}
.card{{background:#fff;border-radius:16px;padding:18px;box-shadow:0 6px 20px rgba(0,0,0,.06)}}
h1,h2{{margin:0 0 12px}} .muted{{color:#6b7280;font-size:14px}} .num{{font-size:32px;font-weight:700}}
ul{{margin:0;padding-left:18px}} table{{width:100%;border-collapse:collapse}} th,td{{padding:10px;border-bottom:1px solid #eee;text-align:left;font-size:14px}} th{{background:#fafafa}}
.section{{margin-top:20px}} input,select,textarea{{width:100%;padding:10px;border:1px solid #d1d5db;border-radius:10px;box-sizing:border-box}} textarea{{min-height:90px}} .formgrid{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}} button{{background:#111827;color:#fff;border:0;border-radius:10px;padding:10px 16px;cursor:pointer}} .hint{{font-size:13px;color:#6b7280}} a.btn{{display:inline-block;background:#111827;color:#fff;text-decoration:none;padding:10px 16px;border-radius:10px;margin-right:8px}}
.bar-row{{display:grid;grid-template-columns:120px 1fr 48px;gap:10px;align-items:center;margin:8px 0}} .bar-track{{height:12px;background:#eef2ff;border-radius:999px;overflow:hidden}} .bar-fill{{height:100%;border-radius:999px}} .bar-label,.bar-value{{font-size:13px}} .flash{{background:#ecfdf5;color:#065f46;border:1px solid #a7f3d0;padding:10px 12px;border-radius:12px;margin-top:16px}}
</style></head><body><div class="wrap">
<h1>宣传票复盘系统 v3.3</h1>
<div class="muted">更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} · 已启用密码保护 · 本地端口 {PORT}</div>
{flash_html}
<div class="grid section">
<div class="card"><div class="muted">累计记录</div><div class="num">{total}</div></div>
<div class="card"><div class="muted">渠道数</div><div class="num">{len(by_channel)}</div></div>
<div class="card"><div class="muted">标签数</div><div class="num">{len(by_tag)}</div></div>
<div class="card"><div class="muted">复盘状态数</div><div class="num">{len(by_status)}</div></div>
</div>
<div class="grid2 section">
<div class="card"><h2>渠道分布图</h2>{bar_html(by_channel, color='#4f46e5')}</div>
<div class="card"><h2>内容联动 Top10 图</h2>{bar_html(by_content, color='#059669')}</div>
</div>
<div class="grid2 section">
<div class="card"><h2>标签分布图</h2>{bar_html(by_tag, color='#dc2626')}</div>
<div class="card"><h2>人工复盘状态图</h2>{bar_html(by_status, color='#d97706')}</div>
</div>
<div class="section card">
<h2>筛选 / 搜索</h2>
<form method="get" action="/">
<div class="formgrid">
<div><label>关键词</label><input name="keyword" value="{keyword}" placeholder="股票代码/名称/内容标题"></div>
<div><label>渠道</label><select name="channel"><option value="">全部</option>{channel_opts}</select></div>
<div><label>标签</label><select name="tag"><option value="">全部</option>{tag_opts}</select></div>
<div><label>复盘状态</label><select name="status"><option value="">全部</option>{status_opts}</select></div>
<div><label>开始日期</label><input type="date" name="date_from" value="{date_from}"></div>
<div><label>结束日期</label><input type="date" name="date_to" value="{date_to}"></div>
</div>
<div style="margin-top:12px"><button type="submit">筛选结果</button> <a class="btn" href="/">清空筛选</a></div>
<div class="hint" style="margin-top:8px">当前筛选结果：{filter_count} 条</div>
</form>
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
</form>
</div>
<div class="section card">
<h2>快捷入口</h2>
<p><a class="btn" href="/export">导出当前记录 JSON</a><a class="btn" href="/logout">退出登录</a></p>
</div>
<div class="section card">
<h2>最新记录</h2>
<table><thead><tr><th>日期</th><th>股票</th><th>代码</th><th>推荐价</th><th>渠道</th><th>标签</th><th>复盘结论</th><th>内容标题</th></tr></thead><tbody>{latest_rows}</tbody></table>
</div>
</div></body></html>'''


def render_login(error=''):
    err = f'<div class="err">{esc(error)}</div>' if error else ''
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>登录宣传票复盘系统</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f6f7fb;padding:24px}}.box{{max-width:420px;margin:10vh auto;background:#fff;padding:24px;border-radius:16px;box-shadow:0 6px 20px rgba(0,0,0,.06)}}input{{width:100%;padding:12px;border:1px solid #d1d5db;border-radius:10px;box-sizing:border-box}}button{{margin-top:12px;width:100%;padding:12px;background:#111827;color:#fff;border:0;border-radius:10px}}.muted{{color:#6b7280;font-size:14px}}.err{{background:#fef2f2;color:#991b1b;border:1px solid #fecaca;padding:10px;border-radius:10px;margin:12px 0}}</style></head><body><div class="box"><h1>登录宣传票复盘系统</h1><div class="muted">v3.3 已启用访问密码保护</div>{err}<form method="post" action="/login"><input type="password" name="password" placeholder="请输入访问密码" required><button type="submit">登录</button></form></div></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def cookies(self):
        return parse_cookies(self.headers.get('Cookie'))

    def authed(self):
        return self.cookies().get(COOKIE_NAME) == PANEL_PASSWORD

    def _send(self, code, body, content_type='text/html; charset=utf-8', extra_headers=None):
        body_bytes = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body_bytes)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body_bytes)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/health':
            self._send(200, 'ok', 'text/plain; charset=utf-8')
            return
        if parsed.path == '/logout':
            self.send_response(303)
            self.send_header('Set-Cookie', f'{COOKIE_NAME}=; Path=/; Max-Age=0')
            self.send_header('Location', '/login')
            self.end_headers()
            return
        if parsed.path == '/login':
            self._send(200, render_login())
            return
        if not self.authed():
            self.send_response(303)
            self.send_header('Location', '/login')
            self.end_headers()
            return
        if parsed.path == '/':
            params = parse_qs(parsed.query)
            self._send(200, render_dashboard(params))
        elif parsed.path == '/export':
            rows = q('SELECT * FROM picks ORDER BY pick_date DESC, code ASC')
            self._send(200, json.dumps(rows, ensure_ascii=False, indent=2), 'application/json; charset=utf-8')
        else:
            self._send(404, 'not found', 'text/plain; charset=utf-8')

    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length).decode('utf-8')
        data = {k: v[0] for k, v in parse_qs(raw).items()}
        if self.path == '/login':
            if data.get('password', '') == PANEL_PASSWORD:
                self.send_response(303)
                self.send_header('Set-Cookie', f'{COOKIE_NAME}={PANEL_PASSWORD}; Path=/; HttpOnly')
                self.send_header('Location', '/')
                self.end_headers()
            else:
                self._send(200, render_login('密码不对，再试一次'))
            return
        if not self.authed():
            self.send_response(303)
            self.send_header('Location', '/login')
            self.end_headers()
            return
        if self.path == '/add':
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
            self.send_header('Location', '/?saved=1')
            self.end_headers()
            return
        self._send(404, 'not found', 'text/plain; charset=utf-8')


if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f'v3.3 server running on http://0.0.0.0:{PORT}')
    print(f'panel password: {PANEL_PASSWORD}')
    server.serve_forever()
