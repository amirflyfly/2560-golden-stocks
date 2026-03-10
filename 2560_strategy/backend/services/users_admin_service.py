"""User admin service."""

from backend.repositories import users_repo
from backend.services.password_service import hash_password


def create_user(username: str, password: str, role: str = 'editor'):
    username = (username or '').strip()
    if not username:
        return False, '用户名不能为空'
    if not password:
        return False, '密码不能为空'
    role = (role or 'editor').strip() or 'editor'
    if role not in ('admin', 'editor', 'viewer'):
        role = 'editor'
    try:
        users_repo.create_user(username, hash_password(password), role=role)
        return True, f'已创建用户：{username}'
    except Exception as e:
        return False, f'创建失败（可能用户名重复）：{e}'


def toggle_user_active(user_id: int, is_active: bool):
    try:
        users_repo.set_user_active(int(user_id), bool(int(is_active)))
        return True, '已更新用户状态'
    except Exception as e:
        return False, f'更新失败：{e}'


def reset_password(user_id: int, new_password: str):
    if not new_password:
        return False, '新密码不能为空'
    try:
        # update directly
        from backend.repositories.db import execute
        execute('UPDATE users SET password_hash=? WHERE id=?', (hash_password(new_password), int(user_id)))
        return True, '密码已重置'
    except Exception as e:
        return False, f'重置失败：{e}'
