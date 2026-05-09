import json
import logging
import os
import secrets
import sys
from ipaddress import ip_address
from logging.handlers import RotatingFileHandler
from urllib.parse import urlparse

sys.path.insert(0, '.')
try:
    import werkzeug_patch
except ImportError:
    pass

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / 'templates'
STATIC_DIR = BASE_DIR / 'static'
DIST_DIR = BASE_DIR / 'dist'
STATE_CHANGING_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
LOG_DIR = BASE_DIR / 'logs'


class JsonLogFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            'time': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings):
    level = getattr(logging, settings.log_level, logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not root_logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
        root_logger.addHandler(console_handler)

    log_path = Path(os.getenv('APP_LOG_FILE', LOG_DIR / 'app.log'))
    if not any(isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == log_path for handler in root_logger.handlers):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=int(os.getenv('APP_LOG_MAX_BYTES', '1048576')),
            backupCount=int(os.getenv('APP_LOG_BACKUP_COUNT', '5')),
            encoding='utf-8',
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(JsonLogFormatter())
        root_logger.addHandler(file_handler)


def _normalize_origin(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _is_same_origin(candidate: str | None, host_url: str) -> bool:
    candidate_origin = _normalize_origin(candidate)
    host_origin = _normalize_origin(host_url)
    return bool(candidate_origin and host_origin and candidate_origin == host_origin)


def _is_loopback_origin(value: str | None) -> bool:
    parsed = urlparse(value or '')
    host = parsed.hostname
    if not host:
        return False
    if host.lower() == 'localhost':
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _is_trusted_write_origin(candidate: str | None, host_url: str, settings) -> bool:
    normalized = _normalize_origin(candidate)
    if not normalized:
        return False
    if _is_same_origin(candidate, host_url):
        return True
    if normalized in settings.cors_allowed_origins:
        return True
    if settings.environment.strip().lower() not in {'prod', 'production'}:
        return _is_loopback_origin(candidate) and _is_loopback_origin(host_url)
    return False


def _should_initialize_sqlite_schema(settings) -> bool:
    if settings.environment.strip().lower() in {'prod', 'production'}:
        return False
    if os.getenv('INIT_SQLITE_SCHEMA', '').strip().lower() in {'1', 'true', 'yes'}:
        return True
    return True


def create_app(config=None):
    from flask import Flask, request, session

    app = Flask(
        __name__,
        template_folder=str(TEMPLATE_DIR),
        static_folder=str(STATIC_DIR),
    )
    
    from backend.core.config import get_settings
    settings = get_settings()

    app.config['SECRET_KEY'] = settings.secret_key
    app.config['SESSION_COOKIE_NAME'] = 'promo_panel_auth'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
    session_cookie_secure = os.getenv('SESSION_COOKIE_SECURE', '').strip().lower()
    app.config['SESSION_COOKIE_SECURE'] = (
        session_cookie_secure in {'1', 'true', 'yes', 'on'}
        if session_cookie_secure
        else settings.environment.lower() in {'prod', 'production'}
    )
    app.config['PERMANENT_SESSION_LIFETIME'] = 86400
    app.config['CSRF_COOKIE_NAME'] = 'promo_panel_csrf'

    configure_logging(settings)
    app.logger.setLevel(getattr(logging, settings.log_level, logging.INFO))

    def ensure_csrf_token() -> str:
        token = session.get('_csrf_token')
        if not token:
            token = secrets.token_urlsafe(32)
            session['_csrf_token'] = token
        return token

    @app.before_request
    def enforce_security_baseline():
        ensure_csrf_token()

        if request.method == 'OPTIONS' and request.path.startswith(settings.api_prefix):
            return ('', 204)

        if request.method not in STATE_CHANGING_METHODS:
            return None

        if request.endpoint in {'main.login'}:
            return None

        if not session.get('auth_token'):
            return None

        origin = request.headers.get('Origin')
        referer = request.headers.get('Referer')
        sec_fetch_site = (request.headers.get('Sec-Fetch-Site') or '').strip().lower()
        if sec_fetch_site == 'cross-site':
            return _reject_request(request.path)
        if origin and not _is_trusted_write_origin(origin, request.host_url, settings):
            return _reject_request(request.path)
        if not origin and referer and not _is_trusted_write_origin(referer, request.host_url, settings):
            return _reject_request(request.path)

        csrf_token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
        if csrf_token != session.get('_csrf_token'):
            return _reject_request(request.path, message='csrf token invalid')
        return None

    def _reject_request(path: str, message: str = 'forbidden'):
        if path.startswith('/api/'):
            from backend.core.responses import error
            return error(message, code=403, status_code=403)
        return message, 403

    @app.after_request
    def add_security_headers(response):
        csp_parts = [
            "default-src 'self'",
            "base-uri 'self'",
            "object-src 'none'",
            "frame-ancestors 'none'",
            "form-action 'self'",
            "img-src 'self' data:",
            "style-src 'self' 'unsafe-inline'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
            "connect-src 'self'",
        ]
        response.headers['Content-Security-Policy'] = '; '.join(csp_parts)
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=(), browsing-topics=()'
        response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'

        origin = request.headers.get('Origin')
        if request.path.startswith(settings.api_prefix) and origin and origin in settings.cors_allowed_origins:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Tenant-ID, X-User-ID, X-CSRF-Token'
            response.headers['Vary'] = 'Origin'

        response.set_cookie(
            app.config['CSRF_COOKIE_NAME'],
            ensure_csrf_token(),
            httponly=False,
            secure=app.config['SESSION_COOKIE_SECURE'],
            samesite=app.config['SESSION_COOKIE_SAMESITE'],
            path='/',
        )
        return response
    
    if config:
        app.config.update(config)
    
    if _should_initialize_sqlite_schema(settings):
        from backend.repositories.db import ensure_schema
        ensure_schema()
    
    from backend.services.multiuser_auth_service import ensure_default_admin
    ensure_default_admin()
    
    # Import strategies to ensure they are registered. In lightweight test
    # environments optional market-data dependencies may be absent; legacy
    # strategy imports must not block app creation.
    try:
        from backend.strategies import strategy_2560
        from backend.strategies import strategy_first_limit_up
    except ModuleNotFoundError as exc:
        app.logger.warning("Skipping optional strategy registration: %s", exc)
    
    from backend.routes.main import bp as main_bp, get_current_language, get_dark_mode, get_sidebar_collapsed, get_current_user
    from backend.routes.api import bp as api_bp
    from backend.routes.admin import bp as admin_bp
    from backend.routes.strategies import bp as strategies_bp
    from backend.routes.strategy_management import strategy_management_bp
    from backend.routes.strategy_scan import bp as strategy_scan_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(strategies_bp)
    app.register_blueprint(strategy_management_bp)
    app.register_blueprint(strategy_scan_bp)

    from backend.api_v1.register import register_api_v1
    register_api_v1(app)
    
    # Translation dictionary
    translations = {
        'zh-CN': {
            '首页概览': '首页概览',
            '成交复盘': '成交复盘',
            '排行榜': '排行榜',
            '报表中心': '报表中心',
            '策略中心': '策略中心',
            '策略管理': '策略管理',
            '系统管理': '系统管理',
            '用户管理': '用户管理',
            '备份管理': '备份管理',
            '个人信息': '个人信息',
            '签到': '签到',
            '退出登录': '退出登录',
            '明亮模式': '明亮模式',
            '暗黑模式': '暗黑模式',
            '积分': '积分',
            '飞哥复盘': '飞哥复盘'
        },
        'en-US': {
            '首页概览': 'Dashboard',
            '成交复盘': 'Deal Review',
            '排行榜': 'Leaderboards',
            '报表中心': 'Reports',
            '策略中心': 'Strategy Center',
            '策略管理': 'Strategy Management',
            '系统管理': 'System Management',
            '用户管理': 'User Management',
            '备份管理': 'Backup Management',
            '个人信息': 'Profile',
            '签到': 'Checkin',
            '退出登录': 'Logout',
            '明亮模式': 'Light Mode',
            '暗黑模式': 'Dark Mode',
            '积分': 'Points',
            '飞哥复盘': 'Feige Review'
        }
    }
    
    # Context processor for templates
    @app.context_processor
    def inject_common_variables():
        current_lang = get_current_language()
        
        def translate(text):
            lang_translations = translations.get(current_lang, translations['zh-CN'])
            return lang_translations.get(text, text)
        
        return {
            'current_language': current_lang,
            'dark_mode': get_dark_mode(),
            'sidebar_collapsed': get_sidebar_collapsed(),
            'user': get_current_user(),
            'csrf_token': ensure_csrf_token(),
            'csrf_cookie_name': app.config['CSRF_COOKIE_NAME'],
            '_': translate
        }
    
    # 提供React应用的静态文件
    from flask import send_from_directory
    
    @app.route('/dist/<path:path>')
    def serve_dist(path):
        return send_from_directory(str(DIST_DIR), path)
    
    @app.route('/assets/<path:path>')
    def serve_assets(path):
        return send_from_directory(str(DIST_DIR / 'assets'), path)
    
    @app.route('/stock-chart')
    def serve_stock_chart():
        return send_from_directory(str(DIST_DIR), 'index.html')

    @app.route('/app')
    @app.route('/app/<path:path>')
    def serve_react_app(path: str = ''):
        return send_from_directory(str(DIST_DIR), 'index.html')
    
    return app
