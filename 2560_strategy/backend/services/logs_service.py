"""Operation logs service."""

from backend.repositories import logs_repo


def log_action(action, target_ids=None, detail=''):
    target_ids = target_ids or []
    csv_ids = ','.join(str(i) for i in target_ids)
    return logs_repo.insert_log(action, csv_ids, detail)


def recent_logs(limit=15):
    return logs_repo.recent_logs(limit=limit)
