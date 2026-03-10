"""HTTP handler routes.

Keep handler methods thin and delegate to web_panel renderers/services.
We keep this module independent from the server startup.
"""

import csv
import io
import json
from urllib.parse import parse_qs, urlparse

from backend.repositories.db import q
from backend.repositories import picks_repo
from backend.services.query_service import filter_where
from backend.services.io_service import bulk_import_from_csv, rows_to_csv
from backend.services.format_service import num, int_num
from backend.services.filters_service import (
    set_dashboard_order,
    save_current_filter,
    delete_saved_filter,
    rename_saved_filter,
)
from backend.services.reports_service import weekly_report_rows, monthly_report_rows
from backend.pages.users_page import render_users_page
from backend.services import multiuser_auth_service
from backend.services import users_admin_service


def handle_get(h):
    """Route GET requests. `h` is the BaseHTTPRequestHandler instance."""
    parsed = urlparse(h.path)

    if parsed.path == '/health':
        h._send(200, 'ok', 'text/plain; charset=utf-8')
        return
    if parsed.path == '/logout':
        token = h.cookies().get(h.COOKIE_NAME)
        multiuser_auth_service.logout(token)
        h._redirect('/login', f"{h.COOKIE_NAME}=; Path=/; Max-Age=0")
        return
    if parsed.path == '/login':
        h._send(200, h.render_login())
        return
    if not h.authed():
        h._redirect('/login')
        return

    if parsed.path == '/':
        h._send(200, h.render_dashboard(parse_qs(parsed.query)))
        return
    if parsed.path == '/edit':
        rid = parse_qs(parsed.query).get('id', [''])[0]
        h._send(200, h.render_edit_form(picks_repo.get_pick_by_id(rid)))
        return
    if parsed.path == '/deal-review':
        h._send(200, h.render_deal_review_page())
        return
    if parsed.path == '/leaderboards':
        params = parse_qs(parsed.query)
        h._send(200, h.render_leaderboards_page((params.get('range', ['30d'])[0] or '30d'), (params.get('metric', ['default'])[0] or 'default')))
        return
    if parsed.path == '/reports':
        h._send(200, h.render_reports_page())
        return

    if parsed.path == '/users':
        # admin only
        s = h.session() or {}
        if (s.get('role') or '') != 'admin':
            h._send(403, 'forbidden', 'text/plain; charset=utf-8'); return
        h._send(200, render_users_page())
        return

    if parsed.path == '/weekly-report.csv':
        csv_body = io.StringIO()
        writer = csv.DictWriter(csv_body, fieldnames=['period', 'total', 'worthy_total', 'deal_total'])
        writer.writeheader()
        for row in weekly_report_rows():
            writer.writerow(row)
        h._send(200, csv_body.getvalue(), 'text/csv; charset=utf-8', {'Content-Disposition': 'attachment; filename="weekly_report.csv"'})
        return

    if parsed.path == '/monthly-report.csv':
        csv_body = io.StringIO()
        writer = csv.DictWriter(csv_body, fieldnames=['month', 'total', 'worthy_total', 'deal_total', 'avg_inquiry'])
        writer.writeheader()
        for row in monthly_report_rows():
            writer.writerow(row)
        h._send(200, csv_body.getvalue(), 'text/csv; charset=utf-8', {'Content-Disposition': 'attachment; filename="monthly_report.csv"'})
        return

    if parsed.path == '/export':
        params = parse_qs(parsed.query)
        where, args = filter_where(params)
        h._send(
            200,
            json.dumps(picks_repo.list_picks(where, args), ensure_ascii=False, indent=2),
            'application/json; charset=utf-8',
        )
        return

    if parsed.path == '/export.csv':
        params = parse_qs(parsed.query)
        where, args = filter_where(params)
        csv_body = rows_to_csv(picks_repo.list_picks(where, args))
        h._send(200, csv_body, 'text/csv; charset=utf-8', {'Content-Disposition': 'attachment; filename="promo_panel_export.csv"'})
        return

    h._send(404, 'not found', 'text/plain; charset=utf-8')


