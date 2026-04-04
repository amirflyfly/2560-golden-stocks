"""Strategy repository for multi-strategy support.

Manages the strategies master data table.
"""

from backend.repositories.db import q, q1, execute


def list_strategies(active_only=True):
    """List all strategies, optionally filtering by active status."""
    sql = "SELECT * FROM strategies"
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY sort_order ASC, id ASC"
    return q(sql)


def get_strategy_by_id(sid):
    """Get a single strategy by ID."""
    return q1("SELECT * FROM strategies WHERE id=?", (sid,))


def get_strategy_by_code(code):
    """Get a single strategy by code."""
    return q1("SELECT * FROM strategies WHERE code=?", (code,))


def create_strategy(code, name, category='', description='', sort_order=0):
    """Create a new strategy."""
    return execute(
        """INSERT INTO strategies (code, name, category, description, sort_order)
           VALUES (?, ?, ?, ?, ?)""",
        (code, name, category, description, sort_order)
    )


def update_strategy(sid, code=None, name=None, category=None, description=None, is_active=None, sort_order=None):
    """Update a strategy. Only updates provided fields."""
    strategy = get_strategy_by_id(sid)
    if not strategy:
        return 0
    
    fields = []
    args = []
    
    if code is not None:
        fields.append("code=?")
        args.append(code)
    if name is not None:
        fields.append("name=?")
        args.append(name)
    if category is not None:
        fields.append("category=?")
        args.append(category)
    if description is not None:
        fields.append("description=?")
        args.append(description)
    if is_active is not None:
        fields.append("is_active=?")
        args.append(1 if is_active else 0)
    if sort_order is not None:
        fields.append("sort_order=?")
        args.append(sort_order)
    
    if not fields:
        return 0
    
    args.append(sid)
    return execute(
        f"UPDATE strategies SET {', '.join(fields)}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        args
    )


def delete_strategy(sid):
    """Delete a strategy (soft delete by deactivating)."""
    return update_strategy(sid, is_active=False)


def toggle_strategy_active(sid):
    """Toggle strategy active status."""
    strategy = get_strategy_by_id(sid)
    if not strategy:
        return 0
    new_status = 0 if strategy.get('is_active') else 1
    return update_strategy(sid, is_active=new_status)


def get_strategy_names_for_dropdown():
    """Get strategy names for dropdown, returns list of {code, name}."""
    strategies = list_strategies(active_only=True)
    return [{'code': s['code'], 'name': s['name']} for s in strategies]


def get_strategy_daily_summary(target_date):
    """Get daily summary for all strategies on a specific date.
    
    Returns all strategies with their pick counts (including 0).
    """
    # Get all active strategies
    strategies = list_strategies(active_only=True)
    
    # Get actual picks for the date
    picks_data = q(
        """SELECT COALESCE(NULLIF(p.strategy_name,''),'2560') as strategy_name,
                  COUNT(*) as total,
                  SUM(CASE WHEN COALESCE(NULLIF(p.review_status,''),'未复盘')='值得复讲' THEN 1 ELSE 0 END) as worthy_total,
                  SUM(CASE WHEN COALESCE(NULLIF(p.deal_status,''),'未成交')='已成交' THEN 1 ELSE 0 END) as deal_total
           FROM picks p
           WHERE COALESCE(p.archived,0)=0 AND p.pick_date=?
           GROUP BY strategy_name""",
        (target_date,)
    )
    
    # Create lookup
    picks_lookup = {p['strategy_name']: p for p in picks_data}
    
    # Merge with all strategies
    result = []
    for s in strategies:
        code = s['code']
        pick_info = picks_lookup.get(code, {'total': 0, 'worthy_total': 0, 'deal_total': 0})
        result.append({
            'strategy_code': code,
            'strategy_name': s['name'],
            'category': s['category'],
            'total': pick_info['total'],
            'worthy_total': pick_info['worthy_total'],
            'deal_total': pick_info['deal_total'],
            'has_picks': pick_info['total'] > 0
        })
    
    return result
