"""Page: dashboard (main panel)."""

from datetime import datetime

from backend.services.filters_service import get_saved_filters, get_dashboard_order
from backend.repositories import picks_repo
from backend.services.flash_service import get_flash
from backend.services.query_service import filter_where
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
from backend.services.http_utils import build_query_string
from backend.ui.html_helpers import esc, select_options, bar_html, render_nav, render_pagination, line_table_html
from backend.app_config import (
    PAGE_SIZE,
    REVIEW_STATUS_OPTIONS,
    RESULT_GRADE_OPTIONS,
    DEAL_STATUS_OPTIONS,
    SPREAD_OPTIONS,
)


def render_dashboard(params=None, port=8765):
    params = params or {}
    flash = get_flash(params)
    page = max(1, int((params.get('page', ['1'])[0] or '1')))
    saved_filters = get_saved_filters()
    dashboard_order = get_dashboard_order()

    overview = dashboard_overview()
    kpi = dashboard_kpi()
    by_channel = dashboard_channels()
    by_tag = dashboard_tags()
    by_status = dashboard_review_status()
    by_grade = dashboard_grades()
    by_deal = dashboard_deals()
    trend_30d = dashboard_trend_30d()
    worthy_trend = dashboard_worthy_trend_30d()
    deal_trend = dashboard_deal_trend_30d()
    recent_logs = recent_operation_logs(15)

    where, args = filter_where(params)
    filter_count = picks_repo.count_picks(where, args)
    offset = (page - 1) * PAGE_SIZE
    latest = picks_repo.list_picks(where, args, limit=PAGE_SIZE, offset=offset)

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
    grade_opts = ''.join([
        f"<option value='{esc(v)}' {'selected' if (params.get('grade',[''])[0] == v) else ''}>{esc(v)}</option>"
        for v in RESULT_GRADE_OPTIONS
    ])
    deal_opts = ''.join([
        f"<option value='{esc(v)}' {'selected' if (params.get('deal_status',[''])[0] == v) else ''}>{esc(v)}</option>"
        for v in DEAL_STATUS_OPTIONS
    ])

    latest_rows = ''.join([
        f"<tr><td><input type='checkbox' name='ids' value='{r['id']}'></td><td>{esc(r['pick_date'])}</td><td>{esc(r['name'])}</td><td>{esc(r['code'])}</td><td>{esc(r['pick_price'])}</td><td>{esc(r['source_channel'])}</td><td>{esc(r['reason_tag'])}</td><td>{esc(r['review_status'])}</td><td>{esc(r['result_grade'])}</td><td>{esc(r['deal_status'])}</td><td>{esc(r['inquiry_count'])}</td><td>{esc(r['secondary_spread'])}</td><td><span class='badge {'badge-archived' if r['archived'] else 'badge-active'}'>{'已归档' if r['archived'] else '使用中'}</span></td><td><a class='txtbtn' href='/edit?id={r['id']}'>编辑</a><form method='post' action='/{'unarchive' if r['archived'] else 'archive'}' class='inline-form'><input type='hidden' name='id' value='{r['id']}'><button type='submit' class='linkbtn'>{'恢复' if r['archived'] else '归档'}</button></form><form method='post' action='/delete' class='inline-form' onsubmit=\"return confirm('确认删除这条记录？删除后不可恢复。')\"><input type='hidden' name='id' value='{r['id']}'><button type='submit' class='linkbtn danger'>删除</button></form></td></tr>"
        for r in latest
    ]) or '<tr><td colspan="14">暂无数据</td></tr>'

    log_rows = ''.join([
        f"<tr><td>{esc(r['created_at'])}</td><td>{esc(r.get('username',''))}</td><td>{esc(r.get('ip',''))}</td><td>{esc(r['action'])}</td><td>{esc(r['target_ids'])}</td><td>{esc(r['detail'])}</td></tr>"
        for r in recent_logs
    ]) or '<tr><td colspan="6">暂无日志</td></tr>'

    flash_html = (
        f"<div class=\"card\" style=\"background:#ecfdf5;color:#065f46;border:1px solid #a7f3d0\">{esc(flash)}</div>"
        if flash else ''
    )

    filter_query = build_query_string(params)
    export_json_href = '/export' + (f'?{filter_query}' if filter_query else '')
    export_csv_href = '/export.csv' + (f'?{filter_query}' if filter_query else '')
    monthly_href = '/monthly-report.csv'

    saved_filter_links = (
        ''.join([
            f"<div style='display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:8px 0'><a class='page-link' href='/?{esc(r['query_string'])}'>{esc(r['name'])}</a><form method='post' action='/rename-filter' class='inline-form' style='display:inline-flex;gap:6px;align-items:center'><input type='hidden' name='filter_id' value='{r['id']}'><input name='new_name' value='{esc(r['name'])}' style='width:160px;padding:6px 8px;border:1px solid #d1d5db;border-radius:8px'><button type='submit' class='linkbtn'>改名</button></form><form method='post' action='/delete-filter' class='inline-form'><input type='hidden' name='filter_id' value='{r['id']}'><button type='submit' class='linkbtn danger'>删除</button></form></div>"
            for r in saved_filters
        ])
        or "<span class='muted'>还没有保存的常用筛选</span>"
    )

    csv_template = 'pick_date,code,name,pick_price,signal,source_channel,reason_tag,review_status,result_grade,inquiry_count,deal_status,secondary_spread,content_title,content_ref,note\n2026-03-09,600519,贵州茅台,1688,强势趋势,douyin,趋势突破,值得复讲,A,12,已咨询,是,爆款复盘01,vid-001,样例备注'

    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>宣传票复盘系统 v4.7</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f6f7fb;color:#1f2937;margin:0;padding:24px}} .wrap{{max-width:1540px;margin:0 auto}} .grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:16px}} .grid2{{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}} .grid3{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}} .card{{background:#fff;border-radius:16px;padding:18px;box-shadow:0 6px 20px rgba(0,0,0,.06)}} h1,h2{{margin:0 0 12px}} .muted{{color:#6b7280;font-size:14px}} .num{{font-size:32px;font-weight:700}} table{{width:100%;border-collapse:collapse}} th,td{{padding:10px;border-bottom:1px solid #eee;text-align:left;font-size:14px;vertical-align:top;white-space:nowrap}} th{{background:#fafafa}} .section{{margin-top:20px}} input,select,textarea{{width:100%;padding:10px;border:1px solid #d1d5db;border-radius:10px;box-sizing:border-box}} textarea{{min-height:90px}} .bigtextarea{{min-height:180px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}} .formgrid3{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}} button{{background:#111827;color:#fff;border:0;border-radius:10px;padding:10px 16px;cursor:pointer}} a.btn{{display:inline-block;background:#111827;color:#fff;text-decoration:none;padding:10px 16px;border-radius:10px;margin-right:8px}} .bar-row,.line-row{{display:grid;grid-template-columns:140px 1fr 62px;gap:10px;align-items:center;margin:8px 0}} .bar-track,.line-track{{height:12px;background:#eef2ff;border-radius:999px;overflow:hidden}} .bar-fill,.line-fill{{height:100%;border-radius:999px}} .inline-form{{display:inline}} .linkbtn{{background:none;color:#2563eb;padding:0 6px;border:none;border-radius:0}} .linkbtn.danger{{color:#dc2626}} .txtbtn{{color:#2563eb;text-decoration:none;padding-right:6px}} .badge{{display:inline-block;padding:4px 8px;border-radius:999px;font-size:12px}} .badge-active{{background:#dcfce7;color:#166534}} .badge-archived{{background:#f3f4f6;color:#4b5563}} .topline{{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap}} .bulkbar{{display:flex;gap:8px;flex-wrap:wrap;align-items:center}} .bulkbar select{{width:auto;min-width:140px}} .smallbtn{{padding:8px 12px;border-radius:10px}} .tablewrap{{overflow:auto}} .subtle{{font-size:12px;color:#6b7280}} @media (max-width:980px){{.grid,.grid2,.grid3,.formgrid3{{grid-template-columns:1fr}} body{{padding:16px}} .wrap{{max-width:100%}}}}</style><script>function toggleAll(source){{document.querySelectorAll('input[name="ids"]').forEach(cb=>cb.checked=source.checked);}} function ensureSelected(form){{const checked=form.querySelectorAll('input[name="ids"]:checked'); if(!checked.length){{alert('请先勾选至少一条记录'); return false;}} return true;}}</script></head><body><div class="wrap"><div class="topline"><div><h1>宣传票复盘系统 v4.7</h1><div class="muted">更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} · 已启用密码保护 · 本地端口 {port}</div></div><div class="muted">本次新增：排行榜指标切换 / 首页排序配置继续可用</div></div><div class='nav'>{render_nav('dashboard')}</div>{flash_html}
