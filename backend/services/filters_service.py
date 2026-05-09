"""Filters-related business logic.

Step 2 of the split: keep thin helpers around saved filters / dashboard order.
(For now this mainly wraps repository calls; later we can add validation, etc.)
"""

from backend.repositories import settings_repo


def get_saved_filters(limit=12):
    return settings_repo.get_saved_filters(limit=limit)


def save_current_filter(name, query_string):
    name = (name or '').strip()
    query_string = (query_string or '').strip()
    if not name or not query_string:
        return 0
    return settings_repo.create_saved_filter(name, query_string)


def get_dashboard_order():
    return settings_repo.get_dashboard_order()


def set_dashboard_order(value):
    value = (value or '').strip()
    if not value:
        return 0
    return settings_repo.set_dashboard_order(value)


def delete_saved_filter(filter_id):
    return settings_repo.delete_saved_filter(filter_id)


def rename_saved_filter(filter_id, new_name):
    new_name = (new_name or '').strip()
    if not new_name:
        return 0
    return settings_repo.rename_saved_filter(filter_id, new_name)
