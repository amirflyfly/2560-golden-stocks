import os

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps
from datetime import datetime, timedelta

bp = Blueprint('main', __name__)


def _is_production() -> bool:
    return any((os.getenv(name) or '').strip().lower() in {'prod', 'production'} for name in ('APP_ENV', 'FLASK_ENV'))


def _legacy_main_frozen_response(successor='/app?page=dashboard'):
    response = jsonify({
        'success': False,
        'message': 'legacy page write endpoint is frozen; use the React v1 workflow',
        'successor': successor,
    })
    response.status_code = 410
    return response


@bp.before_request
def freeze_production_legacy_main_writes_before_auth():
    if not _is_production() or request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        return None
    if request.endpoint == 'main.login':
        return None
    if request.endpoint == 'main.set_language':
        return None
    return _legacy_main_frozen_response()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from backend.services.multiuser_auth_service import get_session
        token = session.get('auth_token')
        if not token or not get_session(token):
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from backend.services.multiuser_auth_service import get_session
        token = session.get('auth_token')
        sess = get_session(token)
        if not sess or sess.get('role') != 'admin':
            flash('需要管理员权限', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def get_current_user():
    from backend.services.multiuser_auth_service import get_session
    token = session.get('auth_token')
    if token:
        sess = get_session(token)
        if sess:
            from backend.repositories import users_repo
            user = users_repo.get_user_by_id(sess.get('user_id'))
            return {
                'user_id': sess.get('user_id'),
                'username': sess.get('username'),
                'role': sess.get('role'),
                'points': user.get('points', 0) if user else 0,
            }
    return None


@bp.route('/health')
def health():
    return 'ok'


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        csrf_token = request.form.get('csrf_token', '')
        if not csrf_token or csrf_token != session.get('_csrf_token'):
            flash('请求校验失败，请刷新页面后重试', 'error')
            return render_template('login.html'), 403
        from backend.services.multiuser_auth_service import login as do_login
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        sess = do_login(username, password)
        if sess:
            session['auth_token'] = sess['session_token']
            session.permanent = True
            return redirect(url_for('main.dashboard'))
        flash('账号或密码错误', 'error')
    return render_template('login.html')


@bp.route('/logout')
def logout():
    from backend.services.multiuser_auth_service import logout
    token = session.get('auth_token')
    if token:
        logout(token)
    session.clear()
    return redirect(url_for('main.login'))


@bp.route('/')
@login_required
def dashboard():
    return redirect('/app?page=dashboard')


@bp.route('/watchlist')
@login_required
def watchlist():
    from backend.repositories import picks_repo
    from backend.services.research_service import build_watchlist_detail, list_research_engines

    watch_items = picks_repo.list_watch_picks(limit=100)
    selected_id = request.args.get('id', type=int)
    engine = request.args.get('engine', '').strip() or None
    detail = None
    if selected_id:
        detail = build_watchlist_detail(selected_id, engine=engine)
    elif watch_items:
        detail = build_watchlist_detail(watch_items[0]['id'], engine=engine)
    return render_template(
        'watchlist.html',
        user=get_current_user(),
        watch_items=watch_items,
        detail=detail,
        research_engines=list_research_engines(),
        current_engine=(detail or {}).get('engine', engine or 'rule'),
    )


@bp.route('/edit')
@login_required
def edit():
    suffix = f"&pick_id={request.args.get('id')}" if request.args.get('id') else ''
    return redirect(f'/app?page=picks{suffix}')


@bp.route('/deal-review')
@login_required
def deal_review():
    return redirect('/app?page=picks&status=validated')


@bp.route('/leaderboards')
@login_required
def leaderboards():
    from backend.services.leaderboard_service import leaderboards
    range_val = request.args.get('range', '30d')
    metric = request.args.get('metric', 'default')
    boards = leaderboards(range_val, metric)
    return render_template(
        'leaderboards.html',
        user=get_current_user(),
        boards=boards,
        current_range=range_val,
        current_metric=metric,
    )


@bp.route('/reports')
@login_required
def reports():
    return redirect('/app?page=reports')


@bp.route('/user/profile')
@login_required
def user_profile():
    user = get_current_user()
    from backend.repositories import users_repo
    user_detail = users_repo.get_user_by_id(user['user_id'])
    return render_template(
        'user_profile.html',
        user=user,
        user_detail=user_detail
    )


@bp.route('/user/checkin', methods=['GET', 'POST'])
@login_required
def checkin():
    user = get_current_user()
    if request.method == 'POST':
        from backend.repositories import users_repo
        today = datetime.now().strftime('%Y-%m-%d')
        last_checkin = users_repo.get_user_last_checkin(user['user_id'])
        if last_checkin == today:
            flash('今日已签到', 'info')
        else:
            points_awarded = 10
            success = users_repo.update_user_points(user['user_id'], points_awarded)
            if success:
                users_repo.update_user_last_checkin(user['user_id'], today)
                flash(f'签到成功，获得 {points_awarded} 积分', 'success')
            else:
                flash('签到失败', 'error')
        return redirect(url_for('main.user_profile'))
    return render_template(
        'checkin.html',
        user=user
    )


@bp.route('/api/set-language', methods=['POST'])
def set_language():
    data = request.json
    language = data.get('language', 'zh-CN')
    session['language'] = language
    return jsonify({'success': True})


def get_current_language():
    return session.get('language', 'zh-CN')


def get_dark_mode():
    return session.get('dark_mode', False)


def get_sidebar_collapsed():
    return session.get('sidebar_collapsed', False)
