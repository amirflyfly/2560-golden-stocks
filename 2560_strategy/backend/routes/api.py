import json
import os
import queue
import threading
import time
from functools import wraps
from uuid import uuid4

from flask import Blueprint, Response, current_app, jsonify, request, session, stream_with_context

bp = Blueprint('api', __name__)

_AGENT_JOB_LOCK = threading.Lock()
_AGENT_JOBS = {}
_AGENT_JOB_EVENTS = {}


@bp.after_request
def add_legacy_api_headers(response):
    response.headers['X-Legacy-API'] = 'deprecated'
    response.headers['Link'] = '</api/v1>; rel="successor-version"'
    return response


@bp.before_request
def freeze_production_legacy_api_writes_before_auth():
    if not _is_production() or request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        return None
    successor = '/app?page=dashboard' if request.path.endswith('/dashboard-order') else '/app?page=picks'
    if request.path.endswith('/save-stock-data'):
        successor = '/app?page=kline'
    return legacy_frozen_response(successor)


def _set_agent_job(job_id, **kwargs):
    with _AGENT_JOB_LOCK:
        payload = _AGENT_JOBS.get(job_id, {})
        payload.update(kwargs)
        _AGENT_JOBS[job_id] = payload
        return dict(payload)


def _get_agent_job(job_id):
    with _AGENT_JOB_LOCK:
        payload = _AGENT_JOBS.get(job_id, {})
        return dict(payload) if payload else None


def _ensure_agent_job_queue(job_id):
    with _AGENT_JOB_LOCK:
        q = _AGENT_JOB_EVENTS.get(job_id)
        if q is None:
            q = queue.Queue()
            _AGENT_JOB_EVENTS[job_id] = q
        return q


def _emit_agent_job_event(job_id, event, data):
    _ensure_agent_job_queue(job_id).put({
        'event': event,
        'data': data,
        'ts': time.time(),
    })


