"""Strategy management routes."""

import os
from functools import wraps

from flask import Blueprint, request, jsonify, redirect, url_for, session
from backend.services.strategy_pool_service import (
    add_stock_to_pool, remove_stock_from_pool,
    run_strategy_for_date, add_scan_result_to_pool,
    run_backtest
)

strategy_management_bp = Blueprint('strategy_management', __name__)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from backend.services.multiuser_auth_service import get_session
        token = session.get('auth_token')
        if not token or not get_session(token):
            if request.path.startswith('/api/'):
                return jsonify({'error': '未登录'}), 401
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function


@strategy_management_bp.after_request
def add_legacy_strategy_management_headers(response):
    response.headers['X-Legacy-API'] = 'deprecated'
    response.headers['Link'] = '</api/v1>; rel="successor-version"'
    return response


@strategy_management_bp.before_request
def freeze_production_legacy_strategy_writes_before_auth():
    if not _is_production() or request.method in {'GET', 'HEAD', 'OPTIONS'}:
        return None
    successor = '/app?page=scans' if request.path.startswith('/strategies/run') else '/app?page=strategies'
    if request.path.startswith('/api/strategy/'):
        successor = '/app?page=picks'
    return _legacy_strategy_frozen_response(successor)


def _react_redirect(page, **params):
    query = "&".join([f"{key}={value}" for key, value in {"page": page, **params}.items() if value])
    return redirect(f"/app?{query}")


def _is_production() -> bool:
    return (os.getenv('APP_ENV') or '').strip().lower() in {'prod', 'production'}


def _legacy_strategy_frozen_response(successor='/app?page=strategies'):
    response = jsonify({
        'success': False,
        'message': 'legacy strategy write endpoint is frozen; use the React v1 workflow',
        'successor': successor,
    })
    response.status_code = 410
    return response


def freeze_legacy_strategy_write_in_production(successor='/app?page=strategies'):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if request.method not in {'GET', 'HEAD', 'OPTIONS'} and _is_production():
                return _legacy_strategy_frozen_response(successor)
            return f(*args, **kwargs)
        return wrapped
    return decorator


@strategy_management_bp.route('/strategies/pool/<strategy_code>')
@login_required
def strategy_pool(strategy_code):
    """Strategy pool page."""
    return _react_redirect("picks", strategy_code=strategy_code)


@strategy_management_bp.route('/strategies/run/<strategy_code>', methods=['GET', 'POST'])
@login_required
@freeze_legacy_strategy_write_in_production('/app?page=scans')
def strategy_run(strategy_code):
    """Strategy manual run page."""
    if request.method == 'GET':
        return _react_redirect("scans", strategy_code=strategy_code)

    if request.method == 'POST':
        target_date = request.form.get('target_date')
        if not target_date:
            return jsonify({'success': False, 'message': '请选择日期'})
        
        result = run_strategy_for_date(strategy_code, target_date)
        return jsonify(result)


@strategy_management_bp.route('/strategies/backtest/<strategy_code>', methods=['GET', 'POST'])
@login_required
@freeze_legacy_strategy_write_in_production()
def strategy_backtest(strategy_code):
    """Strategy backtest page."""
    if request.method == 'GET':
        return _react_redirect("strategies", strategy_code=strategy_code)

    if request.method == 'POST':
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        if not start_date or not end_date:
            return jsonify({'success': False, 'message': '请选择起止日期'})
        
        result = run_backtest(strategy_code, start_date, end_date)
        return jsonify(result)


@strategy_management_bp.route('/api/strategy/pool/add', methods=['POST'])
@login_required
@freeze_legacy_strategy_write_in_production('/app?page=picks')
def api_add_to_pool():
    """API: Add stock to strategy pool."""
    data = request.json
    if not data:
        return jsonify({'success': False, 'message': '无效数据'})
    
    strategy_code = data.get('strategy_code')
    code = data.get('code')
    name = data.get('name')
    add_price = data.get('add_price')
    reason = data.get('reason', '')
    
    if not all([strategy_code, code, name, add_price]):
        return jsonify({'success': False, 'message': '缺少必要参数'})
    
    result = add_stock_to_pool(strategy_code, code, name, add_price, reason)
    return jsonify(result)


@strategy_management_bp.route('/api/strategy/pool/remove', methods=['POST'])
@login_required
@freeze_legacy_strategy_write_in_production('/app?page=picks')
def api_remove_from_pool():
    """API: Remove stock from strategy pool."""
    data = request.json
    if not data:
        return jsonify({'success': False, 'message': '无效数据'})
    
    strategy_code = data.get('strategy_code')
    code = data.get('code')
    
    if not all([strategy_code, code]):
        return jsonify({'success': False, 'message': '缺少必要参数'})
    
    result = remove_stock_from_pool(strategy_code, code)
    return jsonify(result)


@strategy_management_bp.route('/api/strategy/scan/add-to-pool', methods=['POST'])
@login_required
@freeze_legacy_strategy_write_in_production('/app?page=picks')
def api_add_scan_to_pool():
    """API: Add scan results to strategy pool."""
    data = request.json
    if not data:
        return jsonify({'success': False, 'message': '无效数据'})
    
    strategy_code = data.get('strategy_code')
    scan_results = data.get('scan_results', [])
    
    if not strategy_code or not scan_results:
        return jsonify({'success': False, 'message': '缺少必要参数'})
    
    result = add_scan_result_to_pool(strategy_code, scan_results)
    return jsonify(result)
