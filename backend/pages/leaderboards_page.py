"""Page: leaderboards."""

from backend.services.leaderboard_service import leaderboards
from backend.ui.html_helpers import bar_html, render_nav, layout_page


def render_leaderboards_page(range_key='30d', metric='default'):
    data = leaderboards(range_key=range_key, metric=metric)

    range_links = ''.join([
        f"<a class='{'navlink nav-active' if data['range_key'] == rk else 'navlink'}' href='/leaderboards?range={rk}&metric={data['metric']}'>{label}</a>"
        for rk, label in [('7d', '近7天'), ('30d', '近30天'), ('90d', '近90天'), ('all', '全部')]
    ])
    metric_links = ''.join([
        f"<a class='{'navlink nav-active' if data['metric'] == mk else 'navlink'}' href='/leaderboards?range={data['range_key']}&metric={mk}'>{label}</a>"
        for mk, label in [('default', '默认榜单'), ('spread', '传播榜单')]
    ])

    body = f'''<div class="topline"><div><h1>排行榜页</h1><div class="muted">把渠道、标签、成交、咨询这些关键指标拆开看，方便你抓重点</div></div><div><a class="btn" href="/">返回面板</a></div></div>
<div class='nav'>{render_nav('leaderboards')}</div>
<div class='nav'>{range_links}</div>
<div class='nav'>{metric_links}</div>
<div class="grid2 section"><div class="card"><h2>渠道记录 Top10</h2>{bar_html(data['channel_rank'], color='#4f46e5')}</div><div class="card"><h2>值得复讲标签 Top10</h2>{bar_html(data['worthy_rank'], color='#0ea5e9')}</div></div>
<div class="grid2 section"><div class="card"><h2>成交渠道 Top10</h2>{bar_html(data['deal_rank'], color='#16a34a')}</div><div class="card"><h2>{data['right_title']}</h2>{bar_html(data['right_rows'], color=data['right_color'])}</div></div>'''

    return layout_page('排行榜页', body)