def _sse_pack(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _agent_snapshot_payload():
    agents = [
        {'team': '研究团队', 'agent': '市场分析师', 'status': 'pending'},
        {'team': '研究团队', 'agent': '情绪分析师', 'status': 'pending'},
        {'team': '研究团队', 'agent': '新闻分析师', 'status': 'pending'},
        {'team': '研究团队', 'agent': '基本面分析师', 'status': 'pending'},
        {'team': '研究团队', 'agent': '宏观分析师', 'status': 'pending'},
        {'team': '研究团队', 'agent': '资金分析师', 'status': 'pending'},
        {'team': '交易团队', 'agent': '交易员', 'status': 'pending'},
        {'team': '风控团队', 'agent': '风控官', 'status': 'pending'},
    ]
    return {'agents': agents}


def _run_agent_job(job_id, rid, analysis_date, engine):
    from backend.services.research_service import analyze_pick_by_id, build_watchlist_detail

    try:
        _set_agent_job(job_id, status='running', started_at=time.time())
        _emit_agent_job_event(job_id, 'job.running', {'job_id': job_id, 'rid': rid})
        _emit_agent_job_event(job_id, 'agent.snapshot', _agent_snapshot_payload())
        stage_defs = [
            ('市场分析师', 'market_report', '正在分析市场结构与趋势'),
            ('情绪分析师', 'sentiment_report', '正在分析情绪与题材热度'),
            ('新闻分析师', 'news_report', '正在汇总新闻与事件脉络'),
            ('基本面分析师', 'fundamentals_report', '正在提取基本面与财务观点'),
            ('宏观分析师', 'macro_report', '正在评估宏观环境影响'),
            ('资金分析师', 'smart_money_report', '正在跟踪资金流与主力行为'),
            ('交易员', 'volume_price_report', '正在形成交易计划与执行观点'),
        ]
        for agent, section, message in stage_defs:
            _emit_agent_job_event(job_id, 'agent.status', {'agent': agent, 'status': 'in_progress'})
            _emit_agent_job_event(job_id, 'job.progress', {'job_id': job_id, 'agent': agent, 'section': section, 'message': message})
            time.sleep(0.15)

        result = analyze_pick_by_id(rid, analysis_date=analysis_date or None, engine=engine or 'agent')
        if not result.get('success'):
            raise RuntimeError(result.get('message') or '分析失败')
        analysis = result.get('analysis', {}) or {}
        traces = analysis.get('analyst_traces') or []
        for index, trace in enumerate(traces):
            agent = trace.get('title') or trace.get('analyst') or trace.get('agent') or f'Agent {index + 1}'
            content = trace.get('content') or trace.get('summary') or trace.get('report') or ''
            if content:
                _emit_agent_job_event(job_id, 'agent.report.chunk', {
                    'agent': agent,
                    'section': f'trace_{index + 1}',
                    'chunk': content,
                    'index': index,
                    'is_complete': True,
                })
            _emit_agent_job_event(job_id, 'agent.status', {'agent': agent, 'status': 'completed'})
            time.sleep(0.05)

        detail = build_watchlist_detail(rid, engine=engine or 'agent')
        _set_agent_job(job_id, status='completed', result=detail, finished_at=time.time())
        _emit_agent_job_event(job_id, 'job.completed', {
            'job_id': job_id,
            'rid': rid,
            'engine': engine or 'agent',
            'result': detail,
        })
    except Exception as exc:
        _set_agent_job(job_id, status='failed', error=str(exc), finished_at=time.time())
        _emit_agent_job_event(job_id, 'job.failed', {'job_id': job_id, 'error': str(exc)})


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


def _is_production() -> bool:
    return (os.getenv('APP_ENV') or '').strip().lower() in {'prod', 'production'}


def legacy_frozen_response(successor='/app?page=picks'):
    response = jsonify({
        'success': False,
        'message': 'legacy write endpoint is frozen; use the React v1 workflow',
        'successor': successor,
    })
    response.status_code = 410
    return response


def freeze_legacy_write_in_production(successor='/app?page=picks'):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if _is_production():
                return legacy_frozen_response(successor)
            return f(*args, **kwargs)
        return wrapped
    return decorator


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
@freeze_legacy_write_in_production()
def create_pick():
    from backend.repositories import picks_repo
    from backend.services.format_service import num, int_num

    data = request.get_json(silent=True) or request.form
    created_id = picks_repo.create_or_replace_pick(
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
    new_id = int(created_id) if created_id else picks_repo.last_inserted_id()
    log_action('add', [new_id] if new_id else [], f"新增 {data.get('code','')} {data.get('name','')}")
    return jsonify({'success': True, 'id': new_id})


@bp.route('/picks/<int:rid>', methods=['PUT'])
@login_required
@freeze_legacy_write_in_production()
def update_pick(rid):
    from backend.repositories import picks_repo
    from backend.services.format_service import num, int_num

    data = request.get_json(silent=True) or request.form
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
@freeze_legacy_write_in_production()
def delete_pick(rid):
    from backend.repositories import picks_repo
    picks_repo.delete_pick(rid)
    log_action('delete', [rid], '单条删除')
    return jsonify({'success': True})


@bp.route('/picks/<int:rid>/archive', methods=['POST'])
@login_required
@freeze_legacy_write_in_production()
def archive_pick(rid):
    from backend.repositories import picks_repo
    picks_repo.set_archived(rid, True)
    log_action('archive', [rid], '单条归档')
    return jsonify({'success': True})


@bp.route('/picks/<int:rid>/unarchive', methods=['POST'])
@login_required
@freeze_legacy_write_in_production()
def unarchive_pick(rid):
    from backend.repositories import picks_repo
    picks_repo.set_archived(rid, False)
    log_action('unarchive', [rid], '单条恢复')
    return jsonify({'success': True})


@bp.route('/picks/<int:rid>/watch', methods=['POST'])
@login_required
def watch_pick(rid):
    return legacy_frozen_response()


@bp.route('/picks/<int:rid>/unwatch', methods=['POST'])
@login_required
def unwatch_pick(rid):
    return legacy_frozen_response()


@bp.route('/picks/<int:rid>/analyze', methods=['POST'])
@login_required
def analyze_pick(rid):
    return legacy_frozen_response()


@bp.route('/watch-pool', methods=['GET'])
@login_required
def get_watch_pool():
    from backend.repositories import picks_repo
    from backend.services.dashboard_service import dashboard_research_watchlist

    limit = request.args.get('limit', 20, type=int)
    picks = picks_repo.list_watch_picks(limit=limit)
    return jsonify({'success': True, 'items': picks, 'summary': dashboard_research_watchlist(limit=min(limit, 8))})


@bp.route('/watch-pool/analyze', methods=['POST'])
@login_required
def analyze_watch_pool():
    return legacy_frozen_response()


@bp.route('/watch-pool/<int:rid>/detail', methods=['GET'])
@login_required
def watch_pool_detail(rid):
    from backend.services.research_service import build_watchlist_detail

    engine = request.args.get('engine', '')
    result = build_watchlist_detail(rid, engine=engine or None)
    if not result.get('success'):
        return jsonify(result), 404
    return jsonify(result)


@bp.route('/watch-pool/<int:rid>/agent-stream', methods=['POST'])
@login_required
def start_watch_pool_agent_stream(rid):
    return legacy_frozen_response()


@bp.route('/watch-pool/agent-stream/<job_id>', methods=['GET'])
@login_required
def get_watch_pool_agent_stream_job(job_id):
    job = _get_agent_job(job_id)
    if not job:
        return jsonify({'success': False, 'message': '任务不存在'}), 404
    return jsonify({'success': True, 'job': job})


@bp.route('/watch-pool/agent-stream/<job_id>/events', methods=['GET'])
@login_required
def stream_watch_pool_agent_events(job_id):
    job = _get_agent_job(job_id)
    if not job:
        return jsonify({'success': False, 'message': '任务不存在'}), 404

    @stream_with_context
    def generate():
        q = _ensure_agent_job_queue(job_id)
        yield _sse_pack('job.ready', {'job_id': job_id})
        while True:
            try:
                payload = q.get(timeout=15)
                yield _sse_pack(payload['event'], payload['data'])
                if payload['event'] in ('job.completed', 'job.failed'):
                    yield 'event: done\ndata: [DONE]\n\n'
                    break
            except queue.Empty:
                current_job = _get_agent_job(job_id) or {}
                if current_job.get('status') in ('completed', 'failed'):
                    yield 'event: done\ndata: [DONE]\n\n'
                    break
                yield _sse_pack('ping', {'job_id': job_id, 'ts': time.time()})

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


@bp.route('/research/recent/analyze', methods=['POST'])
@login_required
def analyze_recent():
    return legacy_frozen_response()


@bp.route('/picks/batch/archive', methods=['POST'])
@login_required
@freeze_legacy_write_in_production()
def batch_archive():
    from backend.repositories import picks_repo
    ids = request.get_json().get('ids', [])
    picks_repo.batch_set_archived(ids, True)
    log_action('batch_archive', ids, f'批量归档 {len(ids)} 条')
    return jsonify({'success': True, 'count': len(ids)})


@bp.route('/picks/batch/unarchive', methods=['POST'])
@login_required
@freeze_legacy_write_in_production()
def batch_unarchive():
    from backend.repositories import picks_repo
    ids = request.get_json().get('ids', [])
    picks_repo.batch_set_archived(ids, False)
    log_action('batch_unarchive', ids, f'批量恢复 {len(ids)} 条')
    return jsonify({'success': True, 'count': len(ids)})


@bp.route('/picks/batch/delete', methods=['POST'])
@login_required
@freeze_legacy_write_in_production()
def batch_delete():
    from backend.repositories import picks_repo
    ids = request.get_json().get('ids', [])
    picks_repo.batch_delete(ids)
    log_action('batch_delete', ids, f'批量删除 {len(ids)} 条')
    return jsonify({'success': True, 'count': len(ids)})


@bp.route('/picks/batch/review-status', methods=['POST'])
@login_required
@freeze_legacy_write_in_production()
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
@freeze_legacy_write_in_production()
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
@freeze_legacy_write_in_production()
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
@freeze_legacy_write_in_production()
def batch_spread():
    from backend.repositories import picks_repo
    data = request.get_json()
    ids = data.get('ids', [])
    spread = data.get('spread', '否')
    picks_repo.batch_set_secondary_spread(ids, spread)
    log_action('batch_spread', ids, f'批量改二次传播为 {spread}')
    return jsonify({'success': True, 'count': len(ids)})


@bp.route('/export', methods=['GET'])
@login_required
def export_json():
    from backend.repositories import picks_repo
    from backend.services.query_service import filter_where

    params = {k: [v] for k, v in request.args.items()}
    where, args = filter_where(params)
    picks = picks_repo.list_picks(where, args)
    return jsonify(picks)


@bp.route('/export.csv', methods=['GET'])
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
@freeze_legacy_write_in_production()
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
@freeze_legacy_write_in_production()
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
@freeze_legacy_write_in_production()
def delete_filter(fid):
    from backend.services.filters_service import delete_saved_filter
    delete_saved_filter(fid)
    log_action('delete_filter', [], f'删除筛选视图 id={fid}')
    return jsonify({'success': True})


@bp.route('/filters/<int:fid>/rename', methods=['POST'])
@login_required
@freeze_legacy_write_in_production()
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
@freeze_legacy_write_in_production('/app?page=dashboard')
def save_dashboard_order():
    from backend.services.filters_service import set_dashboard_order

    data = request.get_json()
    order = data.get('order', '').strip()
    if order:
        set_dashboard_order(order)
        log_action('save_dashboard_order', [], f'保存首页模块顺序：{order}')
        return jsonify({'success': True})
    return jsonify({'error': '顺序不能为空'}), 400


@bp.route('/stock-data', methods=['GET'])
@login_required
def get_stock_data():
    from backend.services.stock_data_service import get_stock_data_service

    code = request.args.get('code', '600519')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    if not start_date or not end_date:
        return jsonify({'success': False, 'message': '请提供开始日期和结束日期'}), 400

    try:
        stock_data = get_stock_data_service()
        df = stock_data.get_stock_hist(code, start_date, end_date)

        if df is None or df.empty:
            return jsonify({'success': False, 'message': '获取数据失败'}), 400

        kline_data = []
        for _, row in df.iterrows():
            kline_data.append({
                'time': row.get('date', ''),
                'open': float(row.get('open', 0)),
                'high': float(row.get('high', 0)),
                'low': float(row.get('low', 0)),
                'close': float(row.get('close', 0)),
                'volume': float(row.get('volume', 0))
            })

        return jsonify({'success': True, 'data': kline_data})
    except Exception:
        current_app.logger.exception('get_stock_data failed')
        return jsonify({'success': False, 'message': '获取股票数据失败，请稍后重试'}), 500


@bp.route('/save-stock-data', methods=['POST'])
@login_required
@freeze_legacy_write_in_production('/app?page=kline')
def save_stock_data():
    data = request.get_json()
    code = data.get('code', '')
    stock_data = data.get('data', [])

    if not code or not stock_data:
        return jsonify({'success': False, 'message': '请提供股票代码和数据'}), 400

    try:
        print(f"保存股票数据: {code}, 共 {len(stock_data)} 条记录")
        return jsonify({'success': True, 'message': '数据保存成功'})
    except Exception:
        current_app.logger.exception('save_stock_data failed')
        return jsonify({'success': False, 'message': '保存股票数据失败，请稍后重试'}), 500
