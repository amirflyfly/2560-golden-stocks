import os
from functools import wraps

from flask import Blueprint, request, jsonify

bp = Blueprint('strategy_scan', __name__, url_prefix='/api/scan')


@bp.after_request
def add_legacy_scan_headers(response):
    response.headers['X-Legacy-API'] = 'deprecated'
    response.headers['Link'] = '</api/v1>; rel="successor-version"'
    return response


@bp.before_request
def freeze_production_legacy_scan_writes_before_auth():
    if _is_production() and request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        return _legacy_scan_frozen_response()
    return None


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from backend.services.multiuser_auth_service import get_session
        from flask import session
        token = session.get('auth_token')
        sess = get_session(token)
        if not sess or sess.get('role') != 'admin':
            return jsonify({'error': '需要管理员权限'}), 403
        return f(*args, **kwargs)
    return decorated_function


def _is_production() -> bool:
    return (os.getenv('APP_ENV') or '').strip().lower() in {'prod', 'production'}


def _legacy_scan_frozen_response():
    response = jsonify({
        'success': False,
        'message': 'legacy scan write endpoint is frozen; use the React v1 workflow',
        'successor': '/app?page=scans',
    })
    response.status_code = 410
    return response


def freeze_legacy_scan_write_in_production(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if _is_production():
            return _legacy_scan_frozen_response()
        return f(*args, **kwargs)
    return wrapped


@bp.route('/all', methods=['POST'])
@admin_required
@freeze_legacy_scan_write_in_production
def scan_all():
    """Run all active strategies and import results."""
    from backend.services import multi_strategy_service
    
    data = request.get_json() or {}
    date = data.get('date')
    
    results = multi_strategy_service.run_all_strategies(date)
    return jsonify(results)


@bp.route('/<strategy_code>', methods=['POST'])
@admin_required
@freeze_legacy_scan_write_in_production
def scan_single(strategy_code):
    """Run a single strategy and import results."""
    from backend.services import multi_strategy_service
    
    data = request.get_json() or {}
    date = data.get('date')
    
    result = multi_strategy_service.run_single_strategy(strategy_code, date)
    return jsonify(result)


@bp.route('/status', methods=['GET'])
def scan_status():
    """Get strategy scan status for a date."""
    from backend.services import multi_strategy_service
    
    date = request.args.get('date')
    status = multi_strategy_service.get_strategy_status(date)
    return jsonify(status)
