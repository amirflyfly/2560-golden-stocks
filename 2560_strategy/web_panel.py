import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlencode
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


def ensure_schema():
    conn = db_conn()
    try:
        cur = conn.cursor()
        cols = [r['name'] for r in cur.execute("PRAGMA table_info(picks)").fetchall()]
        if 'archived' not in cols:
            cur.execute("ALTER TABLE picks ADD COLUMN archived INTEGER DEFAULT 0")
        conn.commit()
    finally:
        conn.close()


ensure_schema()


def q(sql, args=()):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def q1(sql, args=()):
    rows = q(sql, args)
    return rows[0] if rows else None


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


def bar_html(rows, label_key='name', value_key='cnt', color='#4f46e5', empty_text='暂无数据'):
    if not rows:
        return f'<div class="muted">{esc(empty_text)}</div>'
    maxv = max([r.get(value_key, 0) or 0 for r in rows]) or 1
    items = []
    for r in rows:
        name = esc(r.get(label_key))
        val = r.get(value_key, 0) or 0
        width = max(8, int(val / maxv * 100))
        items.append(
            f'''<div class="bar-row"><div class="bar-label">{name}</div><div class="bar-track"><div class="bar-fill" style="width:{width}%;background:{color}"></div></div><div class="bar-value">{val}</div></div>'''
        )
    return ''.join(items)


def build_query_string(params):
    pairs = []
    for k, values in (params or {}).items():
        if not isinstance(values, list):
            values = [values]
        for v in values:
            if str(v).strip() != '':
                pairs.append((k, v))
    return urlencode(pairs)


def filter_where(params):
    wheres = []
    args = []
    keyword = (params.get('keyword', [''])[0] or '').strip()
    channel = (params.get('channel', [''])[0] or '').strip()
    tag = (params.get('tag', [''])[0] or '').strip()
    status = (params.get('status', [''])[0] or '').strip()
    date_from = (params.get('date_from', [''])[0] or '').strip()
    date_to = (params.get('date_to', [''])[0] or '').strip()
    archive = (params.get('archive', ['active'])[0] or 'active').strip()

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
    if archive == 'archived':
        wheres.append('COALESCE(archived, 0) = 1')
    elif archive != 'all':
        wheres.append('COALESCE(archived, 0) = 0')

    sql_where = (' WHERE ' + ' AND '.join(wheres)) if wheres else ''
    return sql_where, args


def get_flash(params):
    mapping = {
        'saved': '已保存记录',
        'updated': '已更新记录',
        'archived': '已归档记录',
        'unarchived': '已恢复记录',
        'deleted': '已删除记录',
    }
    for key, text in mapping.items():
        if params.get(key, [''])[0] == '1':
            return text
    return ''


