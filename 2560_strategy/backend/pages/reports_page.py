"""Page: reports."""

from backend.services.reports_service import report_summary_text, weekly_report_rows, monthly_report_rows
from backend.ui.html_helpers import esc, render_nav, layout_page


def render_reports_page():
    weekly = weekly_report_rows()
    monthly = monthly_report_rows()
    summary_text = report_summary_text()

    weekly_text = summary_text.get('weekly', '')
    monthly_text = summary_text.get('monthly', '')
    boss_text = summary_text.get('boss', '')

    weekly_rows = ''.join([
        f"<tr><td>{esc(r['period'])}</td><td>{esc(r['total'])}</td><td>{esc(r['worthy_total'])}</td><td>{esc(r['deal_total'])}</td></tr>"
        for r in weekly
    ]) or '<tr><td colspan="4">暂无数据</td></tr>'

    monthly_rows = ''.join([
        f"<tr><td>{esc(r['month'])}</td><td>{esc(r['total'])}</td><td>{esc(r['worthy_total'])}</td><td>{esc(r['deal_total'])}</td><td>{esc(r['avg_inquiry'])}</td></tr>"
        for r in monthly
    ]) or '<tr><td colspan="5">暂无数据</td></tr>'

    body = f'''<div class="topline"><div><h1>报表中心</h1><div class="muted">集中查看周报/月报，适合正式复盘和团队同步</div></div><div><a class="btn" href="/weekly-report.csv">导出周报CSV</a><a class="btn" href="/monthly-report.csv">导出月报CSV</a></div></div>
<div class='nav'>{render_nav('reports')}</div>
<div class="grid3 section"><div class="card"><h2>自动周报文案</h2><div class="muted">适合直接发群、发团队同步</div><textarea style="width:100%;min-height:140px;margin-top:10px;border:1px solid #d1d5db;border-radius:12px;padding:12px;box-sizing:border-box" onclick="this.select()">{weekly_text}</textarea><div class="muted">点击文本框即可一键全选复制</div></div><div class="card"><h2>自动月报文案</h2><div class="muted">适合月复盘、月总结、汇报</div><textarea style="width:100%;min-height:140px;margin-top:10px;border:1px solid #d1d5db;border-radius:12px;padding:12px;box-sizing:border-box" onclick="this.select()">{monthly_text}</textarea><div class="muted">点击文本框即可一键全选复制</div></div><div class="card"><h2>老板汇报版文案</h2><div class="muted">更短、更像管理层汇报口径</div><textarea style="width:100%;min-height:140px;margin-top:10px;border:1px solid #d1d5db;border-radius:12px;padding:12px;box-sizing:border-box" onclick="this.select()">{boss_text}</textarea><div class="muted">适合直接复制给老板/合伙人</div></div></div>
<div class="grid2 section"><div class="card"><h2>近12周周报</h2><div class="tablewrap"><table><thead><tr><th>周</th><th>总记录</th><th>值得复讲</th><th>已成交</th></tr></thead><tbody>{weekly_rows}</tbody></table></div></div><div class="card"><h2>月报汇总</h2><div class="tablewrap"><table><thead><tr><th>月份</th><th>总记录</th><th>值得复讲</th><th>已成交</th><th>平均咨询数</th></tr></thead><tbody>{monthly_rows}</tbody></table></div></div></div>'''

    return layout_page('报表中心', body)
