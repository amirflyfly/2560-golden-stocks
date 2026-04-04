from flask import Blueprint, request, jsonify
from functools import wraps

bp = Blueprint('strategy_scan', __name__, url_prefix='/api/scan')


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


@bp.route('/all', methods=['POST'])
@admin_required
def scan_all():
    """Run all active strategies and import results."""
    from backend.services import multi_strategy_service
    
    data = request.get_json() or {}
    date = data.get('date')
    
    results = multi_strategy_service.run_all_strategies(date)
    return jsonify(results)


@bp.route('/<strategy_code>', methods=['POST'])
@admin_required
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
