"""Multi-user auth service.

- Users stored in DB
- Sessions stored in DB
- Cookie stores random session token
"""

import os
import secrets
from datetime import datetime, timedelta

from backend.repositories import users_repo, sessions_repo
from backend.services.password_service import hash_password, verify_password


DEFAULT_ADMIN_USERNAME = 'admin'
DEFAULT_ADMIN_PASSWORD = 'admin123'


SESSION_DAYS = 30


def ensure_default_admin(username: str | None = None, password: str | None = None):
    """Create the first admin user when bootstrapping an empty database.

    Production deployments must provide ADMIN_INIT_USERNAME and
    ADMIN_INIT_PASSWORD explicitly. Development keeps the historical local
    defaults for compatibility, but only when the caller does not provide
    weaker values.
    """
    if users_repo.has_any_users():
        return False

    environment = os.getenv('APP_ENV', 'development').strip().lower()
    flask_environment = os.getenv('FLASK_ENV', '').strip().lower()
    is_production = environment in {'prod', 'production'} or flask_environment in {'prod', 'production'}
    username = (os.getenv('ADMIN_INIT_USERNAME') or username or DEFAULT_ADMIN_USERNAME).strip() or DEFAULT_ADMIN_USERNAME
    password = os.getenv('ADMIN_INIT_PASSWORD') or password

    if is_production:
        if not password or password == DEFAULT_ADMIN_PASSWORD or len(password) < 12:
            raise RuntimeError('ADMIN_INIT_PASSWORD must be a strong value in production')
        if username == DEFAULT_ADMIN_USERNAME and not os.getenv('ADMIN_INIT_USERNAME'):
            raise RuntimeError('ADMIN_INIT_USERNAME must be explicitly set in production')
    elif not password:
        password = DEFAULT_ADMIN_PASSWORD

    try:
        users_repo.create_user(username, hash_password(password), role='admin')
        return True
    except Exception:
        if is_production:
            raise
        return False


def create_user(username: str, password: str, role: str = 'editor'):
    """Create a user with a plain-text password input for tests and admin flows."""
    username = (username or '').strip()
    if not username or not password or len(password) < 8:
        return None
    existing = users_repo.get_user_by_username(username)
    if existing:
        return existing.get('id')
    return users_repo.create_user(username, hash_password(password), role=role)


def set_user_active(user_id: int, is_active: bool):
    return users_repo.set_user_active(user_id, is_active)


def update_user_password(user_id: int, password: str):
    if not password:
        return 0
    return users_repo.update_password(user_id, hash_password(password))



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
        sessions_repo.delete_session(session_token)
        return None
    if int(s.get('is_active') or 0) != 1:
        sessions_repo.delete_session(session_token)
        return None
    sessions_repo.touch_session(session_token)
    return s
