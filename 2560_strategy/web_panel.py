import csv
import io
import json
import html
import secrets
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlencode
from http.server import BaseHTTPRequestHandler, HTTPServer

from backend.repositories.db import ensure_schema, q, q1, execute, execute_many

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
DB_PATH = DATA_DIR / 'picks.db'
SECRET_PATH = DATA_DIR / 'web_panel_secret.txt'
PORT = 8765
PAGE_SIZE = 20
COOKIE_NAME = 'promo_panel_auth'

REVIEW_STATUS_OPTIONS = ['未复盘', '值得复讲', '逻辑一般', '不建议再提']
RESULT_GRADE_OPTIONS = ['S', 'A', 'B', 'C', '待定']
DEAL_STATUS_OPTIONS = ['未成交', '已咨询', '已成交', '待跟进']
SPREAD_OPTIONS = ['否', '是']
EXPORT_COLUMNS = [
    'id', 'pick_date', 'code', 'name', 'pick_price', 'signal', 'source', 'source_channel',
    'reason_tag', 'review_status', 'result_grade', 'inquiry_count', 'deal_status',
    'secondary_spread', 'content_title', 'content_ref', 'note', 'archived', 'created_at'
]


def ensure_secret():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SECRET_PATH.exists():
        return SECRET_PATH.read_text(encoding='utf-8').strip()
    secret = secrets.token_urlsafe(8)
    SECRET_PATH.write_text(secret, encoding='utf-8')
    return secret


PANEL_PASSWORD = ensure_secret()


ensure_schema()


def log_action(action, target_ids=None, detail=''):
    target_ids = target_ids or []
    execute(
        'INSERT INTO operation_logs (action, target_ids, detail) VALUES (?, ?, ?)',
        (action, ','.join(str(i) for i in target_ids), detail[:1000]),
    )


def label(v, default='-'):
    if v is None:
        return default
    s = str(v).strip()
    return s if s and s.lower() != 'nan' else default


def esc(v):
    return html.escape(label(v, ''))


def num(v, default=0.0):
    try:
        return float(v or 0)
    except Exception:
        return default


def int_num(v, default=0):
    try:
        return int(float(v or 0))
    except Exception:
        return default


def parse_cookies(header):
    cookies = {}
    if not header:
        return cookies
    for part in header.split(';'):
        if '=' in part:
            k, v = part.strip().split('=', 1)
            cookies[k] = v
    return cookies


def parse_multi_post(raw):
    parsed = parse_qs(raw, keep_blank_values=True)
    return {k: v if len(v) > 1 else v[0] for k, v in parsed.items()}


def as_list(data, key):
    v = data.get(key, [])
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip() != '']
    return [str(v)] if str(v).strip() != '' else []


def build_query_string(params):
    pairs = []
    for k, values in (params or {}).items():
        if not isinstance(values, list):
            values = [values]
        for v in values:
            if str(v).strip() != '':
                pairs.append((k, v))
    return urlencode(pairs)


def select_options(options, selected_value):
    return ''.join([
        f"<option value='{esc(v)}' {'selected' if str(selected_value) == str(v) else ''}>{esc(v)}</option>"
        for v in options
    ])


def bar_html(rows, label_key='name', value_key='cnt', color='#4f46e5', empty_text='暂无数据', suffix=''):
    if not rows:
        return f'<div class="muted">{esc(empty_text)}</div>'
    maxv = max([float(r.get(value_key, 0) or 0) for r in rows]) or 1
    items = []
    for r in rows:
        name = esc(r.get(label_key))
        val = float(r.get(value_key, 0) or 0)
        width = max(8, int(val / maxv * 100))
        display = str(int(round(val))) if abs(val - round(val)) < 1e-9 else f'{val:.1f}'
        if suffix:
            display += suffix
        items.append(f'''<div class="bar-row"><div class="bar-label">{name}</div><div class="bar-track"><div class="bar-fill" style="width:{width}%;background:{color}"></div></div><div class="bar-value">{display}</div></div>''')
    return ''.join(items)


def line_table_html(rows, empty_text='暂无数据', color='#4f46e5'):
    if not rows:
        return f'<div class="muted">{esc(empty_text)}</div>'
    maxv = max([float(r.get('cnt', 0) or 0) for r in rows]) or 1
    html_rows = []
    for r in rows:
        val = float(r.get('cnt', 0) or 0)
        width = max(8, int(val / maxv * 100))
        label_text = esc(r.get('name'))
        display = str(int(round(val))) if abs(val - round(val)) < 1e-9 else f'{val:.1f}'
        html_rows.append(f"<div class='line-row'><div class='line-date'>{label_text}</div><div class='line-track'><div class='line-fill' style='width:{width}%;background:{color}'></div></div><div class='line-value'>{display}</div></div>")
    return ''.join(html_rows)


def render_nav(active='dashboard'):
    items = [
        ('/', 'dashboard', '总览面板'),
        ('/deal-review', 'deal', '成交复盘'),
        ('/leaderboards', 'leaderboards', '排行榜'),
        ('/reports', 'reports', '报表中心'),
    ]
    links = []
    for href, key, title in items:
        cls = 'navlink nav-active' if key == active else 'navlink'
        links.append(f"<a class='{cls}' href='{href}'>{title}</a>")
    return ''.join(links)


def render_pagination(page, total_count, base_params):
    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    if total_pages <= 1:
        return ''
    page = max(1, min(page, total_pages))
    links = []
    for pno in range(1, total_pages + 1):
        params = dict(base_params or {})
        params['page'] = [str(pno)]
        href = '/?' + build_query_string(params)
        cls = 'page-link page-active' if pno == page else 'page-link'
        links.append(f"<a class='{cls}' href='{href}'>{pno}</a>")
    return "<div class='pagination'>" + ''.join(links) + '</div>'


