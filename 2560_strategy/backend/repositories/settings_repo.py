"""UI settings persistence.

Step 2 of the web_panel.py split: move ui_settings + saved_filters SQL here.
"""

from backend.repositories.db import q, q1, execute


def get_saved_filters(limit=12):
    return q(
        'SELECT id, name, query_string, created_at '
        'FROM saved_filters ORDER BY id DESC LIMIT ?',
        (int(limit),),
    )


def delete_saved_filter(filter_id):
    return execute('DELETE FROM saved_filters WHERE id=?', (filter_id,))


def rename_saved_filter(filter_id, new_name):
    return execute('UPDATE saved_filters SET name=? WHERE id=?', (new_name, filter_id))


def create_saved_filter(name, query_string):
    return execute(
        'INSERT INTO saved_filters (name, query_string) VALUES (?, ?)',
        (name, query_string),
    )


def get_dashboard_order(default='kpi,trend,filters,actions,records,logs'):
    row = q1("SELECT setting_value FROM ui_settings WHERE setting_key='dashboard_order'")
    if not row or not row.get('setting_value'):
        return default
    return row['setting_value']


def set_dashboard_order(value):
    return execute(
        "INSERT INTO ui_settings (setting_key, setting_value, updated_at) "
        "VALUES ('dashboard_order', ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT(setting_key) DO UPDATE SET "
        "setting_value=excluded.setting_value, updated_at=CURRENT_TIMESTAMP",
        (value,),
    )
