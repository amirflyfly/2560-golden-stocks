"""Page: edit form."""

from backend.ui.html_helpers import esc, label, select_options, layout_page
from backend.app_config import (
    REVIEW_STATUS_OPTIONS,
    RESULT_GRADE_OPTIONS,
    DEAL_STATUS_OPTIONS,
    SPREAD_OPTIONS,
)


def render_edit_form(record):
    if not record:
        return '<!doctype html><html><body>记录不存在</body></html>'

    body = f'''<div class="card"><h1>编辑宣传票记录</h1><form method="post" action="/update"><input type="hidden" name="id" value="{record['id']}"><div class="grid"><div><label>日期</label><input name="pick_date" value="{esc(record['pick_date'])}" required></div><div><label>股票代码</label><input name="code" value="{esc(record['code'])}" required></div><div><label>股票名称</label><input name="name" value="{esc(record['name'])}" required></div><div><label>推荐价</label><input name="pick_price" value="{esc(record['pick_price'])}" required></div><div><label>信号</label><input name="signal" value="{esc(record['signal'])}"></div><div><label>渠道</label><input name="source_channel" value="{esc(record['source_channel'])}"></div><div><label>标签</label><input name="reason_tag" value="{esc(record['reason_tag'])}"></div><div><label>复盘结论</label><select name="review_status">{select_options(REVIEW_STATUS_OPTIONS, label(record.get('review_status'), '未复盘'))}</select></div><div><label>结果评级</label><select name="result_grade">{select_options(RESULT_GRADE_OPTIONS, label(record.get('result_grade'), '待定'))}</select></div><div><label>咨询数</label><input name="inquiry_count" value="{esc(record.get('inquiry_count', 0))}"></div><div><label>成交状态</label><select name="deal_status">{select_options(DEAL_STATUS_OPTIONS, label(record.get('deal_status'), '未成交'))}</select></div><div><label>二次传播</label><select name="secondary_spread">{select_options(SPREAD_OPTIONS, label(record.get('secondary_spread'), '否'))}</select></div><div><label>内容标题</label><input name="content_title" value="{esc(record['content_title'])}"></div><div><label>内容编号/链接</label><input name="content_ref" value="{esc(record['content_ref'])}"></div></div><div style="margin-top:12px"><label>备注/复盘评论</label><textarea name="note" style="width:100%;min-height:100px">{esc(record['note'])}</textarea></div><div style="margin-top:16px"><button type="submit">保存修改</button><a class="btn" href="/">返回面板</a></div></form></div>'''

    return layout_page('编辑记录', body)
