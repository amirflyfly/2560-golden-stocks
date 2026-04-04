"""Strategy management routes."""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from datetime import datetime, timedelta
from backend.services.strategy_service import get_all_strategies
from backend.services.strategy_pool_service import (
    get_strategy_pool, add_stock_to_pool, remove_stock_from_pool,
    run_strategy_for_date, add_scan_result_to_pool,
    get_strategy_backtest, run_backtest
)

strategy_management_bp = Blueprint('strategy_management', __name__)


@strategy_management_bp.route('/strategies/pool/<strategy_code>')
def strategy_pool(strategy_code):
    """Strategy pool page."""
    strategies = get_all_strategies()
    strategy = next((s for s in strategies if s['code'] == strategy_code), None)
    if not strategy:
        return redirect(url_for('strategies.index'))
    
    pool_stocks = get_strategy_pool(strategy_code)
    backtest_results = get_strategy_backtest(strategy_code)
    today = datetime.now().strftime('%Y-%m-%d')
    backtest_start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    
    return render_template('strategies/pool.html',
                         strategy=strategy,
                         strategies=strategies,
                         pool_stocks=pool_stocks,
                         backtest_results=backtest_results,
                         today=today,
                         backtest_start_date=backtest_start_date)


@strategy_management_bp.route('/strategies/run/<strategy_code>', methods=['GET', 'POST'])
def strategy_run(strategy_code):
    """Strategy manual run page."""
    strategies = get_all_strategies()
    strategy = next((s for s in strategies if s['code'] == strategy_code), None)
    if not strategy:
        return redirect(url_for('strategies.index'))
    
    if request.method == 'POST':
        target_date = request.form.get('target_date')
        if not target_date:
            return jsonify({'success': False, 'message': '请选择日期'})
        
        result = run_strategy_for_date(strategy_code, target_date)
        return jsonify(result)
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    return render_template('strategies/run.html',
                         strategy=strategy,
                         strategies=strategies,
                         today=today)


@strategy_management_bp.route('/strategies/backtest/<strategy_code>', methods=['GET', 'POST'])
def strategy_backtest(strategy_code):
    """Strategy backtest page."""
    strategies = get_all_strategies()
    strategy = next((s for s in strategies if s['code'] == strategy_code), None)
    if not strategy:
        return redirect(url_for('strategies.index'))
    
    if request.method == 'POST':
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        if not start_date or not end_date:
            return jsonify({'success': False, 'message': '请选择起止日期'})
        
        result = run_backtest(strategy_code, start_date, end_date)
        return jsonify(result)
    
    backtest_results = get_strategy_backtest(strategy_code)
    today = datetime.now().strftime('%Y-%m-%d')
    backtest_start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    
    return render_template('strategies/backtest.html',
                         strategy=strategy,
                         strategies=strategies,
                         backtest_results=backtest_results,
                         today=today,
                         backtest_start_date=backtest_start_date)


@strategy_management_bp.route('/api/strategy/pool/add', methods=['POST'])
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
