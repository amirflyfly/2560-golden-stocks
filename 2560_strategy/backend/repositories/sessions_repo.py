"""Session repository."""

from backend.repositories.db import q1, execute


def create_session(session_token: str, user_id: int, expires_at_iso: str):
    return execute(
        'INSERT INTO sessions (session_token, user_id, expires_at, last_seen_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)',
        (session_token, int(user_id), expires_at_iso),
    )


def get_session(session_token: str):
    return q1(
        '''SELECT s.session_token, s.user_id, s.expires_at, s.last_seen_at, u.username, u.role, u.is_active
           FROM sessions s JOIN users u ON u.id = s.user_id
           WHERE s.session_token=?''',
        (session_token,),
    )


def touch_session(session_token: str):
    return execute('UPDATE sessions SET last_seen_at=CURRENT_TIMESTAMP WHERE session_token=?', (session_token,))


def delete_session(session_token: str):
    return execute('DELETE FROM sessions WHERE session_token=?', (session_token,))


def delete_expired_sessions():
    return execute("DELETE FROM sessions WHERE expires_at < datetime('now')")