def render_dashboard(params=None):
    params = params or {}
    flash = get_flash(params)

    overview = q1(
        '''SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN COALESCE(archived,0)=0 THEN 1 ELSE 0 END) AS active_total,
            SUM(CASE WHEN COALESCE(archived,0)=1 THEN 1 ELSE 0 END) AS archived_total,
            COUNT(DISTINCT COALESCE(NULLIF(source_channel,''),'system')) AS channel_total,
            COUNT(DISTINCT COALESCE(NULLIF(reason_tag,''),'未标注')) AS tag_total,
            COUNT(DISTINCT COALESCE(NULLIF(review_status,''),'未复盘')) AS status_total
        FROM picks'''
    ) or {}

    by_channel = q("SELECT COALESCE(NULLIF(source_channel,''),'system') AS name, COUNT(*) AS cnt FROM picks WHERE COALESCE(archived,0)=0 GROUP BY name ORDER BY cnt DESC")
    by_tag = q("SELECT COALESCE(NULLIF(reason_tag,''),'未标注') AS name, COUNT(*) AS cnt FROM picks WHERE COALESCE(archived,0)=0 GROUP BY name ORDER BY cnt DESC")
    by_status = q("SELECT COALESCE(NULLIF(review_status,''),'未复盘') AS name, COUNT(*) AS cnt FROM picks WHERE COALESCE(archived,0)=0 GROUP BY name ORDER BY cnt DESC")
    by_content = q("SELECT COALESCE(NULLIF(content_title,''),'未绑定内容') AS name, COUNT(*) AS cnt FROM picks WHERE COALESCE(archived,0)=0 GROUP BY name ORDER BY cnt DESC LIMIT 10")
    worthy_tags = q("SELECT COALESCE(NULLIF(reason_tag,''),'未标注') AS name, COUNT(*) AS cnt FROM picks WHERE COALESCE(archived,0)=0 AND COALESCE(NULLIF(review_status,''),'未复盘')='值得复讲' GROUP BY name ORDER BY cnt DESC LIMIT 10")
    trend_30d = q("SELECT pick_date AS name, COUNT(*) AS cnt FROM picks WHERE COALESCE(archived,0)=0 AND date(pick_date) >= date('now','-29 day') GROUP BY pick_date ORDER BY pick_date ASC")

    where, args = filter_where(params)
    latest = q(
        f'''SELECT id, pick_date, code, name, pick_price, source_channel, reason_tag, review_status, content_title, COALESCE(archived,0) AS archived
            FROM picks {where}
            ORDER BY pick_date DESC, id DESC LIMIT 80''',
        args,
    )
    filter_count = q1(f"SELECT COUNT(*) AS cnt FROM picks {where}", args)['cnt']

    channel_opts = ''.join([
        f"<option value='{esc(r['name'])}' {'selected' if (params.get('channel',[''])[0] == r['name']) else ''}>{esc(r['name'])}</option>"
        for r in by_channel
    ])
    tag_opts = ''.join([
        f"<option value='{esc(r['name'])}' {'selected' if (params.get('tag',[''])[0] == r['name']) else ''}>{esc(r['name'])}</option>"
        for r in by_tag
    ])
    status_opts = ''.join([
        f"<option value='{esc(r['name'])}' {'selected' if (params.get('status',[''])[0] == r['name']) else ''}>{esc(r['name'])}</option>"
        for r in by_status
    ])

    latest_rows = ''.join([
        f"<tr>"
        f"<td>{esc(r['pick_date'])}</td>"
        f"<td>{esc(r['name'])}</td>"
        f"<td>{esc(r['code'])}</td>"
        f"<td>{esc(r['pick_price'])}</td>"
        f"<td>{esc(r['source_channel'])}</td>"
        f"<td>{esc(r['reason_tag'])}</td>"
        f"<td>{esc(r['review_status'])}</td>"
        f"<td>{esc(r['content_title'])}</td>"
        f"<td><span class='badge {'badge-archived' if r['archived'] else 'badge-active'}'>{'已归档' if r['archived'] else '使用中'}</span></td>"
        f"<td>"
        f"<a class='txtbtn' href='/edit?id={r['id']}'>编辑</a>"
        f"<form method='post' action='/{'unarchive' if r['archived'] else 'archive'}' class='inline-form'>"
        f"<input type='hidden' name='id' value='{r['id']}'>"
        f"<button type='submit' class='linkbtn'>{'恢复' if r['archived'] else '归档'}</button>"
        f"</form>"
        f"<form method='post' action='/delete' class='inline-form' onsubmit=\"return confirm('确认删除这条记录？删除后不可恢复。')\">"
        f"<input type='hidden' name='id' value='{r['id']}'>"
        f"<button type='submit' class='linkbtn danger'>删除</button>"
        f"</form>"
        f"</td>"
        f"</tr>"
        for r in latest
    ]) or '<tr><td colspan="10">暂无数据</td></tr>'

    flash_html = f'<div class="flash">{esc(flash)}</div>' if flash else ''
    keyword = esc((params.get('keyword', [''])[0] or '').strip())
    date_from = esc((params.get('date_from', [''])[0] or '').strip())
    date_to = esc((params.get('date_to', [''])[0] or '').strip())
    archive_mode = (params.get('archive', ['active'])[0] or 'active').strip()
    filter_query = build_query_string(params)
    export_href = '/export' + (f'?{filter_query}' if filter_query else '')

    return f'''<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>宣传票复盘系统 v3.4</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f6f7fb;color:#1f2937;margin:0;padding:24px}}
.wrap{{max-width:1380px;margin:0 auto}}
.grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:16px}}
.grid2{{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}}
.grid3{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}
.card{{background:#fff;border-radius:16px;padding:18px;box-shadow:0 6px 20px rgba(0,0,0,.06)}}
h1,h2{{margin:0 0 12px}} .muted{{color:#6b7280;font-size:14px}} .num{{font-size:32px;font-weight:700}}
ul{{margin:0;padding-left:18px}} table{{width:100%;border-collapse:collapse}} th,td{{padding:10px;border-bottom:1px solid #eee;text-align:left;font-size:14px;vertical-align:top}} th{{background:#fafafa}}
.section{{margin-top:20px}} input,select,textarea{{width:100%;padding:10px;border:1px solid #d1d5db;border-radius:10px;box-sizing:border-box}} textarea{{min-height:90px}} .formgrid{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}} button{{background:#111827;color:#fff;border:0;border-radius:10px;padding:10px 16px;cursor:pointer}} .hint{{font-size:13px;color:#6b7280}} a.btn{{display:inline-block;background:#111827;color:#fff;text-decoration:none;padding:10px 16px;border-radius:10px;margin-right:8px}}
.bar-row{{display:grid;grid-template-columns:140px 1fr 48px;gap:10px;align-items:center;margin:8px 0}} .bar-track{{height:12px;background:#eef2ff;border-radius:999px;overflow:hidden}} .bar-fill{{height:100%;border-radius:999px}} .bar-label,.bar-value{{font-size:13px}} .flash{{background:#ecfdf5;color:#065f46;border:1px solid #a7f3d0;padding:10px 12px;border-radius:12px;margin-top:16px}}
.inline-form{{display:inline}} .linkbtn{{background:none;color:#2563eb;padding:0 6px;border:none;border-radius:0}} .linkbtn.danger{{color:#dc2626}} .txtbtn{{color:#2563eb;text-decoration:none;padding-right:6px}} .badge{{display:inline-block;padding:4px 8px;border-radius:999px;font-size:12px}} .badge-active{{background:#dcfce7;color:#166534}} .badge-archived{{background:#f3f4f6;color:#4b5563}}
.topline{{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap}}
@media (max-width: 980px){{.grid,.grid2,.grid3,.formgrid{{grid-template-columns:1fr}} body{{padding:16px}} .wrap{{max-width:100%}} table{{display:block;overflow:auto}}}}
</style></head><body><div class="wrap">
<div class="topline">
<div>
<h1>宣传票复盘系统 v3.4</h1>
<div class="muted">更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} · 已启用密码保护 · 本地端口 {PORT}</div>
</div>
<div class="muted">本次新增：编辑页 / 归档删除 / 进阶图表</div>
</div>
{flash_html}
<div class="grid section">
<div class="card"><div class="muted">累计记录</div><div class="num">{overview.get('total', 0)}</div></div>
<div class="card"><div class="muted">使用中</div><div class="num">{overview.get('active_total', 0) or 0}</div></div>
<div class="card"><div class="muted">已归档</div><div class="num">{overview.get('archived_total', 0) or 0}</div></div>
<div class="card"><div class="muted">渠道数</div><div class="num">{overview.get('channel_total', 0)}</div></div>
<div class="card"><div class="muted">标签数</div><div class="num">{overview.get('tag_total', 0)}</div></div>
</div>
<div class="grid2 section">
<div class="card"><h2>渠道分布图</h2>{bar_html(by_channel, color='#4f46e5')}</div>
<div class="card"><h2>内容联动 Top10 图</h2>{bar_html(by_content, color='#059669')}</div>
</div>
<div class="grid3 section">
<div class="card"><h2>标签分布图</h2>{bar_html(by_tag, color='#dc2626')}</div>
<div class="card"><h2>人工复盘状态图</h2>{bar_html(by_status, color='#d97706')}</div>
<div class="card"><h2>值得复讲标签 Top10</h2>{bar_html(worthy_tags, color='#0ea5e9', empty_text='暂无值得复讲数据')}</div>
</div>
<div class="section card">
<h2>近 30 天录入趋势</h2>
<div class="muted" style="margin-bottom:10px">看最近录入节奏，适合判断宣传票复盘是否持续在做</div>
{bar_html(trend_30d, color='#7c3aed', empty_text='近30天暂无数据')}
</div>
<div class="section card">
<h2>筛选 / 搜索</h2>
<form method="get" action="/">
<div class="formgrid">
<div><label>关键词</label><input name="keyword" value="{keyword}" placeholder="股票代码/股票名称/内容标题/内容编号"></div>
<div><label>渠道</label><select name="channel"><option value="">全部</option>{channel_opts}</select></div>
<div><label>标签</label><select name="tag"><option value="">全部</option>{tag_opts}</select></div>
<div><label>复盘状态</label><select name="status"><option value="">全部</option>{status_opts}</select></div>
<div><label>开始日期</label><input type="date" name="date_from" value="{date_from}"></div>
<div><label>结束日期</label><input type="date" name="date_to" value="{date_to}"></div>
<div><label>记录范围</label><select name="archive"><option value="active" {'selected' if archive_mode == 'active' else ''}>仅使用中</option><option value="archived" {'selected' if archive_mode == 'archived' else ''}>仅已归档</option><option value="all" {'selected' if archive_mode == 'all' else ''}>全部记录</option></select></div>
</div>
<div style="margin-top:12px"><button type="submit">筛选结果</button> <a class="btn" href="/">清空筛选</a></div>
<div class="hint" style="margin-top:8px">当前筛选结果：{filter_count} 条</div>
</form>
</div>
<div class="section card">
<h2>新增记录</h2>
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
<p><a class="btn" href="{export_href}">导出当前筛选 JSON</a><a class="btn" href="/logout">退出登录</a></p>
</div>
<div class="section card">
<h2>最新记录</h2>
<table><thead><tr><th>日期</th><th>股票</th><th>代码</th><th>推荐价</th><th>渠道</th><th>标签</th><th>复盘结论</th><th>内容标题</th><th>状态</th><th>操作</th></tr></thead><tbody>{latest_rows}</tbody></table>
</div>
</div></body></html>'''


