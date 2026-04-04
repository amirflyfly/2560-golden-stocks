from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps
from datetime import datetime, timedelta

bp = Blueprint('main', __name__)


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
            # Get user points from database
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
    from backend.services.dashboard_service import (
        dashboard_overview, dashboard_kpi, dashboard_channels, dashboard_tags,
        dashboard_review_status, dashboard_grades, dashboard_deals,
        dashboard_trend_30d, dashboard_worthy_trend_30d, dashboard_deal_trend_30d,
        recent_operation_logs, dashboard_strategy_summary, dashboard_strategy_panels,
        dashboard_strategy_compare, dashboard_second_board_pool, dashboard_watch_pool,
        dashboard_validate_rows, dashboard_validate_stats, dashboard_validate_rate,
        dashboard_hit_compare, dashboard_strategy_names, dashboard_daily_strategy_matrix,
        dashboard_daily_strategy_picks,
    )
    from backend.services.filters_service import get_saved_filters, get_dashboard_order
    from backend.services.query_service import filter_where
    from backend.services import strategy_service
    from backend.repositories import picks_repo
    from backend.services import backup_service
    from backend.app_config import PAGE_SIZE
    
    page = request.args.get('page', 1, type=int)
    target_date = (request.args.get('target_date') or datetime.now().strftime('%Y-%m-%d')).strip()
    selected_strategy = (request.args.get('strategy') or '').strip()
    saved_filters = get_saved_filters()
    dashboard_order = get_dashboard_order()
    strategy_options = strategy_service.get_strategy_dropdown_options()
    
    overview = dashboard_overview()
    kpi = dashboard_kpi()
    by_channel = dashboard_channels()
    by_tag = dashboard_tags()
    by_status = dashboard_review_status()
    by_grade = dashboard_grades()
    by_deal = dashboard_deals()
    trend_30d = dashboard_trend_30d()
    worthy_trend = dashboard_worthy_trend_30d()
    deal_trend = dashboard_deal_trend_30d()
    recent_logs = recent_operation_logs(15)
    bstats = backup_service.backup_stats()
    strategy_summary = dashboard_strategy_summary()
    strategy_panels = dashboard_strategy_panels()
    strategy_compare = dashboard_strategy_compare()
    strategy_names = dashboard_strategy_names()
    daily_strategy_matrix = strategy_service.get_daily_strategy_summary(target_date)
    daily_strategy_picks = dashboard_daily_strategy_picks(target_date, selected_strategy)
    second_board_pool = dashboard_second_board_pool()
    watch_pool = dashboard_watch_pool()
    validate_rows = dashboard_validate_rows()
    validate_stats = dashboard_validate_stats()
    validate_rate = dashboard_validate_rate()
    hit_compare = dashboard_hit_compare()
    
    params = {k: [v] for k, v in request.args.items() if k != 'page'}
    where, args = filter_where(params)
    filter_count = picks_repo.count_picks(where, args)
    offset = (page - 1) * PAGE_SIZE
    latest = picks_repo.list_picks(where, args, limit=PAGE_SIZE, offset=offset)
    
    total_pages = max(1, (filter_count + PAGE_SIZE - 1) // PAGE_SIZE)
    
    return render_template('dashboard.html',
        user=get_current_user(),
        overview=overview,
        kpi=kpi,
        by_channel=by_channel,
        by_tag=by_tag,
        by_status=by_status,
        by_grade=by_grade,
        by_deal=by_deal,
        trend_30d=trend_30d,
        worthy_trend=worthy_trend,
        deal_trend=deal_trend,
        recent_logs=recent_logs,
        bstats=bstats,
        strategy_summary=strategy_summary,
        strategy_panels=strategy_panels,
        strategy_compare=strategy_compare,
        strategy_names=strategy_names,
        daily_strategy_matrix=daily_strategy_matrix,
        daily_strategy_picks=daily_strategy_picks,
        selected_strategy=selected_strategy,
        target_date=target_date,
        second_board_pool=second_board_pool,
        watch_pool=watch_pool,
        validate_rows=validate_rows,
        validate_stats=validate_stats,
        validate_rate=validate_rate,
        hit_compare=hit_compare,
        saved_filters=saved_filters,
        dashboard_order=dashboard_order,
        latest=latest,
        page=page,
        total_pages=total_pages,
        filter_count=filter_count,
        request_args=request.args,
        today=datetime.now().strftime('%Y-%m-%d'),
        backtest_start_date=(datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d'),
        strategy_options=strategy_options,
    )


@bp.route('/edit')
@login_required
def edit():
    from backend.repositories import picks_repo
    rid = request.args.get('id')
    pick = picks_repo.get_pick_by_id(rid) if rid else None
    return render_template('edit.html', pick=pick, user=get_current_user())


@bp.route('/deal-review')
@login_required
def deal_review():
    from backend.services.leaderboard_service import leaderboards
    from backend.services.dashboard_service import dashboard_deals
    from backend.repositories import picks_repo
    from backend.app_config import PAGE_SIZE, REVIEW_STATUS_OPTIONS, RESULT_GRADE_OPTIONS, DEAL_STATUS_OPTIONS
    
    page = request.args.get('page', 1, type=int)
    where = "WHERE deal_status != '未成交'"
    args = []
    total = picks_repo.count_picks(where, args)
    offset = (page - 1) * PAGE_SIZE
    deals = picks_repo.list_picks(where, args, limit=PAGE_SIZE, offset=offset)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    
    return render_template('deal_review.html',
        user=get_current_user(),
        deals=deals,
        page=page,
        total_pages=total_pages,
        total=total,
    )


@bp.route('/leaderboards')
@login_required
def leaderboards():
    from backend.services.leaderboard_service import leaderboards
    range_val = request.args.get('range', '30d')
    metric = request.args.get('metric', 'default')
    boards = leaderboards(range_val, metric)
    return render_template('leaderboards.html',
        user=get_current_user(),
        boards=boards,
        current_range=range_val,
        current_metric=metric,
    )


@bp.route('/reports')
@login_required
def reports():
    from backend.services.reports_service import report_summary_text, weekly_report_rows, monthly_report_rows
    summary = report_summary_text()
    weekly = list(weekly_report_rows())
    monthly = list(monthly_report_rows())
    return render_template('reports.html',
        user=get_current_user(),
        summary=summary,
        weekly=weekly,
        monthly=monthly,
    )


@bp.route('/user/profile')
@login_required
def user_profile():
    """User profile page."""
    user = get_current_user()
    from backend.repositories import users_repo
    user_detail = users_repo.get_user_by_id(user['user_id'])
    return render_template('user_profile.html',
        user=user,
        user_detail=user_detail
    )


@bp.route('/user/checkin', methods=['GET', 'POST'])
@login_required
def checkin():
    """User checkin."""
    user = get_current_user()
    if request.method == 'POST':
        from backend.repositories import users_repo
        # Check if already checked in today
        today = datetime.now().strftime('%Y-%m-%d')
        last_checkin = users_repo.get_user_last_checkin(user['user_id'])
        if last_checkin == today:
            flash('今日已签到', 'info')
        else:
            # Award points for checkin
            points_awarded = 10  # 每日签到获得10积分
            success = users_repo.update_user_points(user['user_id'], points_awarded)
            if success:
                users_repo.update_user_last_checkin(user['user_id'], today)
                flash(f'签到成功，获得 {points_awarded} 积分', 'success')
            else:
                flash('签到失败', 'error')
        return redirect(url_for('main.user_profile'))
    return render_template('checkin.html',
        user=user
    )


@bp.route('/api/set-language', methods=['POST'])
def set_language():
    """Set user language preference."""
    data = request.json
    language = data.get('language', 'zh-CN')
    # Store language in session
    session['language'] = language
    return jsonify({'success': True})


def get_current_language():
    """Get current language."""
    return session.get('language', 'zh-CN')


def get_dark_mode():
    """Get dark mode preference."""
    return session.get('dark_mode', False)


def get_sidebar_collapsed():
    """Get sidebar collapsed preference."""
    return session.get('sidebar_collapsed', False)
