"""Page: login."""

from backend.ui.html_helpers import esc


def render_login(error=''):
    err = f'<div class="err">{esc(error)}</div>' if error else ''
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>登录宣传票复盘系统</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f6f7fb;padding:24px}}.box{{max-width:420px;margin:10vh auto;background:#fff;padding:24px;border-radius:16px;box-shadow:0 6px 20px rgba(0,0,0,.06)}}input{{width:100%;padding:12px;border:1px solid #d1d5db;border-radius:10px;box-sizing:border-box}}button{{margin-top:12px;width:100%;padding:12px;background:#111827;color:#fff;border:0;border-radius:10px}}.muted{{color:#6b7280;font-size:14px}}.err{{background:#fef2f2;color:#991b1b;border:1px solid #fecaca;padding:10px;border-radius:10px;margin:12px 0}}</style></head><body><div class="box"><h1>登录宣传票复盘系统</h1><div class="muted">v4.7 多用户登录已启用</div>{err}<form method="post" action="/login"><input name="username" placeholder="用户名" required style="margin-top:12px"><input type="password" name="password" placeholder="密码" required style="margin-top:12px"><button type="submit">登录</button></form></div></body></html>'''
