"""Reports logic.

Step 3 of the web_panel.py split: move report aggregation + summary text here.
"""

from backend.repositories.db import q


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
