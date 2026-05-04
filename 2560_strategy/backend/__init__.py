import sys
sys.path.insert(0, '.')
try:
    import werkzeug_patch
except ImportError:
    pass

from flask import Flask
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / 'templates'
STATIC_DIR = BASE_DIR / 'static'
DIST_DIR = BASE_DIR / 'dist'


def create_app(config=None):
    app = Flask(
        __name__,
        template_folder=str(TEMPLATE_DIR),
        static_folder=str(STATIC_DIR),
    )
    
    app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
    app.config['SESSION_COOKIE_NAME'] = 'promo_panel_auth'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['PERMANENT_SESSION_LIFETIME'] = 86400
    
    # 添加 Content Security Policy 头，允许 unsafe-eval 和 unsafe-inline 以支持 kline-charts-react 库和内联事件处理程序
    @app.after_request
    def add_csp_header(response):
        response.headers['Content-Security-Policy'] = "script-src 'self' 'unsafe-eval' 'unsafe-inline'"
        return response
    
    if config:
        app.config.update(config)
    
    from backend.repositories.db import ensure_schema
    ensure_schema()
    
    from backend.services.multiuser_auth_service import ensure_default_admin
    ensure_default_admin('admin', 'admin123')
    
    # Import strategies to ensure they are registered
    from backend.strategies import strategy_2560
    from backend.strategies import strategy_first_limit_up
    
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
    
    return app
