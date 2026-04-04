"""Strategy service layer.

Business logic for strategy management.
"""

from backend.repositories import strategy_repo


def get_all_strategies(active_only=True):
    """Get all strategies."""
    return strategy_repo.list_strategies(active_only=active_only)


def get_strategy_dropdown_options():
    """Get strategy options for dropdown menus."""
    return strategy_repo.get_strategy_names_for_dropdown()


def get_daily_strategy_summary(target_date):
    """Get daily summary showing all strategies including those with 0 picks."""
    return strategy_repo.get_strategy_daily_summary(target_date)


def create_strategy(code, name, category='', description=''):
    """Create a new strategy."""
    # Get next sort order
    strategies = get_all_strategies(active_only=False)
    sort_order = len(strategies)
    return strategy_repo.create_strategy(code, name, category, description, sort_order)


def update_strategy(sid, **kwargs):
    """Update a strategy."""
    return strategy_repo.update_strategy(sid, **kwargs)


def toggle_strategy(sid):
    """Toggle strategy active status."""
    return strategy_repo.toggle_strategy_active(sid)


def delete_strategy(sid):
    """Soft delete a strategy."""
    return strategy_repo.delete_strategy(sid)


def validate_strategy_code(code, exclude_id=None):
    """Validate if strategy code is available."""
    existing = strategy_repo.get_strategy_by_code(code)
    if existing:
        if exclude_id and existing['id'] == exclude_id:
            return True
        return False
    return True
