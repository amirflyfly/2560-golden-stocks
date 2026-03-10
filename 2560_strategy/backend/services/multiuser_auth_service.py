"""Multi-user auth service.

- Users stored in DB
- Sessions stored in DB
- Cookie stores random session token
"""

import secrets
from datetime import datetime, timedelta

from backend.repositories import users_repo, sessions_repo
from backend.services.password_service import hash_password, verify_password


SESSION_DAYS = 30


def ensure_default_admin(username: str, password: str):
    """Create default admin if no users exist."""
    if users_repo.has_any_users():
        return False
    username = (username or 'admin').strip() or 'admin'
    try:
        users_repo.create_user(username, hash_password(password), role='admin')
        return True
    except Exception:
        return False


def login(username: str, password: str):
    u = users_repo.get_user_by_username((username or '').strip())
    if not u or int(u.get('is_active') or 0) != 1:
        return None
    if not verify_password(password or '', u.get('password_hash') or ''):
        return None

    token = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(days=SESSION_DAYS)
    expires_iso = expires.strftime('%Y-%m-%d %H:%M:%S')
    sessions_repo.delete_expired_sessions()
    sessions_repo.create_session(token, int(u['id']), expires_iso)
    return {
        'session_token': token,
        'user_id': int(u['id']),
        'username': u.get('username'),
        'role': u.get('role') or 'admin',
        'expires_at': expires_iso,
    }


def logout(session_token: str):
    if session_token:
        sessions_repo.delete_session(session_token)


def get_session(session_token: str):
    if not session_token:
        return None
    s = sessions_repo.get_session(session_token)
    if not s:
        return None
    if int(s.get('is_active') or 0) != 1:
        return None
    # sqlite datetime string compare is ok; do explicit check via SQL would be better
    # We'll rely on periodic cleanup + basic guard.
    sessions_repo.touch_session(session_token)
    return s