def render_login(error=''):
    err = f'<div class="err">{esc(error)}</div>' if error else ''
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>登录宣传票复盘系统</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f6f7fb;padding:24px}}.box{{max-width:420px;margin:10vh auto;background:#fff;padding:24px;border-radius:16px;box-shadow:0 6px 20px rgba(0,0,0,.06)}}input{{width:100%;padding:12px;border:1px solid #d1d5db;border-radius:10px;box-sizing:border-box}}button{{margin-top:12px;width:100%;padding:12px;background:#111827;color:#fff;border:0;border-radius:10px}}.muted{{color:#6b7280;font-size:14px}}.err{{background:#fef2f2;color:#991b1b;border:1px solid #fecaca;padding:10px;border-radius:10px;margin:12px 0}}</style></head><body><div class="box"><h1>登录宣传票复盘系统</h1><div class="muted">v3.4 已启用访问密码保护</div>{err}<form method="post" action="/login"><input type="password" name="password" placeholder="请输入访问密码" required><button type="submit">登录</button></form></div></body></html>'''


def render_edit_form(record):
    if not record:
        return '<!doctype html><html><body>记录不存在</body></html>'
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>编辑记录</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f6f7fb;padding:24px;color:#1f2937}}.box{{max-width:960px;margin:0 auto;background:#fff;padding:24px;border-radius:16px;box-shadow:0 6px 20px rgba(0,0,0,.06)}}input,select,textarea{{width:100%;padding:10px;border:1px solid #d1d5db;border-radius:10px;box-sizing:border-box}}textarea{{min-height:100px}}.formgrid{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}button{{background:#111827;color:#fff;border:0;border-radius:10px;padding:10px 16px;cursor:pointer}}a.btn{{display:inline-block;background:#fff;color:#111827;text-decoration:none;padding:10px 16px;border-radius:10px;border:1px solid #d1d5db;margin-left:8px}}@media (max-width: 900px){{.formgrid{{grid-template-columns:1fr}}}}</style></head><body><div class="box"><h1>编辑宣传票记录</h1><div style="color:#6b7280;margin-bottom:16px">记录 ID：{record['id']} · 你可以直接修改后保存</div><form method="post" action="/update"><input type="hidden" name="id" value="{record['id']}"><div class="formgrid"><div><label>日期</label><input name="pick_date" value="{esc(record['pick_date'])}" required></div><div><label>股票代码</label><input name="code" value="{esc(record['code'])}" required></div><div><label>股票名称</label><input name="name" value="{esc(record['name'])}" required></div><div><label>推荐价</label><input name="pick_price" value="{esc(record['pick_price'])}" required></div><div><label>信号</label><input name="signal" value="{esc(record['signal'])}"></div><div><label>渠道</label><input name="source_channel" value="{esc(record['source_channel'])}"></div><div><label>标签</label><input name="reason_tag" value="{esc(record['reason_tag'])}"></div><div><label>复盘结论</label><select name="review_status"><option {'selected' if label(record['review_status'],'') == '未复盘' else ''}>未复盘</option><option {'selected' if label(record['review_status'],'') == '值得复讲' else ''}>值得复讲</option><option {'selected' if label(record['review_status'],'') == '逻辑一般' else ''}>逻辑一般</option><option {'selected' if label(record['review_status'],'') == '不建议再提' else ''}>不建议再提</option></select></div><div><label>内容标题</label><input name="content_title" value="{esc(record['content_title'])}"></div><div><label>内容编号/链接</label><input name="content_ref" value="{esc(record['content_ref'])}"></div></div><div style="margin-top:12px"><label>备注/复盘评论</label><textarea name="note">{esc(record['note'])}</textarea></div><div style="margin-top:16px"><button type="submit">保存修改</button><a class="btn" href="/">返回面板</a></div></form></div></body></html>'''


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

    def _redirect(self, location, cookie=None):
        self.send_response(303)
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.send_header('Location', location)
        self.end_headers()

    def _read_post(self):
        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length).decode('utf-8')
        return {k: v[0] for k, v in parse_qs(raw).items()}

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/health':
            self._send(200, 'ok', 'text/plain; charset=utf-8')
            return
        if parsed.path == '/logout':
            self._redirect('/login', f'{COOKIE_NAME}=; Path=/; Max-Age=0')
            return
        if parsed.path == '/login':
            self._send(200, render_login())
            return
        if not self.authed():
            self._redirect('/login')
            return
        if parsed.path == '/':
            params = parse_qs(parsed.query)
            self._send(200, render_dashboard(params))
        elif parsed.path == '/edit':
            params = parse_qs(parsed.query)
            record_id = params.get('id', [''])[0]
            record = q1('SELECT * FROM picks WHERE id=?', (record_id,))
            self._send(200, render_edit_form(record))
        elif parsed.path == '/export':
            params = parse_qs(parsed.query)
            where, args = filter_where(params)
            rows = q(f'SELECT * FROM picks {where} ORDER BY pick_date DESC, id DESC', args)
            self._send(200, json.dumps(rows, ensure_ascii=False, indent=2), 'application/json; charset=utf-8')
        else:
            self._send(404, 'not found', 'text/plain; charset=utf-8')

    def do_POST(self):
        data = self._read_post()
        if self.path == '/login':
            if data.get('password', '') == PANEL_PASSWORD:
                self._redirect('/', f'{COOKIE_NAME}={PANEL_PASSWORD}; Path=/; HttpOnly')
            else:
                self._send(200, render_login('密码不对，再试一次'))
            return
        if not self.authed():
            self._redirect('/login')
            return
        if self.path == '/add':
            execute(
                '''INSERT OR REPLACE INTO picks
                (pick_date, code, name, pick_price, signal, source, source_channel, reason_tag, note, review_status, review_comment, content_title, content_ref, archived)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)''',
                (
                    data.get('pick_date', ''), data.get('code', ''), data.get('name', ''), float(data.get('pick_price', '0') or 0),
                    data.get('signal', ''), 'webform', data.get('source_channel', 'web'), data.get('reason_tag', ''), data.get('note', ''),
                    data.get('review_status', '未复盘'), data.get('note', ''), data.get('content_title', ''), data.get('content_ref', '')
                )
            )
            self._redirect('/?saved=1')
            return
        if self.path == '/update':
            execute(
                '''UPDATE picks SET
                    pick_date=?, code=?, name=?, pick_price=?, signal=?, source_channel=?, reason_tag=?, note=?,
                    review_status=?, review_comment=?, content_title=?, content_ref=?
                   WHERE id=?''',
                (
                    data.get('pick_date', ''), data.get('code', ''), data.get('name', ''), float(data.get('pick_price', '0') or 0),
                    data.get('signal', ''), data.get('source_channel', ''), data.get('reason_tag', ''), data.get('note', ''),
                    data.get('review_status', '未复盘'), data.get('note', ''), data.get('content_title', ''), data.get('content_ref', ''), data.get('id', '')
                )
            )
            self._redirect('/?updated=1')
            return
        if self.path == '/archive':
            execute('UPDATE picks SET archived=1 WHERE id=?', (data.get('id', ''),))
            self._redirect('/?archived=1')
            return
        if self.path == '/unarchive':
            execute('UPDATE picks SET archived=0 WHERE id=?', (data.get('id', ''),))
            self._redirect('/?unarchived=1')
            return
        if self.path == '/delete':
            execute('DELETE FROM picks WHERE id=?', (data.get('id', ''),))
            self._redirect('/?deleted=1')
            return
        self._send(404, 'not found', 'text/plain; charset=utf-8')


if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f'v3.4 server running on http://0.0.0.0:{PORT}')
    print(f'panel password: {PANEL_PASSWORD}')
    server.serve_forever()
