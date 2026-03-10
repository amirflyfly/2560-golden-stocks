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
from backend.services.filters_service import (
    get_saved_filters,
    get_dashboard_order,
    set_dashboard_order,
    save_current_filter,
    delete_saved_filter,
    rename_saved_filter,
)
from backend.services.reports_service import report_summary_text, monthly_report_rows, weekly_report_rows
from backend.services.query_service import filter_where
from backend.services.io_service import bulk_import_from_csv, rows_to_csv
from backend.services.format_service import num, int_num
from backend.services.http_utils import parse_cookies, parse_multi_post, as_list, build_query_string
from backend.services.flash_service import get_flash
from backend.services.auth_service import ensure_secret
from backend.services.logs_service import log_action
from backend.routes.panel_routes import handle_get, handle_post

from backend.pages.dashboard_page import render_dashboard
from backend.pages.login_page import render_login
from backend.pages.edit_page import render_edit_form
from backend.pages.deal_page import render_deal_review_page
from backend.pages.leaderboards_page import render_leaderboards_page
from backend.pages.reports_page import render_reports_page

from backend.services.leaderboard_service import leaderboards
from backend.services.dashboard_service import (
    dashboard_overview,
    dashboard_kpi,
    dashboard_channels,
    dashboard_tags,
    dashboard_review_status,
    dashboard_grades,
    dashboard_deals,
    dashboard_trend_30d,
    dashboard_worthy_trend_30d,
    dashboard_deal_trend_30d,
    recent_operation_logs,
)
from backend.ui.html_helpers import (
    label,
    esc,
    select_options,
    bar_html,
    render_nav,
    render_pagination,
    layout_page,
    line_table_html,
)

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
PANEL_PASSWORD = ensure_secret(DATA_DIR, SECRET_PATH)


ensure_schema()


class Handler(BaseHTTPRequestHandler):
    COOKIE_NAME = COOKIE_NAME
    PANEL_PASSWORD = PANEL_PASSWORD
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

    render_dashboard = staticmethod(render_dashboard)
    render_login = staticmethod(render_login)
    render_edit_form = staticmethod(render_edit_form)
    render_deal_review_page = staticmethod(render_deal_review_page)
    render_leaderboards_page = staticmethod(render_leaderboards_page)
    render_reports_page = staticmethod(render_reports_page)
    log_action = staticmethod(log_action)

    def do_GET(self):
        return handle_get(self)

    def do_POST(self):
        return handle_post(self)




if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f'v4.7 server running on http://0.0.0.0:{PORT}')
    print(f'panel password: {PANEL_PASSWORD}')
    server.serve_forever()
