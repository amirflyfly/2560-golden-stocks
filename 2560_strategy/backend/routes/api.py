from flask import Blueprint, request, jsonify, session, flash, redirect, url_for
from functools import wraps

bp = Blueprint('api', __name__)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from backend.services.multiuser_auth_service import get_session
        token = session.get('auth_token')
        if not token or not get_session(token):
            return jsonify({'error': '未登录'}), 401
        return f(*args, **kwargs)
    return decorated_function


def get_current_user():
    from backend.services.multiuser_auth_service import get_session
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


def log_action(action, target_ids=None, detail=''):
    from backend.services.logs_service import log_action as do_log
    user = get_current_user() or {}
    do_log(action, target_ids=target_ids, detail=detail, actor=user)


@bp.route('/picks', methods=['GET'])
@login_required
def list_picks():
    from backend.repositories import picks_repo
    from backend.services.query_service import filter_where
    
    params = {k: [v] for k, v in request.args.items()}
    where, args = filter_where(params)
    picks = picks_repo.list_picks(where, args)
    return jsonify(picks)


@bp.route('/picks', methods=['POST'])
@login_required
def create_pick():
    from backend.repositories import picks_repo
    from backend.services.format_service import num, int_num
    
    data = request.get_json() or request.form
    picks_repo.create_or_replace_pick(
        pick_date=data.get('pick_date', ''),
        code=data.get('code', ''),
        name=data.get('name', ''),
        pick_price=num(data.get('pick_price', '0')),
        signal=data.get('signal', ''),
        source='webform',
        source_channel=data.get('source_channel', 'web'),
        reason_tag=data.get('reason_tag', ''),
        note=data.get('note', ''),
        review_status=data.get('review_status', '未复盘'),
        review_comment=data.get('note', ''),
        content_title=data.get('content_title', ''),
        content_ref=data.get('content_ref', ''),
        result_grade=data.get('result_grade', '待定'),
        inquiry_count=int_num(data.get('inquiry_count', 0)),
        deal_status=data.get('deal_status', '未成交'),
        secondary_spread=data.get('secondary_spread', '否'),
        strategy_name=data.get('strategy_name', '2560'),
    )
    new_id = picks_repo.last_inserted_id()
    log_action('add', [new_id] if new_id else [], f"新增 {data.get('code','')} {data.get('name','')}")
    return jsonify({'success': True, 'id': new_id})


@bp.route('/picks/<int:rid>', methods=['PUT'])
@login_required
def update_pick(rid):
    from backend.repositories import picks_repo
    from backend.services.format_service import num, int_num
    
    data = request.get_json() or request.form
    picks_repo.update_pick(
        rid=rid,
        pick_date=data.get('pick_date', ''),
        code=data.get('code', ''),
        name=data.get('name', ''),
        pick_price=num(data.get('pick_price', '0')),
        signal=data.get('signal', ''),
        source_channel=data.get('source_channel', ''),
        reason_tag=data.get('reason_tag', ''),
        note=data.get('note', ''),
        review_status=data.get('review_status', '未复盘'),
        review_comment=data.get('note', ''),
        content_title=data.get('content_title', ''),
        content_ref=data.get('content_ref', ''),
        result_grade=data.get('result_grade', '待定'),
        inquiry_count=int_num(data.get('inquiry_count', 0)),
        deal_status=data.get('deal_status', '未成交'),
        secondary_spread=data.get('secondary_spread', '否'),
        strategy_name=data.get('strategy_name', '2560'),
    )
    log_action('update', [rid], f'编辑记录 {rid}')
    return jsonify({'success': True})


@bp.route('/picks/<int:rid>', methods=['DELETE'])
@login_required
def delete_pick(rid):
    from backend.repositories import picks_repo
    picks_repo.delete_pick(rid)
    log_action('delete', [rid], '单条删除')
    return jsonify({'success': True})


@bp.route('/picks/<int:rid>/archive', methods=['POST'])
@login_required
def archive_pick(rid):
    from backend.repositories import picks_repo
    picks_repo.set_archived(rid, True)
    log_action('archive', [rid], '单条归档')
    return jsonify({'success': True})


@bp.route('/picks/<int:rid>/unarchive', methods=['POST'])
@login_required
def unarchive_pick(rid):
    from backend.repositories import picks_repo
    picks_repo.set_archived(rid, False)
    log_action('unarchive', [rid], '单条恢复')
    return jsonify({'success': True})


@bp.route('/picks/batch/archive', methods=['POST'])
@login_required
def batch_archive():
    from backend.repositories import picks_repo
    ids = request.get_json().get('ids', [])
    picks_repo.batch_set_archived(ids, True)
    log_action('batch_archive', ids, f'批量归档 {len(ids)} 条')
    return jsonify({'success': True, 'count': len(ids)})


@bp.route('/picks/batch/unarchive', methods=['POST'])
@login_required
def batch_unarchive():
    from backend.repositories import picks_repo
    ids = request.get_json().get('ids', [])
    picks_repo.batch_set_archived(ids, False)
    log_action('batch_unarchive', ids, f'批量恢复 {len(ids)} 条')
    return jsonify({'success': True, 'count': len(ids)})


