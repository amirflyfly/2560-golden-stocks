from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from functools import wraps

bp = Blueprint('strategies', __name__, url_prefix='/strategies')


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from backend.services.multiuser_auth_service import get_session
        from flask import session
        token = session.get('auth_token')
        sess = get_session(token)
        if not sess or sess.get('role') != 'admin':
            flash('需要管理员权限', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def get_current_user():
    from backend.services.multiuser_auth_service import get_session
    from flask import session
    token = session.get('auth_token')
    if token:
        sess = get_session(token)
        if sess:
            return {
                'user_id': sess.get('user_id'),
                'username': sess.get('username'),
                'role': sess.get('role'),
            }
    return None


@bp.route('/')
@admin_required
def index():
    from backend.services import strategy_service
    strategies = strategy_service.get_all_strategies(active_only=False)
    return render_template('strategies/index.html', 
        strategies=strategies,
        user=get_current_user()
    )


@bp.route('/create', methods=['POST'])
@admin_required
def create():
    from backend.services import strategy_service
    
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    category = request.form.get('category', '').strip()
    description = request.form.get('description', '').strip()
    
    if not code or not name:
        flash('策略编码和名称不能为空', 'error')
        return redirect(url_for('strategies.index'))
    
    if not strategy_service.validate_strategy_code(code):
        flash('策略编码已存在', 'error')
        return redirect(url_for('strategies.index'))
    
    strategy_service.create_strategy(code, name, category, description)
    flash('策略创建成功', 'success')
    return redirect(url_for('strategies.index'))


@bp.route('/<int:sid>/update', methods=['POST'])
@admin_required
def update(sid):
    from backend.services import strategy_service
    
    name = request.form.get('name', '').strip()
    category = request.form.get('category', '').strip()
    description = request.form.get('description', '').strip()
    
    strategy_service.update_strategy(sid, name=name, category=category, description=description)
    flash('策略更新成功', 'success')
    return redirect(url_for('strategies.index'))


@bp.route('/<int:sid>/toggle', methods=['POST'])
@admin_required
def toggle(sid):
    from backend.services import strategy_service
    strategy_service.toggle_strategy(sid)
    return jsonify({'success': True})


@bp.route('/<int:sid>/delete', methods=['POST'])
@admin_required
def delete(sid):
    from backend.services import strategy_service
    strategy_service.delete_strategy(sid)
    flash('策略已停用', 'success')
    return redirect(url_for('strategies.index'))


@bp.route('/api/list')
def api_list():
    """API endpoint for getting active strategies (for dropdowns)."""
    from backend.services import strategy_service
    strategies = strategy_service.get_strategy_dropdown_options()
    return jsonify(strategies)
