from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault('APP_ENV', 'development')
os.environ.setdefault('APP_DEBUG', '0')
os.environ.setdefault('MARKET_DATA_PROVIDER', 'mootdx')
os.environ.setdefault('MARKET_DATA_FALLBACKS', 'akshare')
os.environ.setdefault('SECRET_KEY', 'e2e-dev-secret-key-please-do-not-use-in-prod')
os.environ.setdefault('SESSION_COOKIE_SAMESITE', 'Lax')
os.environ['CACHE_BACKEND'] = os.getenv('E2E_CACHE_BACKEND', 'memory')
os.environ['TASK_QUEUE_BACKEND'] = os.getenv('E2E_TASK_QUEUE_BACKEND', 'memory')
os.environ['TASK_EXECUTION_MODE'] = os.getenv('E2E_TASK_EXECUTION_MODE', 'threadpool')
for name in (
    'PICKS_REPOSITORY_BACKEND',
    'AUTH_REPOSITORY_BACKEND',
    'AUDIT_REPOSITORY_BACKEND',
    'SETTINGS_REPOSITORY_BACKEND',
    'LOGS_REPOSITORY_BACKEND',
    'STRATEGY_POOL_REPOSITORY_BACKEND',
    'STRATEGY_REPOSITORY_BACKEND',
    'TRADING_REPOSITORY_BACKEND',
):
    os.environ[name] = os.getenv(f'E2E_{name}', 'sqlite')

BASE_DIR = Path(__file__).resolve().parents[1]
E2E_DATA_DIR = BASE_DIR / 'data' / 'e2e'
E2E_DB_PATH = E2E_DATA_DIR / 'picks-e2e.db'
E2E_LOG_PATH = E2E_DATA_DIR / 'app.log'

os.environ.setdefault('APP_LOG_FILE', str(E2E_LOG_PATH))

import sys

sys.path.insert(0, str(BASE_DIR))

import backend as backend_package
import backend.repositories.db as db_module
from backend import create_app
from backend.repositories import users_repo
from backend.services.multiuser_auth_service import create_user

backend_package.DIST_DIR = Path(os.getenv('E2E_DIST_DIR', BASE_DIR / 'dist'))


def reset_database() -> None:
    E2E_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if E2E_DB_PATH.exists():
        E2E_DB_PATH.unlink()
    db_module.DB_PATH = E2E_DB_PATH


def ensure_user(username: str, password: str, role: str) -> int:
    existing = users_repo.get_user_by_username(username)
    if existing:
        return int(existing['id'])
    create_user(username, password, role)
    created = users_repo.get_user_by_username(username)
    return int(created['id'])


def seed_e2e_data() -> None:
    if not users_repo.get_tenant_by_code('tenant-two'):
        users_repo.create_tenant('tenant-two', '第二测试租户', plan='pro', status='active')
    if not users_repo.get_tenant_by_code('disabled-e2e'):
        users_repo.create_tenant('disabled-e2e', '停用测试租户', plan='default', status='disabled')

    tenant_two = users_repo.get_tenant_by_code('tenant-two')
    disabled_tenant = users_repo.get_tenant_by_code('disabled-e2e')

    admin = users_repo.get_user_by_username('admin')
    if admin:
        users_repo.bind_user_tenant(int(admin['id']), int(tenant_two['id']), 'admin', is_default=False)
        users_repo.bind_user_tenant(int(admin['id']), int(disabled_tenant['id']), 'admin', is_default=False)

    editor_id = ensure_user('e2e_editor', 'testpass', 'editor')
    viewer_id = ensure_user('e2e_viewer', 'testpass', 'viewer')
    unbound_id = ensure_user('e2e_unbound', 'testpass', 'viewer')

    users_repo.bind_user_tenant(editor_id, 1, 'editor', is_default=True)
    users_repo.bind_user_tenant(editor_id, int(tenant_two['id']), 'editor', is_default=False)
    users_repo.bind_user_tenant(viewer_id, 1, 'viewer', is_default=True)

    users_repo.unbind_user_tenant(unbound_id, int(tenant_two['id']))


def build_app():
    reset_database()
    app = create_app()
    seed_e2e_data()
    return app


app = build_app()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.getenv('PORT', '8765')), debug=False, use_reloader=False)
