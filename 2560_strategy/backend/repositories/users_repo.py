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


def list_users():
    return q('SELECT id, username, role, is_active, created_at FROM users ORDER BY id')


def update_password(user_id: int, password_hash: str):
    return execute('UPDATE users SET password_hash=? WHERE id=?', (password_hash, int(user_id)))


def update_user_points(user_id: int, points: int):
    """Update user points."""
    # First get current points
    user = get_user_by_id(user_id)
    current_points = user.get('points', 0) if user else 0
    new_points = current_points + points
    return execute('UPDATE users SET points=? WHERE id=?', (new_points, int(user_id)))


def get_user_last_checkin(user_id: int):
    """Get user last checkin date."""
    user = get_user_by_id(user_id)
    return user.get('last_checkin') if user else None


def update_user_last_checkin(user_id: int, checkin_date: str):
    """Update user last checkin date."""
    return execute('UPDATE users SET last_checkin=? WHERE id=?', (checkin_date, int(user_id)))