<div class="grid section"><div class="card"><div class="muted">累计记录</div><div class="num">{overview.get('total',0)}</div></div><div class="card"><div class="muted">使用中</div><div class="num">{overview.get('active_total',0) or 0}</div></div><div class="card"><div class="muted">已成交数</div><div class="num">{int(overview.get('deal_total') or 0)}</div></div><div class="card"><div class="muted">二次传播数</div><div class="num">{int(overview.get('spread_total') or 0)}</div></div><div class="card"><div class="muted">值得复讲总数</div><div class="num">{int(overview.get('worthy_total') or 0)}</div></div></div>
<div class="grid3 section"><div class="card"><div class="muted">本周新增</div><div class="num">{int(kpi.get('week_new') or 0)}</div><div class="subtle">反映本周录入节奏</div></div><div class="card"><div class="muted">近30天新增</div><div class="num">{int(kpi.get('last30_new') or 0)}</div><div class="subtle">观察数据沉淀速度</div></div><div class="card"><div class="muted">平均咨询数</div><div class="num">{kpi.get('avg_inquiry') or 0}</div><div class="subtle">衡量内容带来互动的能力</div></div></div>
<div class="section card"><h2>首页模块排序</h2><div class='muted'>当前顺序：{dashboard_order}</div><form method='post' action='/save-dashboard-order' style='margin-top:12px'><div class='formgrid3'><div><label>模块顺序字符串</label><input name='dashboard_order' value='{dashboard_order}'></div><div class='muted' style='display:flex;align-items:end'>可用值示例：kpi,trend,filters,actions,records,logs</div><div style='display:flex;align-items:end'><button type='submit'>保存首页顺序</button></div></div></form></div><div class="section card"><h2>备份 / 恢复</h2><div class='muted'>建议每周至少备份一次（方案B：db+关键文件）。恢复前系统会自动再备份一次当前数据。</div><p><a class="btn" href="/backup.zip">下载备份包（zip）</a> <a class="btn" href="/restore">上传恢复</a></p></div>
<div class="section card"><h2>快捷入口</h2><p><a class="btn" href="/deal-review">成交复盘页</a><a class="btn" href="/leaderboards">排行榜页</a><a class="btn" href="/reports">报表中心</a><a class="btn" href="{monthly_href}">导出月报 CSV</a><a class="btn" href="{export_json_href}">导出 JSON</a><a class="btn" href="{export_csv_href}">导出 CSV</a><a class="btn" href="/logout">退出登录</a></p></div><div class="section card"><h2>常用筛选视图</h2><div class='pagination'>{saved_filter_links}</div><div class='muted' style='margin-top:8px'>点击“重命名”会先自动生成一个占位新名字，你后面如果要我再做成弹窗改名也可以继续升级。</div><form method='post' action='/save-filter' style='margin-top:12px'><div class='formgrid3'><div><label>视图名称</label><input name='filter_name' placeholder='例如：抖音已成交 / A级内容'></div><div><label>当前筛选串</label><input name='query_string' value='{filter_query}' placeholder='会自动带上当前筛选参数'></div><div style='display:flex;align-items:end'><button type='submit'>保存当前筛选</button></div></div></form></div>
<div class="grid3 section"><div class="card"><h2>结果评级分布</h2>{bar_html(by_grade, color='#0f766e')}</div><div class="card"><h2>成交状态分布</h2>{bar_html(by_deal, color='#ca8a04')}</div><div class="card"><h2>标签分布</h2>{bar_html(by_tag, color='#dc2626')}</div></div>
<div class="grid3 section"><div class="card"><h2>近30天录入趋势</h2>{line_table_html(trend_30d, color='#7c3aed')}</div><div class="card"><h2>近30天值得复讲趋势</h2>{line_table_html(worthy_trend, color='#0891b2')}</div><div class="card"><h2>近30天成交趋势</h2>{line_table_html(deal_trend, color='#16a34a')}</div></div>
<div class="section card"><h2>筛选 / 搜索</h2><form method="get" action="/"><div class="formgrid3"><div><label>关键词</label><input name="keyword" value="{esc((params.get('keyword',[''])[0] or '').strip())}" placeholder="股票代码/股票名称/内容标题/内容编号"></div><div><label>渠道</label><select name="channel"><option value="">全部</option>{channel_opts}</select></div><div><label>标签</label><select name="tag"><option value="">全部</option>{tag_opts}</select></div><div><label>复盘状态</label><select name="status"><option value="">全部</option>{status_opts}</select></div><div><label>结果评级</label><select name="grade"><option value="">全部</option>{grade_opts}</select></div><div><label>成交状态</label><select name="deal_status"><option value="">全部</option>{deal_opts}</select></div><div><label>开始日期</label><input type="date" name="date_from" value="{esc((params.get('date_from',[''])[0] or '').strip())}"></div><div><label>结束日期</label><input type="date" name="date_to" value="{esc((params.get('date_to',[''])[0] or '').strip())}"></div><div><label>记录范围</label><select name="archive"><option value="active" {'selected' if (params.get('archive',['active'])[0] or 'active')=='active' else ''}>仅使用中</option><option value="archived" {'selected' if (params.get('archive',['active'])[0] or 'active')=='archived' else ''}>仅已归档</option><option value="all" {'selected' if (params.get('archive',['active'])[0] or 'active')=='all' else ''}>全部记录</option></select></div></div><div style="margin-top:12px"><button type="submit">筛选结果</button> <a class="btn" href="/">清空筛选</a></div><div class="muted" style="margin-top:8px">当前筛选结果：{filter_count} 条</div></form></div>
<div class="grid2 section"><div class="card"><h2>新增记录</h2><form method="post" action="/add"><div class="formgrid3"><div><label>日期</label><input name="pick_date" value="{datetime.now().strftime('%Y-%m-%d')}" required></div><div><label>股票代码</label><input name="code" required></div><div><label>股票名称</label><input name="name" required></div><div><label>推荐价</label><input name="pick_price" required></div><div><label>信号</label><input name="signal"></div><div><label>渠道</label><input name="source_channel" placeholder="douyin/xhs/live/community"></div><div><label>标签</label><input name="reason_tag" placeholder="趋势突破/缩量回踩"></div><div><label>复盘结论</label><select name="review_status">{select_options(REVIEW_STATUS_OPTIONS, '未复盘')}</select></div><div><label>结果评级</label><select name="result_grade">{select_options(RESULT_GRADE_OPTIONS, '待定')}</select></div><div><label>咨询数</label><input name="inquiry_count" value="0"></div><div><label>成交状态</label><select name="deal_status">{select_options(DEAL_STATUS_OPTIONS, '未成交')}</select></div><div><label>二次传播</label><select name="secondary_spread">{select_options(SPREAD_OPTIONS, '否')}</select></div><div><label>内容标题</label><input name="content_title"></div><div><label>内容编号/链接</label><input name="content_ref"></div></div><div style="margin-top:12px"><label>备注/复盘评论</label><textarea name="note"></textarea></div><div style="margin-top:12px"><button type="submit">保存到系统</button></div></form></div><div class="card"><h2>批量 CSV 导入</h2><form method="post" action="/bulk-import"><div style="margin-top:12px"><textarea style="min-height:180px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace" name="csv_text" placeholder="{esc(csv_template)}"></textarea></div><div style="margin-top:12px"><button type="submit">批量导入 CSV</button></div></form></div></div>
<div class="section card"><div class="topline" style="margin-bottom:12px"><h2>最新记录</h2><div class="subtle">支持批量归档 / 恢复 / 删除 / 批量改复盘状态 / 评级 / 成交 / 传播</div></div><form method="post" action="/batch-review" onsubmit="return ensureSelected(this)"><div class="bulkbar" style="margin-bottom:12px"><select name="review_status">{select_options(REVIEW_STATUS_OPTIONS, '值得复讲')}</select><button type="submit" class="smallbtn">批量改复盘状态</button><select name="result_grade">{select_options(RESULT_GRADE_OPTIONS, 'A')}</select><button formaction="/batch-grade" type="submit" class="smallbtn">批量改评级</button><select name="deal_status">{select_options(DEAL_STATUS_OPTIONS, '已咨询')}</select><button formaction="/batch-deal" type="submit" class="smallbtn">批量改成交状态</button><select name="secondary_spread">{select_options(SPREAD_OPTIONS, '是')}</select><button formaction="/batch-spread" type="submit" class="smallbtn">批量改传播</button><button formaction="/batch-archive" type="submit" class="smallbtn">批量归档</button><button formaction="/batch-unarchive" type="submit" class="smallbtn">批量恢复</button><button formaction="/batch-delete" type="submit" class="smallbtn" onclick="return ensureSelected(this.form) && confirm('确认批量删除所选记录？删除后不可恢复。')">批量删除</button></div><div class="tablewrap"><table><thead><tr><th><input type="checkbox" onclick="toggleAll(this)"></th><th>日期</th><th>股票</th><th>代码</th><th>推荐价</th><th>渠道</th><th>标签</th><th>复盘结论</th><th>评级</th><th>成交状态</th><th>咨询数</th><th>二次传播</th><th>状态</th><th>操作</th></tr></thead><tbody>{latest_rows}</tbody></table></div>{render_pagination(page, filter_count, params)}</form></div>
<div class="section card"><h2>最近操作日志</h2><div class="tablewrap"><table><thead><tr><th>时间</th><th>用户</th><th>IP</th><th>动作</th><th>记录ID</th><th>说明</th></tr></thead><tbody>{log_rows}</tbody></table></div></div></div></body></html>'''
