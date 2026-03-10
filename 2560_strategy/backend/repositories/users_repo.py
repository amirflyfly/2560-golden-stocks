"""User repository."""

from backend.repositories.db import q, q1, execute


def get_user_by_username(username: str):
    return q1('SELECT * FROM users WHERE username=?', (username,))


def get_user_by_id(user_id: int):
    return q1('SELECT * FROM users WHERE id=?', (int(user_id),))


def create_user(username: str, password_hash: str, role: str = 'admin'):
    return execute(
        'INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
        (username, password_hash, role),
    )


def set_user_active(user_id: int, is_active: bool):
    return execute('UPDATE users SET is_active=? WHERE id=?', (1 if is_active else 0, int(user_id)))



def has_any_users():
    return q1('SELECT id FROM users LIMIT 1') is not None