def handle_post(h):
    """Route POST requests. `h` is the BaseHTTPRequestHandler instance."""
    data = h._read_post()

    if h.path == '/login':
        username = (data.get('username', '') or '').strip()
        password = data.get('password', '')
        sess = multiuser_auth_service.login(username, password)
        if sess:
            h._redirect('/', f"{h.COOKIE_NAME}={sess['session_token']}; Path=/; HttpOnly")
        else:
            h._send(200, h.render_login('账号或密码不对'))
        return
    if not h.authed():
        h._redirect('/login')
        return

    if h.path == '/add':
        picks_repo.create_or_replace_pick(
            pick_date=data.get('pick_date', ''),
            code=data.get('code', ''),
            name=data.get('name', ''),
            pick_price=num(data.get('pick_price', '0')),
            signal=data.get('signal', ''),
            source='webform',
            source_channel=data.get('source_channel', 'web'),
            reason_tag=data.get('reason_tag', ''),
            note=data.get('note', ''),
            review_status=data.get('review_status', '未复盘'),
            review_comment=data.get('note', ''),
            content_title=data.get('content_title', ''),
            content_ref=data.get('content_ref', ''),
            result_grade=data.get('result_grade', '待定'),
            inquiry_count=int_num(data.get('inquiry_count', 0)),
            deal_status=data.get('deal_status', '未成交'),
            secondary_spread=data.get('secondary_spread', '否'),
        )
        new_id = picks_repo.last_inserted_id()
        h.log_action('add', [new_id] if new_id else [], f"新增 {data.get('code','')} {data.get('name','')}")
        h._redirect('/?saved=1')
        return

    if h.path == '/bulk-import':
        ids = bulk_import_from_csv(data.get('csv_text', ''))
        h.log_action('bulk_import', ids, f'CSV 导入 {len(ids)} 条')
        h._redirect('/?imported=1')
        return

    if h.path == '/save-filter':
        name = (data.get('filter_name', '') or '').strip()
        query_string = (data.get('query_string', '') or '').strip()
        if name and query_string:
            save_current_filter(name, query_string)
            h.log_action('save_filter', [], f'保存筛选视图：{name}')
        h._redirect('/')
        return

    if h.path == '/save-dashboard-order':
        order = (data.get('dashboard_order', '') or '').strip()
        if order:
            set_dashboard_order(order)
            h.log_action('save_dashboard_order', [], f'保存首页模块顺序：{order}')
        h._redirect('/')
        return

    if h.path == '/delete-filter':
        fid = data.get('filter_id', '')
        if fid:
            delete_saved_filter(fid)
            h.log_action('delete_filter', [], f'删除筛选视图 id={fid}')
        h._redirect('/')
        return

    if h.path == '/rename-filter':
        fid = data.get('filter_id', '')
        new_name = (data.get('new_name', '') or '').strip()
        if fid and new_name:
            rename_saved_filter(fid, new_name)
            h.log_action('rename_filter', [], f'重命名筛选视图 id={fid} -> {new_name}')
        h._redirect('/')
        return

    if h.path == '/update':
        rid = data.get('id', '')
        picks_repo.update_pick(
            rid=rid,
            pick_date=data.get('pick_date', ''),
            code=data.get('code', ''),
            name=data.get('name', ''),
            pick_price=num(data.get('pick_price', '0')),
            signal=data.get('signal', ''),
            source_channel=data.get('source_channel', ''),
            reason_tag=data.get('reason_tag', ''),
            note=data.get('note', ''),
            review_status=data.get('review_status', '未复盘'),
            review_comment=data.get('note', ''),
            content_title=data.get('content_title', ''),
            content_ref=data.get('content_ref', ''),
            result_grade=data.get('result_grade', '待定'),
            inquiry_count=int_num(data.get('inquiry_count', 0)),
            deal_status=data.get('deal_status', '未成交'),
            secondary_spread=data.get('secondary_spread', '否'),
        )
        h.log_action('update', [rid], f'编辑记录 {rid}')
        h._redirect('/?updated=1')
        return

    # Simple one-liners (batch updates) stay as-is, but routed here.
    if h.path == '/archive':
        rid = data.get('id', '')
        picks_repo.set_archived(rid, True)
        h.log_action('archive', [rid], '单条归档')
        h._redirect('/?archived=1')
        return
    if h.path == '/unarchive':
        rid = data.get('id', '')
        picks_repo.set_archived(rid, False)
        h.log_action('unarchive', [rid], '单条恢复')
        h._redirect('/?unarchived=1')
        return
    if h.path == '/delete':
        rid = data.get('id', '')
        picks_repo.delete_pick(rid)
        h.log_action('delete', [rid], '单条删除')
        h._redirect('/?deleted=1')
        return

    if h.path == '/batch-archive':
        ids = h._selected_ids(data)
        picks_repo.batch_set_archived(ids, True)
        h.log_action('batch_archive', ids, f'批量归档 {len(ids)} 条')
        h._redirect('/?batch_archived=1')
        return
    if h.path == '/batch-unarchive':
        ids = h._selected_ids(data)
        picks_repo.batch_set_archived(ids, False)
        h.log_action('batch_unarchive', ids, f'批量恢复 {len(ids)} 条')
        h._redirect('/?batch_unarchived=1')
        return
    if h.path == '/batch-delete':
        ids = h._selected_ids(data)
        picks_repo.batch_delete(ids)
        h.log_action('batch_delete', ids, f'批量删除 {len(ids)} 条')
        h._redirect('/?batch_deleted=1')
        return
    if h.path == '/batch-review':
        ids = h._selected_ids(data)
        status = data.get('review_status', '未复盘')
        picks_repo.batch_set_review_status(ids, status)
        h.log_action('batch_review', ids, f'批量改复盘状态为 {status}')
        h._redirect('/?batch_reviewed=1')
        return
    if h.path == '/batch-grade':
        ids = h._selected_ids(data)
        grade = data.get('result_grade', '待定')
        picks_repo.batch_set_result_grade(ids, grade)
        h.log_action('batch_grade', ids, f'批量改评级为 {grade}')
        h._redirect('/?batch_grade=1')
        return
    if h.path == '/batch-deal':
        ids = h._selected_ids(data)
        ds = data.get('deal_status', '未成交')
        picks_repo.batch_set_deal_status(ids, ds)
        h.log_action('batch_deal', ids, f'批量改成交状态为 {ds}')
        h._redirect('/?batch_deal=1')
        return
    if h.path == '/batch-spread':
        ids = h._selected_ids(data)
        sp = data.get('secondary_spread', '否')
        picks_repo.batch_set_secondary_spread(ids, sp)
        h.log_action('batch_spread', ids, f'批量改二次传播为 {sp}')
        h._redirect('/?batch_spread=1')
        return

    
    if h.path == '/users/create':
        s = h.session() or {}
        if (s.get('role') or '') != 'admin':
            h._send(403, 'forbidden', 'text/plain; charset=utf-8'); return
        ok, msg = users_admin_service.create_user(data.get('username',''), data.get('password',''), data.get('role','editor'))
        h.log_action('create_user', [], msg)
        h._send(200, render_users_page(msg))
        return

    if h.path == '/users/toggle':
        s = h.session() or {}
        if (s.get('role') or '') != 'admin':
            h._send(403, 'forbidden', 'text/plain; charset=utf-8'); return
        ok, msg = users_admin_service.toggle_user_active(data.get('user_id',0), data.get('is_active',0))
        h.log_action('toggle_user', [data.get('user_id',0)], msg)
        h._send(200, render_users_page(msg))
        return

    if h.path == '/users/reset':
        s = h.session() or {}
        if (s.get('role') or '') != 'admin':
            h._send(403, 'forbidden', 'text/plain; charset=utf-8'); return
        ok, msg = users_admin_service.reset_password(data.get('user_id',0), data.get('new_password',''))
        h.log_action('reset_password', [data.get('user_id',0)], msg)
        h._send(200, render_users_page(msg))
        return
    h._send(404, 'not found', 'text/plain; charset=utf-8')