@bp.route('/picks/batch/delete', methods=['POST'])
@login_required
def batch_delete():
    from backend.repositories import picks_repo
    ids = request.get_json().get('ids', [])
    picks_repo.batch_delete(ids)
    log_action('batch_delete', ids, f'批量删除 {len(ids)} 条')
    return jsonify({'success': True, 'count': len(ids)})


@bp.route('/picks/batch/review-status', methods=['POST'])
@login_required
def batch_review_status():
    from backend.repositories import picks_repo
    data = request.get_json()
    ids = data.get('ids', [])
    status = data.get('status', '未复盘')
    picks_repo.batch_set_review_status(ids, status)
    log_action('batch_review', ids, f'批量改复盘状态为 {status}')
    return jsonify({'success': True, 'count': len(ids)})


@bp.route('/picks/batch/grade', methods=['POST'])
@login_required
def batch_grade():
    from backend.repositories import picks_repo
    data = request.get_json()
    ids = data.get('ids', [])
    grade = data.get('grade', '待定')
    picks_repo.batch_set_result_grade(ids, grade)
    log_action('batch_grade', ids, f'批量改评级为 {grade}')
    return jsonify({'success': True, 'count': len(ids)})


@bp.route('/picks/batch/deal-status', methods=['POST'])
@login_required
def batch_deal_status():
    from backend.repositories import picks_repo
    data = request.get_json()
    ids = data.get('ids', [])
    status = data.get('status', '未成交')
    picks_repo.batch_set_deal_status(ids, status)
    log_action('batch_deal', ids, f'批量改成交状态为 {status}')
    return jsonify({'success': True, 'count': len(ids)})


@bp.route('/picks/batch/spread', methods=['POST'])
@login_required
def batch_spread():
    from backend.repositories import picks_repo
    data = request.get_json()
    ids = data.get('ids', [])
    spread = data.get('spread', '否')
    picks_repo.batch_set_secondary_spread(ids, spread)
    log_action('batch_spread', ids, f'批量改二次传播为 {spread}')
    return jsonify({'success': True, 'count': len(ids)})


@bp.route('/export')
@login_required
def export_json():
    from backend.repositories import picks_repo
    from backend.services.query_service import filter_where
    
    params = {k: [v] for k, v in request.args.items()}
    where, args = filter_where(params)
    picks = picks_repo.list_picks(where, args)
    return jsonify(picks)


@bp.route('/export.csv')
@login_required
def export_csv():
    from backend.repositories import picks_repo
    from backend.services.query_service import filter_where
    from backend.services.io_service import rows_to_csv
    from flask import Response
    
    params = {k: [v] for k, v in request.args.items()}
    where, args = filter_where(params)
    picks = picks_repo.list_picks(where, args)
    csv_body = rows_to_csv(picks)
    return Response(
        csv_body,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename="export.csv"'}
    )


@bp.route('/bulk-import', methods=['POST'])
@login_required
def bulk_import():
    from backend.services.io_service import bulk_import_from_csv
    
    csv_text = request.form.get('csv_text', '')
    ids = bulk_import_from_csv(csv_text)
    log_action('bulk_import', ids, f'CSV 导入 {len(ids)} 条')
    return jsonify({'success': True, 'count': len(ids), 'ids': ids})


@bp.route('/filters', methods=['GET'])
@login_required
def list_filters():
    from backend.services.filters_service import get_saved_filters
    return jsonify(get_saved_filters())


@bp.route('/filters', methods=['POST'])
@login_required
def save_filter():
    from backend.services.filters_service import save_current_filter
    
    data = request.get_json()
    name = data.get('name', '').strip()
    query_string = data.get('query_string', '').strip()
    if name and query_string:
        save_current_filter(name, query_string)
        log_action('save_filter', [], f'保存筛选视图：{name}')
        return jsonify({'success': True})
    return jsonify({'error': '参数不完整'}), 400


@bp.route('/filters/<int:fid>', methods=['DELETE'])
@login_required
def delete_filter(fid):
    from backend.services.filters_service import delete_saved_filter
    delete_saved_filter(fid)
    log_action('delete_filter', [], f'删除筛选视图 id={fid}')
    return jsonify({'success': True})


@bp.route('/filters/<int:fid>/rename', methods=['POST'])
@login_required
def rename_filter(fid):
    from backend.services.filters_service import rename_saved_filter
    
    data = request.get_json()
    new_name = data.get('name', '').strip()
    if new_name:
        rename_saved_filter(fid, new_name)
        log_action('rename_filter', [], f'重命名筛选视图 id={fid} -> {new_name}')
        return jsonify({'success': True})
    return jsonify({'error': '名称不能为空'}), 400


@bp.route('/dashboard-order', methods=['POST'])
@login_required
def save_dashboard_order():
    from backend.services.filters_service import set_dashboard_order
    
    data = request.get_json()
    order = data.get('order', '').strip()
    if order:
        set_dashboard_order(order)
        log_action('save_dashboard_order', [], f'保存首页模块顺序：{order}')
        return jsonify({'success': True})
    return jsonify({'error': '顺序不能为空'}), 400