def layout_page(title, body):
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)}</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f6f7fb;color:#1f2937;margin:0;padding:24px}}
.wrap{{max-width:1540px;margin:0 auto}} .card{{background:#fff;border-radius:16px;padding:18px;box-shadow:0 6px 20px rgba(0,0,0,.06)}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}} .grid2{{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}}
.bar-row,.line-row{{display:grid;grid-template-columns:140px 1fr 62px;gap:10px;align-items:center;margin:8px 0}} .bar-track,.line-track{{height:12px;background:#eef2ff;border-radius:999px;overflow:hidden}} .bar-fill,.line-fill{{height:100%;border-radius:999px}}
.muted{{color:#6b7280;font-size:14px}} .num{{font-size:32px;font-weight:700}} .topline{{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap}} a.btn{{display:inline-block;background:#111827;color:#fff;text-decoration:none;padding:10px 16px;border-radius:10px;margin-right:8px}} .nav{{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}} .navlink{{display:inline-block;padding:10px 14px;border-radius:999px;background:#fff;color:#111827;text-decoration:none;border:1px solid #e5e7eb}} .nav-active{{background:#111827;color:#fff;border-color:#111827}} .pagination{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:14px}} .page-link{{display:inline-block;padding:6px 10px;border-radius:10px;background:#fff;color:#111827;text-decoration:none;border:1px solid #e5e7eb}} .page-active{{background:#111827;color:#fff;border-color:#111827}} table{{width:100%;border-collapse:collapse}} th,td{{padding:10px;border-bottom:1px solid #eee;text-align:left;font-size:14px;vertical-align:top}} th{{background:#fafafa}} .tablewrap{{overflow:auto}} @media (max-width:980px){{.grid,.grid2{{grid-template-columns:1fr}} body{{padding:16px}}}}</style></head><body><div class="wrap">{body}</div></body></html>'''


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
    grade = (params.get('grade', [''])[0] or '').strip()
    deal_status = (params.get('deal_status', [''])[0] or '').strip()

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
    if grade:
        wheres.append("COALESCE(NULLIF(result_grade,''),'待定') = ?")
        args.append(grade)
    if deal_status:
        wheres.append("COALESCE(NULLIF(deal_status,''),'未成交') = ?")
        args.append(deal_status)
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
        'saved': '已保存记录', 'updated': '已更新记录', 'archived': '已归档记录', 'unarchived': '已恢复记录',
        'deleted': '已删除记录', 'batch_archived': '已批量归档所选记录', 'batch_unarchived': '已批量恢复所选记录',
        'batch_deleted': '已批量删除所选记录', 'batch_reviewed': '已批量更新复盘状态', 'batch_grade': '已批量更新结果评级',
        'batch_deal': '已批量更新成交状态', 'batch_spread': '已批量更新二次传播状态', 'imported': '已完成批量导入',
    }
    for key, text in mapping.items():
        if params.get(key, [''])[0] == '1':
            return text
    return ''


def bulk_import_from_csv(csv_text):
    csv_text = (csv_text or '').strip()
    if not csv_text:
        return []
    reader = csv.DictReader(io.StringIO(csv_text))
    imported_ids = []
    for row in reader:
        if not any((v or '').strip() for v in row.values()):
            continue
        execute(
            '''INSERT OR REPLACE INTO picks
            (pick_date, code, name, pick_price, signal, source, source_channel, reason_tag, note, review_status, review_comment, content_title, content_ref, archived, result_grade, inquiry_count, deal_status, secondary_spread)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)''',
            (
                (row.get('pick_date') or '').strip(), (row.get('code') or '').strip(), (row.get('name') or '').strip(), num(row.get('pick_price')),
                (row.get('signal') or '').strip(), 'csv-import', (row.get('source_channel') or 'csv').strip(), (row.get('reason_tag') or '').strip(),
                (row.get('note') or '').strip(), (row.get('review_status') or '未复盘').strip(), (row.get('review_comment') or row.get('note') or '').strip(),
                (row.get('content_title') or '').strip(), (row.get('content_ref') or '').strip(), (row.get('result_grade') or '待定').strip(),
                int_num(row.get('inquiry_count')), (row.get('deal_status') or '未成交').strip(), (row.get('secondary_spread') or '否').strip(),
            )
        )
        new_row = q1('SELECT id FROM picks ORDER BY id DESC LIMIT 1')
        if new_row:
            imported_ids.append(new_row['id'])
    return imported_ids


def rows_to_csv(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, '') for k in EXPORT_COLUMNS})
    return output.getvalue()


def get_saved_filters():
    return q('SELECT id, name, query_string, created_at FROM saved_filters ORDER BY id DESC LIMIT 12')


def get_dashboard_order():
    row = q1("SELECT setting_value FROM ui_settings WHERE setting_key='dashboard_order'")
    if not row or not row.get('setting_value'):
        return 'kpi,trend,filters,actions,records,logs'
    return row['setting_value']


def set_dashboard_order(value):
    execute(
        "INSERT INTO ui_settings (setting_key, setting_value, updated_at) VALUES ('dashboard_order', ?, CURRENT_TIMESTAMP) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value, updated_at=CURRENT_TIMESTAMP",
        (value,)
    )


def report_summary_text():
    monthly = monthly_report_rows()
    weekly = weekly_report_rows()
    if not monthly:
        return {'weekly': '当前还没有可总结的周报数据。', 'monthly': '当前还没有可总结的月报数据。'}
    latest = monthly[0]
    month = latest.get('month') or '-'
    total = int(latest.get('total') or 0)
    worthy = int(latest.get('worthy_total') or 0)
    deal = int(latest.get('deal_total') or 0)
    avg_inquiry = latest.get('avg_inquiry') or 0
    worthy_rate = round((worthy / total * 100), 1) if total else 0

    monthly_summary = f"{month} 月共沉淀 {total} 条记录，其中值得复讲 {worthy} 条（{worthy_rate}%），已成交 {deal} 条，平均咨询数 {avg_inquiry}。"
    if worthy_rate >= 30:
        monthly_summary += ' 本月优质内容占比不错，建议继续放大高表现选题。'
    elif worthy_rate > 0:
        monthly_summary += ' 本月已经开始出现优质内容，建议继续复盘高表现标签和渠道。'
    else:
        monthly_summary += ' 本月还没有跑出明显的优质内容，建议重点复盘标签、渠道和内容脚本。'

    weekly_summary = '当前还没有可总结的周报数据。'
    if weekly:
        current_week = weekly[0]
        weekly_total = int(current_week.get('total') or 0)
        weekly_worthy = int(current_week.get('worthy_total') or 0)
        weekly_deal = int(current_week.get('deal_total') or 0)
        weekly_summary = f"最近一周（{current_week.get('period')}）新增 {weekly_total} 条记录，其中值得复讲 {weekly_worthy} 条、已成交 {weekly_deal} 条。"
        if weekly_worthy > 0 or weekly_deal > 0:
            weekly_summary += ' 这一周已经有正向信号，建议继续盯住高表现内容。'
        else:
            weekly_summary += ' 这一周还在积累期，建议继续测试内容角度和渠道组合。'

    boss_summary = f"老板视角可直接看：本月累计 {total} 条，值得复讲 {worthy} 条，已成交 {deal} 条，平均咨询数 {avg_inquiry}。"
    if deal > 0:
        boss_summary += ' 已经有成交反馈，建议优先复用已验证的内容路径。'
    elif worthy > 0:
        boss_summary += ' 已经有优质内容苗头，下一步重点放大高表现方向。'
    else:
        boss_summary += ' 当前还处于测试积累阶段，建议继续扩大样本并优化内容脚本。'
    return {'weekly': weekly_summary, 'monthly': monthly_summary, 'boss': boss_summary}


def monthly_report_rows():
    return q(
        '''SELECT substr(pick_date,1,7) AS month,
                  COUNT(*) AS total,
                  SUM(CASE WHEN COALESCE(NULLIF(review_status,''),'未复盘')='值得复讲' THEN 1 ELSE 0 END) AS worthy_total,
                  SUM(CASE WHEN COALESCE(NULLIF(deal_status,''),'未成交')='已成交' THEN 1 ELSE 0 END) AS deal_total,
                  ROUND(AVG(COALESCE(inquiry_count,0)),1) AS avg_inquiry
           FROM picks GROUP BY month ORDER BY month DESC'''
    )


def weekly_report_rows():
    return q(
        '''SELECT strftime('%Y-W%W', pick_date) AS period,
                  COUNT(*) AS total,
                  SUM(CASE WHEN COALESCE(NULLIF(review_status,''),'未复盘')='值得复讲' THEN 1 ELSE 0 END) AS worthy_total,
                  SUM(CASE WHEN COALESCE(NULLIF(deal_status,''),'未成交')='已成交' THEN 1 ELSE 0 END) AS deal_total
           FROM picks GROUP BY period ORDER BY period DESC LIMIT 12'''
    )


def render_dashboard(params=None):
    params = params or {}
    flash = get_flash(params)
    page = max(1, int((params.get('page', ['1'])[0] or '1')))
    saved_filters = get_saved_filters()
    dashboard_order = get_dashboard_order()
    overview = q1(
        '''SELECT COUNT(*) AS total,
                  SUM(CASE WHEN COALESCE(archived,0)=0 THEN 1 ELSE 0 END) AS active_total,
                  SUM(CASE WHEN COALESCE(NULLIF(deal_status,''),'未成交')='已成交' THEN 1 ELSE 0 END) AS deal_total,
                  SUM(CASE WHEN COALESCE(NULLIF(secondary_spread,''),'否')='是' THEN 1 ELSE 0 END) AS spread_total,
                  SUM(CASE WHEN COALESCE(NULLIF(review_status,''),'未复盘')='值得复讲' THEN 1 ELSE 0 END) AS worthy_total
           FROM picks'''
    ) or {}
    kpi = q1(
        '''SELECT SUM(CASE WHEN date(pick_date) >= date('now','weekday 1','-7 days') THEN 1 ELSE 0 END) AS week_new,
                  SUM(CASE WHEN date(pick_date) >= date('now','-6 day') THEN 1 ELSE 0 END) AS last7_new,
                  SUM(CASE WHEN date(pick_date) >= date('now','-29 day') THEN 1 ELSE 0 END) AS last30_new,
                  ROUND(100.0 * SUM(CASE WHEN COALESCE(NULLIF(review_status,''),'未复盘')='值得复讲' THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0), 1) AS worthy_rate,
                  ROUND(AVG(COALESCE(inquiry_count,0)), 1) AS avg_inquiry
           FROM picks WHERE COALESCE(archived,0)=0'''
    ) or {}
    by_channel = q("SELECT COALESCE(NULLIF(source_channel,''),'system') AS name, COUNT(*) AS cnt FROM picks WHERE COALESCE(archived,0)=0 GROUP BY name ORDER BY cnt DESC")
    by_tag = q("SELECT COALESCE(NULLIF(reason_tag,''),'未标注') AS name, COUNT(*) AS cnt FROM picks WHERE COALESCE(archived,0)=0 GROUP BY name ORDER BY cnt DESC")
    by_status = q("SELECT COALESCE(NULLIF(review_status,''),'未复盘') AS name, COUNT(*) AS cnt FROM picks WHERE COALESCE(archived,0)=0 GROUP BY name ORDER BY cnt DESC")
    by_grade = q("SELECT COALESCE(NULLIF(result_grade,''),'待定') AS name, COUNT(*) AS cnt FROM picks WHERE COALESCE(archived,0)=0 GROUP BY name ORDER BY cnt DESC")
    by_deal = q("SELECT COALESCE(NULLIF(deal_status,''),'未成交') AS name, COUNT(*) AS cnt FROM picks WHERE COALESCE(archived,0)=0 GROUP BY name ORDER BY cnt DESC")
    trend_30d = q("SELECT pick_date AS name, COUNT(*) AS cnt FROM picks WHERE COALESCE(archived,0)=0 AND date(pick_date) >= date('now','-29 day') GROUP BY pick_date ORDER BY pick_date ASC")
    worthy_trend = q("SELECT pick_date AS name, SUM(CASE WHEN COALESCE(NULLIF(review_status,''),'未复盘')='值得复讲' THEN 1 ELSE 0 END) AS cnt FROM picks WHERE COALESCE(archived,0)=0 AND date(pick_date) >= date('now','-29 day') GROUP BY pick_date ORDER BY pick_date ASC")
    deal_trend = q("SELECT pick_date AS name, SUM(CASE WHEN COALESCE(NULLIF(deal_status,''),'未成交')='已成交' THEN 1 ELSE 0 END) AS cnt FROM picks WHERE COALESCE(archived,0)=0 AND date(pick_date) >= date('now','-29 day') GROUP BY pick_date ORDER BY pick_date ASC")
    recent_logs = q("SELECT action, target_ids, detail, created_at FROM operation_logs ORDER BY id DESC LIMIT 15")

    where, args = filter_where(params)
    filter_count = q1(f"SELECT COUNT(*) AS cnt FROM picks {where}", args)['cnt']
    offset = (page - 1) * PAGE_SIZE
    latest = q(
        f'''SELECT id, pick_date, code, name, pick_price, source_channel, reason_tag, review_status, content_title,
                   COALESCE(archived,0) AS archived, COALESCE(result_grade,'待定') AS result_grade,
                   COALESCE(inquiry_count,0) AS inquiry_count, COALESCE(deal_status,'未成交') AS deal_status,
                   COALESCE(secondary_spread,'否') AS secondary_spread
            FROM picks {where} ORDER BY pick_date DESC, id DESC LIMIT ? OFFSET ?''', args + [PAGE_SIZE, offset])

    channel_opts = ''.join([f"<option value='{esc(r['name'])}' {'selected' if (params.get('channel',[''])[0] == r['name']) else ''}>{esc(r['name'])}</option>" for r in by_channel])
    tag_opts = ''.join([f"<option value='{esc(r['name'])}' {'selected' if (params.get('tag',[''])[0] == r['name']) else ''}>{esc(r['name'])}</option>" for r in by_tag])
    status_opts = ''.join([f"<option value='{esc(r['name'])}' {'selected' if (params.get('status',[''])[0] == r['name']) else ''}>{esc(r['name'])}</option>" for r in by_status])
    grade_opts = ''.join([f"<option value='{esc(v)}' {'selected' if (params.get('grade',[''])[0] == v) else ''}>{esc(v)}</option>" for v in RESULT_GRADE_OPTIONS])
    deal_opts = ''.join([f"<option value='{esc(v)}' {'selected' if (params.get('deal_status',[''])[0] == v) else ''}>{esc(v)}</option>" for v in DEAL_STATUS_OPTIONS])

    latest_rows = ''.join([
        f"<tr><td><input type='checkbox' name='ids' value='{r['id']}'></td><td>{esc(r['pick_date'])}</td><td>{esc(r['name'])}</td><td>{esc(r['code'])}</td><td>{esc(r['pick_price'])}</td><td>{esc(r['source_channel'])}</td><td>{esc(r['reason_tag'])}</td><td>{esc(r['review_status'])}</td><td>{esc(r['result_grade'])}</td><td>{esc(r['deal_status'])}</td><td>{esc(r['inquiry_count'])}</td><td>{esc(r['secondary_spread'])}</td><td><span class='badge {'badge-archived' if r['archived'] else 'badge-active'}'>{'已归档' if r['archived'] else '使用中'}</span></td><td><a class='txtbtn' href='/edit?id={r['id']}'>编辑</a><form method='post' action='/{'unarchive' if r['archived'] else 'archive'}' class='inline-form'><input type='hidden' name='id' value='{r['id']}'><button type='submit' class='linkbtn'>{'恢复' if r['archived'] else '归档'}</button></form><form method='post' action='/delete' class='inline-form' onsubmit=\"return confirm('确认删除这条记录？删除后不可恢复。')\"><input type='hidden' name='id' value='{r['id']}'><button type='submit' class='linkbtn danger'>删除</button></form></td></tr>"
        for r in latest
    ]) or '<tr><td colspan="14">暂无数据</td></tr>'
    log_rows = ''.join([f"<tr><td>{esc(r['created_at'])}</td><td>{esc(r['action'])}</td><td>{esc(r['target_ids'])}</td><td>{esc(r['detail'])}</td></tr>" for r in recent_logs]) or '<tr><td colspan="4">暂无日志</td></tr>'
    flash_html = f'<div class="card" style="background:#ecfdf5;color:#065f46;border:1px solid #a7f3d0">{esc(flash)}</div>' if flash else ''

    filter_query = build_query_string(params)
    export_json_href = '/export' + (f'?{filter_query}' if filter_query else '')
    export_csv_href = '/export.csv' + (f'?{filter_query}' if filter_query else '')
    monthly_href = '/monthly-report.csv'
    saved_filter_links = ''.join([f"<div style='display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:8px 0'><a class='page-link' href='/?{esc(r['query_string'])}'>{esc(r['name'])}</a><form method='post' action='/rename-filter' class='inline-form' style='display:inline-flex;gap:6px;align-items:center'><input type='hidden' name='filter_id' value='{r['id']}'><input name='new_name' value='{esc(r['name'])}' style='width:160px;padding:6px 8px;border:1px solid #d1d5db;border-radius:8px'><button type='submit' class='linkbtn'>改名</button></form><form method='post' action='/delete-filter' class='inline-form'><input type='hidden' name='filter_id' value='{r['id']}'><button type='submit' class='linkbtn danger'>删除</button></form></div>" for r in saved_filters]) or "<span class='muted'>还没有保存的常用筛选</span>"
    csv_template = 'pick_date,code,name,pick_price,signal,source_channel,reason_tag,review_status,result_grade,inquiry_count,deal_status,secondary_spread,content_title,content_ref,note\n2026-03-09,600519,贵州茅台,1688,强势趋势,douyin,趋势突破,值得复讲,A,12,已咨询,是,爆款复盘01,vid-001,样例备注'

    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>宣传票复盘系统 v4.7</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f6f7fb;color:#1f2937;margin:0;padding:24px}} .wrap{{max-width:1540px;margin:0 auto}} .grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:16px}} .grid2{{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}} .grid3{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}} .card{{background:#fff;border-radius:16px;padding:18px;box-shadow:0 6px 20px rgba(0,0,0,.06)}} h1,h2{{margin:0 0 12px}} .muted{{color:#6b7280;font-size:14px}} .num{{font-size:32px;font-weight:700}} table{{width:100%;border-collapse:collapse}} th,td{{padding:10px;border-bottom:1px solid #eee;text-align:left;font-size:14px;vertical-align:top;white-space:nowrap}} th{{background:#fafafa}} .section{{margin-top:20px}} input,select,textarea{{width:100%;padding:10px;border:1px solid #d1d5db;border-radius:10px;box-sizing:border-box}} textarea{{min-height:90px}} .bigtextarea{{min-height:180px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}} .formgrid3{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}} button{{background:#111827;color:#fff;border:0;border-radius:10px;padding:10px 16px;cursor:pointer}} a.btn{{display:inline-block;background:#111827;color:#fff;text-decoration:none;padding:10px 16px;border-radius:10px;margin-right:8px}} .bar-row,.line-row{{display:grid;grid-template-columns:140px 1fr 62px;gap:10px;align-items:center;margin:8px 0}} .bar-track,.line-track{{height:12px;background:#eef2ff;border-radius:999px;overflow:hidden}} .bar-fill,.line-fill{{height:100%;border-radius:999px}} .inline-form{{display:inline}} .linkbtn{{background:none;color:#2563eb;padding:0 6px;border:none;border-radius:0}} .linkbtn.danger{{color:#dc2626}} .txtbtn{{color:#2563eb;text-decoration:none;padding-right:6px}} .badge{{display:inline-block;padding:4px 8px;border-radius:999px;font-size:12px}} .badge-active{{background:#dcfce7;color:#166534}} .badge-archived{{background:#f3f4f6;color:#4b5563}} .topline{{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap}} .bulkbar{{display:flex;gap:8px;flex-wrap:wrap;align-items:center}} .bulkbar select{{width:auto;min-width:140px}} .smallbtn{{padding:8px 12px;border-radius:10px}} .tablewrap{{overflow:auto}} .subtle{{font-size:12px;color:#6b7280}} @media (max-width:980px){{.grid,.grid2,.grid3,.formgrid3{{grid-template-columns:1fr}} body{{padding:16px}} .wrap{{max-width:100%}}}}</style><script>function toggleAll(source){{document.querySelectorAll('input[name="ids"]').forEach(cb=>cb.checked=source.checked);}} function ensureSelected(form){{const checked=form.querySelectorAll('input[name="ids"]:checked'); if(!checked.length){{alert('请先勾选至少一条记录'); return false;}} return true;}}</script></head><body><div class="wrap"><div class="topline"><div><h1>宣传票复盘系统 v4.7</h1><div class="muted">更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} · 已启用密码保护 · 本地端口 {PORT}</div></div><div class="muted">本次新增：排行榜指标切换 / 首页排序配置继续可用</div></div><div class='nav'>{render_nav('dashboard')}</div>{flash_html}
<div class="grid section"><div class="card"><div class="muted">累计记录</div><div class="num">{overview.get('total',0)}</div></div><div class="card"><div class="muted">使用中</div><div class="num">{overview.get('active_total',0) or 0}</div></div><div class="card"><div class="muted">已成交数</div><div class="num">{int(overview.get('deal_total') or 0)}</div></div><div class="card"><div class="muted">二次传播数</div><div class="num">{int(overview.get('spread_total') or 0)}</div></div><div class="card"><div class="muted">值得复讲总数</div><div class="num">{int(overview.get('worthy_total') or 0)}</div></div></div>
<div class="grid3 section"><div class="card"><div class="muted">本周新增</div><div class="num">{int(kpi.get('week_new') or 0)}</div><div class="subtle">反映本周录入节奏</div></div><div class="card"><div class="muted">近30天新增</div><div class="num">{int(kpi.get('last30_new') or 0)}</div><div class="subtle">观察数据沉淀速度</div></div><div class="card"><div class="muted">平均咨询数</div><div class="num">{kpi.get('avg_inquiry') or 0}</div><div class="subtle">衡量内容带来互动的能力</div></div></div>
<div class="section card"><h2>首页模块排序</h2><div class='muted'>当前顺序：{dashboard_order}</div><form method='post' action='/save-dashboard-order' style='margin-top:12px'><div class='formgrid3'><div><label>模块顺序字符串</label><input name='dashboard_order' value='{dashboard_order}'></div><div class='muted' style='display:flex;align-items:end'>可用值示例：kpi,trend,filters,actions,records,logs</div><div style='display:flex;align-items:end'><button type='submit'>保存首页顺序</button></div></div></form></div><div class="section card"><h2>快捷入口</h2><p><a class="btn" href="/deal-review">成交复盘页</a><a class="btn" href="/leaderboards">排行榜页</a><a class="btn" href="/reports">报表中心</a><a class="btn" href="{monthly_href}">导出月报 CSV</a><a class="btn" href="{export_json_href}">导出 JSON</a><a class="btn" href="{export_csv_href}">导出 CSV</a><a class="btn" href="/logout">退出登录</a></p></div><div class="section card"><h2>常用筛选视图</h2><div class='pagination'>{saved_filter_links}</div><div class='muted' style='margin-top:8px'>点击“重命名”会先自动生成一个占位新名字，你后面如果要我再做成弹窗改名也可以继续升级。</div><form method='post' action='/save-filter' style='margin-top:12px'><div class='formgrid3'><div><label>视图名称</label><input name='filter_name' placeholder='例如：抖音已成交 / A级内容'></div><div><label>当前筛选串</label><input name='query_string' value='{filter_query}' placeholder='会自动带上当前筛选参数'></div><div style='display:flex;align-items:end'><button type='submit'>保存当前筛选</button></div></div></form></div>
<div class="grid3 section"><div class="card"><h2>结果评级分布</h2>{bar_html(by_grade, color='#0f766e')}</div><div class="card"><h2>成交状态分布</h2>{bar_html(by_deal, color='#ca8a04')}</div><div class="card"><h2>标签分布</h2>{bar_html(by_tag, color='#dc2626')}</div></div>
<div class="grid3 section"><div class="card"><h2>近30天录入趋势</h2>{line_table_html(trend_30d, color='#7c3aed')}</div><div class="card"><h2>近30天值得复讲趋势</h2>{line_table_html(worthy_trend, color='#0891b2')}</div><div class="card"><h2>近30天成交趋势</h2>{line_table_html(deal_trend, color='#16a34a')}</div></div>
<div class="section card"><h2>筛选 / 搜索</h2><form method="get" action="/"><div class="formgrid3"><div><label>关键词</label><input name="keyword" value="{esc((params.get('keyword',[''])[0] or '').strip())}" placeholder="股票代码/股票名称/内容标题/内容编号"></div><div><label>渠道</label><select name="channel"><option value="">全部</option>{channel_opts}</select></div><div><label>标签</label><select name="tag"><option value="">全部</option>{tag_opts}</select></div><div><label>复盘状态</label><select name="status"><option value="">全部</option>{status_opts}</select></div><div><label>结果评级</label><select name="grade"><option value="">全部</option>{grade_opts}</select></div><div><label>成交状态</label><select name="deal_status"><option value="">全部</option>{deal_opts}</select></div><div><label>开始日期</label><input type="date" name="date_from" value="{esc((params.get('date_from',[''])[0] or '').strip())}"></div><div><label>结束日期</label><input type="date" name="date_to" value="{esc((params.get('date_to',[''])[0] or '').strip())}"></div><div><label>记录范围</label><select name="archive"><option value="active" {'selected' if (params.get('archive',['active'])[0] or 'active')=='active' else ''}>仅使用中</option><option value="archived" {'selected' if (params.get('archive',['active'])[0] or 'active')=='archived' else ''}>仅已归档</option><option value="all" {'selected' if (params.get('archive',['active'])[0] or 'active')=='all' else ''}>全部记录</option></select></div></div><div style="margin-top:12px"><button type="submit">筛选结果</button> <a class="btn" href="/">清空筛选</a></div><div class="muted" style="margin-top:8px">当前筛选结果：{filter_count} 条</div></form></div>
<div class="grid2 section"><div class="card"><h2>新增记录</h2><form method="post" action="/add"><div class="formgrid3"><div><label>日期</label><input name="pick_date" value="{datetime.now().strftime('%Y-%m-%d')}" required></div><div><label>股票代码</label><input name="code" required></div><div><label>股票名称</label><input name="name" required></div><div><label>推荐价</label><input name="pick_price" required></div><div><label>信号</label><input name="signal"></div><div><label>渠道</label><input name="source_channel" placeholder="douyin/xhs/live/community"></div><div><label>标签</label><input name="reason_tag" placeholder="趋势突破/缩量回踩"></div><div><label>复盘结论</label><select name="review_status">{select_options(REVIEW_STATUS_OPTIONS, '未复盘')}</select></div><div><label>结果评级</label><select name="result_grade">{select_options(RESULT_GRADE_OPTIONS, '待定')}</select></div><div><label>咨询数</label><input name="inquiry_count" value="0"></div><div><label>成交状态</label><select name="deal_status">{select_options(DEAL_STATUS_OPTIONS, '未成交')}</select></div><div><label>二次传播</label><select name="secondary_spread">{select_options(SPREAD_OPTIONS, '否')}</select></div><div><label>内容标题</label><input name="content_title"></div><div><label>内容编号/链接</label><input name="content_ref"></div></div><div style="margin-top:12px"><label>备注/复盘评论</label><textarea name="note"></textarea></div><div style="margin-top:12px"><button type="submit">保存到系统</button></div></form></div><div class="card"><h2>批量 CSV 导入</h2><form method="post" action="/bulk-import"><div style="margin-top:12px"><textarea style="min-height:180px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace" name="csv_text" placeholder="{esc(csv_template)}"></textarea></div><div style="margin-top:12px"><button type="submit">批量导入 CSV</button></div></form></div></div>
<div class="section card"><div class="topline" style="margin-bottom:12px"><h2>最新记录</h2><div class="subtle">支持批量归档 / 恢复 / 删除 / 批量改复盘状态 / 评级 / 成交 / 传播</div></div><form method="post" action="/batch-review" onsubmit="return ensureSelected(this)"><div class="bulkbar" style="margin-bottom:12px"><select name="review_status">{select_options(REVIEW_STATUS_OPTIONS, '值得复讲')}</select><button type="submit" class="smallbtn">批量改复盘状态</button><select name="result_grade">{select_options(RESULT_GRADE_OPTIONS, 'A')}</select><button formaction="/batch-grade" type="submit" class="smallbtn">批量改评级</button><select name="deal_status">{select_options(DEAL_STATUS_OPTIONS, '已咨询')}</select><button formaction="/batch-deal" type="submit" class="smallbtn">批量改成交状态</button><select name="secondary_spread">{select_options(SPREAD_OPTIONS, '是')}</select><button formaction="/batch-spread" type="submit" class="smallbtn">批量改传播</button><button formaction="/batch-archive" type="submit" class="smallbtn">批量归档</button><button formaction="/batch-unarchive" type="submit" class="smallbtn">批量恢复</button><button formaction="/batch-delete" type="submit" class="smallbtn" onclick="return ensureSelected(this.form) && confirm('确认批量删除所选记录？删除后不可恢复。')">批量删除</button></div><div class="tablewrap"><table><thead><tr><th><input type="checkbox" onclick="toggleAll(this)"></th><th>日期</th><th>股票</th><th>代码</th><th>推荐价</th><th>渠道</th><th>标签</th><th>复盘结论</th><th>评级</th><th>成交状态</th><th>咨询数</th><th>二次传播</th><th>状态</th><th>操作</th></tr></thead><tbody>{latest_rows}</tbody></table></div>{render_pagination(page, filter_count, params)}</form></div>
<div class="section card"><h2>最近操作日志</h2><div class="tablewrap"><table><thead><tr><th>时间</th><th>动作</th><th>记录ID</th><th>说明</th></tr></thead><tbody>{log_rows}</tbody></table></div></div></div></body></html>'''


def render_login(error=''):
    err = f'<div class="err">{esc(error)}</div>' if error else ''
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>登录宣传票复盘系统</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f6f7fb;padding:24px}}.box{{max-width:420px;margin:10vh auto;background:#fff;padding:24px;border-radius:16px;box-shadow:0 6px 20px rgba(0,0,0,.06)}}input{{width:100%;padding:12px;border:1px solid #d1d5db;border-radius:10px;box-sizing:border-box}}button{{margin-top:12px;width:100%;padding:12px;background:#111827;color:#fff;border:0;border-radius:10px}}.muted{{color:#6b7280;font-size:14px}}.err{{background:#fef2f2;color:#991b1b;border:1px solid #fecaca;padding:10px;border-radius:10px;margin:12px 0}}</style></head><body><div class="box"><h1>登录宣传票复盘系统</h1><div class="muted">v4.7 已启用访问密码保护</div>{err}<form method="post" action="/login"><input type="password" name="password" placeholder="请输入访问密码" required><button type="submit">登录</button></form></div></body></html>'''


def render_edit_form(record):
    if not record:
        return '<!doctype html><html><body>记录不存在</body></html>'
    return layout_page('编辑记录', f'''<div class="card"><h1>编辑宣传票记录</h1><form method="post" action="/update"><input type="hidden" name="id" value="{record['id']}"><div class="grid"><div><label>日期</label><input name="pick_date" value="{esc(record['pick_date'])}" required></div><div><label>股票代码</label><input name="code" value="{esc(record['code'])}" required></div><div><label>股票名称</label><input name="name" value="{esc(record['name'])}" required></div><div><label>推荐价</label><input name="pick_price" value="{esc(record['pick_price'])}" required></div><div><label>信号</label><input name="signal" value="{esc(record['signal'])}"></div><div><label>渠道</label><input name="source_channel" value="{esc(record['source_channel'])}"></div><div><label>标签</label><input name="reason_tag" value="{esc(record['reason_tag'])}"></div><div><label>复盘结论</label><select name="review_status">{select_options(REVIEW_STATUS_OPTIONS, label(record.get('review_status'), '未复盘'))}</select></div><div><label>结果评级</label><select name="result_grade">{select_options(RESULT_GRADE_OPTIONS, label(record.get('result_grade'), '待定'))}</select></div><div><label>咨询数</label><input name="inquiry_count" value="{esc(record.get('inquiry_count', 0))}"></div><div><label>成交状态</label><select name="deal_status">{select_options(DEAL_STATUS_OPTIONS, label(record.get('deal_status'), '未成交'))}</select></div><div><label>二次传播</label><select name="secondary_spread">{select_options(SPREAD_OPTIONS, label(record.get('secondary_spread'), '否'))}</select></div><div><label>内容标题</label><input name="content_title" value="{esc(record['content_title'])}"></div><div><label>内容编号/链接</label><input name="content_ref" value="{esc(record['content_ref'])}"></div></div><div style="margin-top:12px"><label>备注/复盘评论</label><textarea name="note" style="width:100%;min-height:100px">{esc(record['note'])}</textarea></div><div style="margin-top:16px"><button type="submit">保存修改</button><a class="btn" href="/">返回面板</a></div></form></div>''')


def render_deal_review_page():
    deals = q(
        '''SELECT pick_date, code, name, source_channel, reason_tag, review_status, result_grade, inquiry_count, deal_status, secondary_spread, content_title
           FROM picks
           WHERE COALESCE(NULLIF(deal_status,''),'未成交')='已成交'
           ORDER BY pick_date DESC, id DESC'''
    )
    rows = ''.join([
        f"<tr><td>{esc(r['pick_date'])}</td><td>{esc(r['name'])}</td><td>{esc(r['code'])}</td><td>{esc(r['source_channel'])}</td><td>{esc(r['reason_tag'])}</td><td>{esc(r['review_status'])}</td><td>{esc(r['result_grade'])}</td><td>{esc(r['inquiry_count'])}</td><td>{esc(r['secondary_spread'])}</td><td>{esc(r['content_title'])}</td></tr>"
        for r in deals
    ]) or '<tr><td colspan="10">暂无成交记录</td></tr>'
    summary = q1(
        '''SELECT COUNT(*) AS total,
                  ROUND(AVG(COALESCE(inquiry_count,0)),1) AS avg_inquiry,
                  SUM(CASE WHEN COALESCE(NULLIF(secondary_spread,''),'否')='是' THEN 1 ELSE 0 END) AS spread_total
           FROM picks WHERE COALESCE(NULLIF(deal_status,''),'未成交')='已成交' '''
    ) or {}
    body = f'''<div class="topline"><div><h1>成交复盘页</h1><div class="muted">专门查看已成交内容，反推最有效的渠道 / 标签 / 内容方向</div></div><div><a class="btn" href="/">返回面板</a></div></div>
<div class='nav'>{render_nav('deal')}</div>
<div class="grid section"><div class="card"><div class="muted">已成交条数</div><div class="num">{int(summary.get('total') or 0)}</div></div><div class="card"><div class="muted">成交记录平均咨询数</div><div class="num">{summary.get('avg_inquiry') or 0}</div></div><div class="card"><div class="muted">成交中的二次传播数</div><div class="num">{int(summary.get('spread_total') or 0)}</div></div></div>
<div class="section card"><div class="tablewrap"><table><thead><tr><th>日期</th><th>股票</th><th>代码</th><th>渠道</th><th>标签</th><th>复盘结论</th><th>评级</th><th>咨询数</th><th>二次传播</th><th>内容标题</th></tr></thead><tbody>{rows}</tbody></table></div></div>'''
    return layout_page('成交复盘页', body)


def render_leaderboards_page(range_key='30d', metric='default'):
    range_sql_map = {
        '7d': "WHERE date(pick_date) >= date('now','-6 day')",
        '30d': "WHERE date(pick_date) >= date('now','-29 day')",
        '90d': "WHERE date(pick_date) >= date('now','-89 day')",
        'all': ''
    }
    range_sql = range_sql_map.get(range_key, range_sql_map['30d'])
    range_where = (range_sql + ' AND ') if range_sql else 'WHERE '

    channel_rank = q(f"SELECT COALESCE(NULLIF(source_channel,''),'system') AS name, COUNT(*) AS cnt FROM picks {range_sql} GROUP BY name ORDER BY cnt DESC LIMIT 10")
    worthy_rank = q(f"SELECT COALESCE(NULLIF(reason_tag,''),'未标注') AS name, COUNT(*) AS cnt FROM picks {range_where}COALESCE(NULLIF(review_status,''),'未复盘')='值得复讲' GROUP BY name ORDER BY cnt DESC LIMIT 10")
    deal_rank = q(f"SELECT COALESCE(NULLIF(source_channel,''),'system') AS name, COUNT(*) AS cnt FROM picks {range_where}COALESCE(NULLIF(deal_status,''),'未成交')='已成交' GROUP BY name ORDER BY cnt DESC LIMIT 10")
    inquiry_rank = q(f"SELECT COALESCE(NULLIF(reason_tag,''),'未标注') AS name, ROUND(AVG(COALESCE(inquiry_count,0)),1) AS cnt FROM picks {range_sql} GROUP BY name ORDER BY cnt DESC LIMIT 10")
    spread_rank = q(f"SELECT COALESCE(NULLIF(source_channel,''),'system') AS name, COUNT(*) AS cnt FROM picks {range_where}COALESCE(NULLIF(secondary_spread,''),'否')='是' GROUP BY name ORDER BY cnt DESC LIMIT 10")

    range_links = ''.join([
        f"<a class='{'navlink nav-active' if range_key == rk else 'navlink'}' href='/leaderboards?range={rk}&metric={metric}'>{label}</a>"
        for rk, label in [('7d', '近7天'), ('30d', '近30天'), ('90d', '近90天'), ('all', '全部')]
    ])
    metric_links = ''.join([
        f"<a class='{'navlink nav-active' if metric == mk else 'navlink'}' href='/leaderboards?range={range_key}&metric={mk}'>{label}</a>"
        for mk, label in [('default', '默认榜单'), ('spread', '传播榜单')]
    ])

    right_title = '二次传播渠道 Top10' if metric == 'spread' else '标签平均咨询数 Top10'
    right_rows = spread_rank if metric == 'spread' else inquiry_rank
    right_color = '#7c3aed' if metric == 'spread' else '#ca8a04'

    body = f'''<div class="topline"><div><h1>排行榜页</h1><div class="muted">把渠道、标签、成交、咨询这些关键指标拆开看，方便你抓重点</div></div><div><a class="btn" href="/">返回面板</a></div></div>
<div class='nav'>{render_nav('leaderboards')}</div>
<div class='nav'>{range_links}</div>
<div class='nav'>{metric_links}</div>
<div class="grid2 section"><div class="card"><h2>渠道记录 Top10</h2>{bar_html(channel_rank, color='#4f46e5')}</div><div class="card"><h2>值得复讲标签 Top10</h2>{bar_html(worthy_rank, color='#0ea5e9')}</div></div>
<div class="grid2 section"><div class="card"><h2>成交渠道 Top10</h2>{bar_html(deal_rank, color='#16a34a')}</div><div class="card"><h2>{right_title}</h2>{bar_html(right_rows, color=right_color)}</div></div>'''
    return layout_page('排行榜页', body)


def render_reports_page():
    weekly = weekly_report_rows()
    monthly = monthly_report_rows()
    summary_text = report_summary_text()
    weekly_text = summary_text.get('weekly', '')
    monthly_text = summary_text.get('monthly', '')
    boss_text = summary_text.get('boss', '')
    weekly_rows = ''.join([f"<tr><td>{esc(r['period'])}</td><td>{esc(r['total'])}</td><td>{esc(r['worthy_total'])}</td><td>{esc(r['deal_total'])}</td></tr>" for r in weekly]) or '<tr><td colspan="4">暂无数据</td></tr>'
    monthly_rows = ''.join([f"<tr><td>{esc(r['month'])}</td><td>{esc(r['total'])}</td><td>{esc(r['worthy_total'])}</td><td>{esc(r['deal_total'])}</td><td>{esc(r['avg_inquiry'])}</td></tr>" for r in monthly]) or '<tr><td colspan="5">暂无数据</td></tr>'
    body = f'''<div class="topline"><div><h1>报表中心</h1><div class="muted">集中查看周报/月报，适合正式复盘和团队同步</div></div><div><a class="btn" href="/weekly-report.csv">导出周报CSV</a><a class="btn" href="/monthly-report.csv">导出月报CSV</a></div></div>
<div class='nav'>{render_nav('reports')}</div>
<div class="grid3 section"><div class="card"><h2>自动周报文案</h2><div class="muted">适合直接发群、发团队同步</div><textarea style="width:100%;min-height:140px;margin-top:10px;border:1px solid #d1d5db;border-radius:12px;padding:12px;box-sizing:border-box" onclick="this.select()">{weekly_text}</textarea><div class="muted">点击文本框即可一键全选复制</div></div><div class="card"><h2>自动月报文案</h2><div class="muted">适合月复盘、月总结、汇报</div><textarea style="width:100%;min-height:140px;margin-top:10px;border:1px solid #d1d5db;border-radius:12px;padding:12px;box-sizing:border-box" onclick="this.select()">{monthly_text}</textarea><div class="muted">点击文本框即可一键全选复制</div></div><div class="card"><h2>老板汇报版文案</h2><div class="muted">更短、更像管理层汇报口径</div><textarea style="width:100%;min-height:140px;margin-top:10px;border:1px solid #d1d5db;border-radius:12px;padding:12px;box-sizing:border-box" onclick="this.select()">{boss_text}</textarea><div class="muted">适合直接复制给老板/合伙人</div></div></div>
<div class="grid2 section"><div class="card"><h2>近12周周报</h2><div class="tablewrap"><table><thead><tr><th>周</th><th>总记录</th><th>值得复讲</th><th>已成交</th></tr></thead><tbody>{weekly_rows}</tbody></table></div></div><div class="card"><h2>月报汇总</h2><div class="tablewrap"><table><thead><tr><th>月份</th><th>总记录</th><th>值得复讲</th><th>已成交</th><th>平均咨询数</th></tr></thead><tbody>{monthly_rows}</tbody></table></div></div></div>'''
    return layout_page('报表中心', body)


class Handler(BaseHTTPRequestHandler):
    def cookies(self): return parse_cookies(self.headers.get('Cookie'))
    def authed(self): return self.cookies().get(COOKIE_NAME) == PANEL_PASSWORD

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
        return parse_multi_post(self.rfile.read(length).decode('utf-8'))

    def _selected_ids(self, data):
        return [int(x) for x in as_list(data, 'ids') if str(x).isdigit()]

    def _batch_update(self, sql, ids):
        return execute_many(sql, [(i,) for i in ids]) if ids else 0

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/health':
            self._send(200, 'ok', 'text/plain; charset=utf-8'); return
        if parsed.path == '/logout':
            self._redirect('/login', f'{COOKIE_NAME}=; Path=/; Max-Age=0'); return
        if parsed.path == '/login':
            self._send(200, render_login()); return
        if not self.authed():
            self._redirect('/login'); return
        if parsed.path == '/':
            self._send(200, render_dashboard(parse_qs(parsed.query))); return
        if parsed.path == '/edit':
            self._send(200, render_edit_form(q1('SELECT * FROM picks WHERE id=?', (parse_qs(parsed.query).get('id', [''])[0],)))); return
        if parsed.path == '/deal-review':
            self._send(200, render_deal_review_page()); return
        if parsed.path == '/leaderboards':
            params = parse_qs(parsed.query)
            self._send(200, render_leaderboards_page((params.get('range', ['30d'])[0] or '30d'), (params.get('metric', ['default'])[0] or 'default'))); return
        if parsed.path == '/reports':
            self._send(200, render_reports_page()); return
        if parsed.path == '/weekly-report.csv':
            csv_body = io.StringIO()
            writer = csv.DictWriter(csv_body, fieldnames=['period', 'total', 'worthy_total', 'deal_total'])
            writer.writeheader()
            for row in weekly_report_rows():
                writer.writerow(row)
            self._send(200, csv_body.getvalue(), 'text/csv; charset=utf-8', {'Content-Disposition': 'attachment; filename="weekly_report.csv"'}); return
        if parsed.path == '/monthly-report.csv':
            csv_body = io.StringIO()
            writer = csv.DictWriter(csv_body, fieldnames=['month', 'total', 'worthy_total', 'deal_total', 'avg_inquiry'])
            writer.writeheader()
            for row in monthly_report_rows():
                writer.writerow(row)
            self._send(200, csv_body.getvalue(), 'text/csv; charset=utf-8', {'Content-Disposition': 'attachment; filename="monthly_report.csv"'}); return
        if parsed.path == '/export':
            params = parse_qs(parsed.query); where, args = filter_where(params)
            self._send(200, json.dumps(q(f'SELECT * FROM picks {where} ORDER BY pick_date DESC, id DESC', args), ensure_ascii=False, indent=2), 'application/json; charset=utf-8'); return
        if parsed.path == '/export.csv':
            params = parse_qs(parsed.query); where, args = filter_where(params)
            csv_body = rows_to_csv(q(f'SELECT * FROM picks {where} ORDER BY pick_date DESC, id DESC', args))
            self._send(200, csv_body, 'text/csv; charset=utf-8', {'Content-Disposition': 'attachment; filename="promo_panel_export.csv"'}); return
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
            self._redirect('/login'); return
        if self.path == '/add':
            execute('''INSERT OR REPLACE INTO picks (pick_date, code, name, pick_price, signal, source, source_channel, reason_tag, note, review_status, review_comment, content_title, content_ref, archived, result_grade, inquiry_count, deal_status, secondary_spread) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)''',
                    (data.get('pick_date', ''), data.get('code', ''), data.get('name', ''), num(data.get('pick_price', '0')), data.get('signal', ''), 'webform', data.get('source_channel', 'web'), data.get('reason_tag', ''), data.get('note', ''), data.get('review_status', '未复盘'), data.get('note', ''), data.get('content_title', ''), data.get('content_ref', ''), data.get('result_grade', '待定'), int_num(data.get('inquiry_count', 0)), data.get('deal_status', '未成交'), data.get('secondary_spread', '否')))
            new_row = q1('SELECT id FROM picks ORDER BY id DESC LIMIT 1'); log_action('add', [new_row['id']] if new_row else [], f"新增 {data.get('code','')} {data.get('name','')}"); self._redirect('/?saved=1'); return
        if self.path == '/bulk-import':
            ids = bulk_import_from_csv(data.get('csv_text', '')); log_action('bulk_import', ids, f'CSV 导入 {len(ids)} 条'); self._redirect('/?imported=1'); return
        if self.path == '/save-filter':
            name = (data.get('filter_name', '') or '').strip()
            query_string = (data.get('query_string', '') or '').strip()
            if name and query_string:
                execute('INSERT INTO saved_filters (name, query_string) VALUES (?, ?)', (name, query_string))
                log_action('save_filter', [], f'保存筛选视图：{name}')
            self._redirect('/')
            return
        if self.path == '/save-dashboard-order':
            order = (data.get('dashboard_order', '') or '').strip()
            if order:
                set_dashboard_order(order)
                log_action('save_dashboard_order', [], f'保存首页模块顺序：{order}')
            self._redirect('/')
            return
        if self.path == '/delete-filter':
            fid = data.get('filter_id', '')
            if fid:
                execute('DELETE FROM saved_filters WHERE id=?', (fid,))
                log_action('delete_filter', [], f'删除筛选视图 id={fid}')
            self._redirect('/')
            return
        if self.path == '/rename-filter':
            fid = data.get('filter_id', '')
            new_name = (data.get('new_name', '') or '').strip()
            if fid and new_name:
                execute('UPDATE saved_filters SET name=? WHERE id=?', (new_name, fid))
                log_action('rename_filter', [], f'重命名筛选视图 id={fid} -> {new_name}')
            self._redirect('/')
            return
        if self.path == '/update':
            rid = data.get('id', '')
            execute('''UPDATE picks SET pick_date=?, code=?, name=?, pick_price=?, signal=?, source_channel=?, reason_tag=?, note=?, review_status=?, review_comment=?, content_title=?, content_ref=?, result_grade=?, inquiry_count=?, deal_status=?, secondary_spread=? WHERE id=?''',
                    (data.get('pick_date', ''), data.get('code', ''), data.get('name', ''), num(data.get('pick_price', '0')), data.get('signal', ''), data.get('source_channel', ''), data.get('reason_tag', ''), data.get('note', ''), data.get('review_status', '未复盘'), data.get('note', ''), data.get('content_title', ''), data.get('content_ref', ''), data.get('result_grade', '待定'), int_num(data.get('inquiry_count', 0)), data.get('deal_status', '未成交'), data.get('secondary_spread', '否'), rid))
            log_action('update', [rid], f'编辑记录 {rid}'); self._redirect('/?updated=1'); return
        if self.path == '/archive': rid = data.get('id', ''); execute('UPDATE picks SET archived=1 WHERE id=?', (rid,)); log_action('archive', [rid], '单条归档'); self._redirect('/?archived=1'); return
        if self.path == '/unarchive': rid = data.get('id', ''); execute('UPDATE picks SET archived=0 WHERE id=?', (rid,)); log_action('unarchive', [rid], '单条恢复'); self._redirect('/?unarchived=1'); return
        if self.path == '/delete': rid = data.get('id', ''); execute('DELETE FROM picks WHERE id=?', (rid,)); log_action('delete', [rid], '单条删除'); self._redirect('/?deleted=1'); return
        if self.path == '/batch-archive': ids = self._selected_ids(data); self._batch_update('UPDATE picks SET archived=1 WHERE id=?', ids); log_action('batch_archive', ids, f'批量归档 {len(ids)} 条'); self._redirect('/?batch_archived=1'); return
        if self.path == '/batch-unarchive': ids = self._selected_ids(data); self._batch_update('UPDATE picks SET archived=0 WHERE id=?', ids); log_action('batch_unarchive', ids, f'批量恢复 {len(ids)} 条'); self._redirect('/?batch_unarchived=1'); return
        if self.path == '/batch-delete': ids = self._selected_ids(data); self._batch_update('DELETE FROM picks WHERE id=?', ids); log_action('batch_delete', ids, f'批量删除 {len(ids)} 条'); self._redirect('/?batch_deleted=1'); return
        if self.path == '/batch-review': ids = self._selected_ids(data); status = data.get('review_status', '未复盘'); execute_many('UPDATE picks SET review_status=? WHERE id=?', [(status, i) for i in ids]) if ids else None; log_action('batch_review', ids, f'批量改复盘状态为 {status}'); self._redirect('/?batch_reviewed=1'); return
        if self.path == '/batch-grade': ids = self._selected_ids(data); grade = data.get('result_grade', '待定'); execute_many('UPDATE picks SET result_grade=? WHERE id=?', [(grade, i) for i in ids]) if ids else None; log_action('batch_grade', ids, f'批量改评级为 {grade}'); self._redirect('/?batch_grade=1'); return
        if self.path == '/batch-deal': ids = self._selected_ids(data); ds = data.get('deal_status', '未成交'); execute_many('UPDATE picks SET deal_status=? WHERE id=?', [(ds, i) for i in ids]) if ids else None; log_action('batch_deal', ids, f'批量改成交状态为 {ds}'); self._redirect('/?batch_deal=1'); return
        if self.path == '/batch-spread': ids = self._selected_ids(data); sp = data.get('secondary_spread', '否'); execute_many('UPDATE picks SET secondary_spread=? WHERE id=?', [(sp, i) for i in ids]) if ids else None; log_action('batch_spread', ids, f'批量改二次传播为 {sp}'); self._redirect('/?batch_spread=1'); return
        self._send(404, 'not found', 'text/plain; charset=utf-8')


if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f'v4.7 server running on http://0.0.0.0:{PORT}')
    print(f'panel password: {PANEL_PASSWORD}')
    server.serve_forever()
