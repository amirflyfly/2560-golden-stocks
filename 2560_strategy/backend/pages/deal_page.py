"""Page: deal review."""

from backend.repositories.db import q, q1
from backend.ui.html_helpers import esc, render_nav, layout_page


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
