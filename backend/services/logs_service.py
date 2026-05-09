"""Operation logs service."""

from backend.repositories import logs_repo


def log_action(action, target_ids=None, detail='', actor=None, ip='', user_agent=''):
    actor = actor or {}
    user_id = actor.get('user_id') or actor.get('id') or actor.get('user_id')
    username = actor.get('username') or ''
    target_ids = target_ids or []
    csv_ids = ','.join(str(i) for i in target_ids)
    return logs_repo.insert_log(action, csv_ids, detail, user_id=user_id, username=username, ip=ip, user_agent=user_agent)


def recent_logs(limit=15):
    return logs_repo.recent_logs(limit=limit)
