"""Leaderboards logic.

Step 4 of the web_panel.py split: move leaderboard queries here.
"""

from backend.repositories.db import q


def leaderboards(range_key='30d', metric='default'):
    range_sql_map = {
        '7d': "WHERE date(pick_date) >= date('now','-6 day')",
        '30d': "WHERE date(pick_date) >= date('now','-29 day')",
        '90d': "WHERE date(pick_date) >= date('now','-89 day')",
        'all': ''
    }
    range_sql = range_sql_map.get(range_key, range_sql_map['30d'])
    range_where = (range_sql + ' AND ') if range_sql else 'WHERE '

    channel_rank = q(
        f"SELECT COALESCE(NULLIF(source_channel,''),'system') AS name, COUNT(*) AS cnt "
        f"FROM picks {range_sql} GROUP BY name ORDER BY cnt DESC LIMIT 10"
    )
    worthy_rank = q(
        f"SELECT COALESCE(NULLIF(reason_tag,''),'未标注') AS name, COUNT(*) AS cnt "
        f"FROM picks {range_where}COALESCE(NULLIF(review_status,''),'未复盘')='值得复讲' "
        f"GROUP BY name ORDER BY cnt DESC LIMIT 10"
    )
    deal_rank = q(
        f"SELECT COALESCE(NULLIF(source_channel,''),'system') AS name, COUNT(*) AS cnt "
        f"FROM picks {range_where}COALESCE(NULLIF(deal_status,''),'未成交')='已成交' "
        f"GROUP BY name ORDER BY cnt DESC LIMIT 10"
    )
    inquiry_rank = q(
        f"SELECT COALESCE(NULLIF(reason_tag,''),'未标注') AS name, "
        f"ROUND(AVG(COALESCE(inquiry_count,0)),1) AS cnt "
        f"FROM picks {range_sql} GROUP BY name ORDER BY cnt DESC LIMIT 10"
    )
    spread_rank = q(
        f"SELECT COALESCE(NULLIF(source_channel,''),'system') AS name, COUNT(*) AS cnt "
        f"FROM picks {range_where}COALESCE(NULLIF(secondary_spread,''),'否')='是' "
        f"GROUP BY name ORDER BY cnt DESC LIMIT 10"
    )

    right_title = '二次传播渠道 Top10' if metric == 'spread' else '标签平均咨询数 Top10'
    right_rows = spread_rank if metric == 'spread' else inquiry_rank
    right_color = '#7c3aed' if metric == 'spread' else '#ca8a04'

    return {
        'range_key': range_key,
        'metric': metric,
        'channel_rank': channel_rank,
        'worthy_rank': worthy_rank,
        'deal_rank': deal_rank,
        'inquiry_rank': inquiry_rank,
        'spread_rank': spread_rank,
        'right_title': right_title,
        'right_rows': right_rows,
        'right_color': right_color,
    }
