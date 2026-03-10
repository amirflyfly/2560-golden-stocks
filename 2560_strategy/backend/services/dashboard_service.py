"""Dashboard data aggregation.

Step 5 of the web_panel.py split: move dashboard queries and aggregations here.
Rendering stays in web_panel.py.
"""

from backend.repositories.db import q, q1


def dashboard_overview():
    return q1(
        '''SELECT COUNT(*) AS total,
                  SUM(CASE WHEN COALESCE(archived,0)=0 THEN 1 ELSE 0 END) AS active_total,
                  SUM(CASE WHEN COALESCE(NULLIF(deal_status,''),'未成交')='已成交' THEN 1 ELSE 0 END) AS deal_total,
                  SUM(CASE WHEN COALESCE(NULLIF(secondary_spread,''),'否')='是' THEN 1 ELSE 0 END) AS spread_total,
                  SUM(CASE WHEN COALESCE(NULLIF(review_status,''),'未复盘')='值得复讲' THEN 1 ELSE 0 END) AS worthy_total
           FROM picks'''
    ) or {}


def dashboard_kpi():
    return q1(
        '''SELECT SUM(CASE WHEN date(pick_date) >= date('now','weekday 1','-7 days') THEN 1 ELSE 0 END) AS week_new,
                  SUM(CASE WHEN date(pick_date) >= date('now','-6 day') THEN 1 ELSE 0 END) AS last7_new,
                  SUM(CASE WHEN date(pick_date) >= date('now','-29 day') THEN 1 ELSE 0 END) AS last30_new,
                  ROUND(100.0 * SUM(CASE WHEN COALESCE(NULLIF(review_status,''),'未复盘')='值得复讲' THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0), 1) AS worthy_rate,
                  ROUND(AVG(COALESCE(inquiry_count,0)), 1) AS avg_inquiry
           FROM picks WHERE COALESCE(archived,0)=0'''
    ) or {}


def dashboard_channels():
    return q("SELECT COALESCE(NULLIF(source_channel,''),'system') AS name, COUNT(*) AS cnt FROM picks WHERE COALESCE(archived,0)=0 GROUP BY name ORDER BY cnt DESC")


def dashboard_tags():
    return q("SELECT COALESCE(NULLIF(reason_tag,''),'未标注') AS name, COUNT(*) AS cnt FROM picks WHERE COALESCE(archived,0)=0 GROUP BY name ORDER BY cnt DESC")


def dashboard_review_status():
    return q("SELECT COALESCE(NULLIF(review_status,''),'未复盘') AS name, COUNT(*) AS cnt FROM picks WHERE COALESCE(archived,0)=0 GROUP BY name ORDER BY cnt DESC")


def dashboard_grades():
    return q("SELECT COALESCE(NULLIF(result_grade,''),'待定') AS name, COUNT(*) AS cnt FROM picks WHERE COALESCE(archived,0)=0 GROUP BY name ORDER BY cnt DESC")


def dashboard_deals():
    return q("SELECT COALESCE(NULLIF(deal_status,''),'未成交') AS name, COUNT(*) AS cnt FROM picks WHERE COALESCE(archived,0)=0 GROUP BY name ORDER BY cnt DESC")


def dashboard_trend_30d():
    return q("SELECT pick_date AS name, COUNT(*) AS cnt FROM picks WHERE COALESCE(archived,0)=0 AND date(pick_date) >= date('now','-29 day') GROUP BY pick_date ORDER BY pick_date ASC")


def dashboard_worthy_trend_30d():
    return q("SELECT pick_date AS name, SUM(CASE WHEN COALESCE(NULLIF(review_status,''),'未复盘')='值得复讲' THEN 1 ELSE 0 END) AS cnt FROM picks WHERE COALESCE(archived,0)=0 AND date(pick_date) >= date('now','-29 day') GROUP BY pick_date ORDER BY pick_date ASC")


def dashboard_deal_trend_30d():
    return q("SELECT pick_date AS name, SUM(CASE WHEN COALESCE(NULLIF(deal_status,''),'未成交')='已成交' THEN 1 ELSE 0 END) AS cnt FROM picks WHERE COALESCE(archived,0)=0 AND date(pick_date) >= date('now','-29 day') GROUP BY pick_date ORDER BY pick_date ASC")


def recent_operation_logs(limit=15):
    return q(
        "SELECT action, target_ids, detail, created_at FROM operation_logs ORDER BY id DESC LIMIT ?",
        (int(limit),),
    )
