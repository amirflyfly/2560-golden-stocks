"""Operation logs repository."""

from backend.repositories.db import q, execute


def insert_log(action, target_ids_csv='', detail='', user_id=None, username='', ip='', user_agent=''):
    username = username or ''
    ip = ip or ''
    user_agent = user_agent or ''
    return execute(
        'INSERT INTO operation_logs (action, target_ids, detail, user_id, username, ip, user_agent) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (action, target_ids_csv, (detail or '')[:1000], user_id, username[:64], ip[:64], user_agent[:200]),
    )


def recent_logs(limit=15):
    return q(
        'SELECT created_at, username, ip, action, target_ids, detail FROM operation_logs ORDER BY id DESC LIMIT ?',
        (int(limit),),
    )
