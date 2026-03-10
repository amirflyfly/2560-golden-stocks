"""HTML/UI helper functions.

Phase 2 split: move pure rendering helpers out of web_panel.py.
Keep dependency-light and side-effect free.
"""

import html as _html


def label(v, default='-'):
    if v is None:
        return default
    s = str(v).strip()
    return s if s and s.lower() != 'nan' else default


def esc(v):
    return _html.escape(label(v, ''))


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
            display = f'{display}{suffix}'
        items.append(
            f"<div class='bar-row'><div class='muted'>{name}</div>"
            f"<div class='bar-track'><div class='bar-fill' style='width:{width}%;background:{color}'></div></div>"
            f"<div style='text-align:right'>{esc(display)}</div></div>"
        )
    return ''.join(items)


def render_nav(active='dashboard'):
    items = [
        ('/', 'dashboard', '面板'),
        ('/deal-review', 'deal', '成交复盘'),
        ('/leaderboards', 'leaderboards', '排行榜'),
        ('/reports', 'reports', '报表中心'),
    ]
    links = []
    for href, key, label_ in items:
        cls = 'navlink nav-active' if active == key else 'navlink'
        links.append(f"<a class='{cls}' href='{href}'>{esc(label_)}</a>")
    return '<div class="nav">' + ''.join(links) + '</div>'


def render_pagination(page, total_count, base_params, page_size=20):
    # base_params: dict[str, list[str]] (from parse_qs)
    # Keep it small: only render links; query string building stays in web_panel.py.
    pages = max(1, int((total_count + page_size - 1) / page_size))
    if pages <= 1:
        return ''
    links = []
    for p in range(1, pages + 1):
        cls = 'page-link page-active' if p == page else 'page-link'
        links.append(f"<a class='{cls}' href='?page={p}'>{p}</a>")
    return "<div class='pagination'>" + ''.join(links) + '</div>'


def layout_page(title, body):
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)}</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f6f7fb;color:#1f2937;margin:0;padding:24px}}
.wrap{{max-width:1540px;margin:0 auto}} .card{{background:#fff;border-radius:16px;padding:18px;box-shadow:0 6px 20px rgba(0,0,0,.06)}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}} .grid2{{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}}
.bar-row,.line-row{{display:grid;grid-template-columns:140px 1fr 62px;gap:10px;align-items:center;margin:8px 0}} .bar-track,.line-track{{height:12px;background:#eef2ff;border-radius:999px;overflow:hidden}} .bar-fill,.line-fill{{height:100%;border-radius:999px}}
.muted{{color:#6b7280;font-size:14px}} .num{{font-size:32px;font-weight:700}} .topline{{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap}} a.btn{{display:inline-block;background:#111827;color:#fff;text-decoration:none;padding:10px 16px;border-radius:10px;margin-right:8px}} .nav{{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}} .navlink{{display:inline-block;padding:10px 14px;border-radius:999px;background:#fff;color:#111827;text-decoration:none;border:1px solid #e5e7eb}} .nav-active{{background:#111827;color:#fff;border-color:#111827}} .pagination{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:14px}} .page-link{{display:inline-block;padding:6px 10px;border-radius:10px;background:#fff;color:#111827;text-decoration:none;border:1px solid #e5e7eb}} .page-active{{background:#111827;color:#fff;border-color:#111827}} table{{width:100%;border-collapse:collapse}} th,td{{padding:10px;border-bottom:1px solid #eee;text-align:left;font-size:14px;vertical-align:top}} th{{background:#fafafa}} .tablewrap{{overflow:auto}} @media (max-width:980px){{.grid,.grid2{{grid-template-columns:1fr}} body{{padding:16px}}}}</style></head><body><div class="wrap">{body}</div></body></html>'''
