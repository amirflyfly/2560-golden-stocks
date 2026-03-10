"""Operation logs repository."""

from backend.repositories.db import q, execute


def insert_log(action, target_ids_csv='', detail=''):
    return execute(
        'INSERT INTO operation_logs (action, target_ids, detail) VALUES (?, ?, ?)',
        (action, target_ids_csv, (detail or '')[:1000]),
    )


def recent_logs(limit=15):
    return q(
        'SELECT action, target_ids, detail, created_at FROM operation_logs ORDER BY id DESC LIMIT ?',
        (int(limit),),
    )
