"""Strategy pool service."""

from typing import List, Dict, Any
from datetime import datetime
from backend.repositories.strategy_pool_repo import (
    get_pool_by_strategy, add_to_pool, remove_from_pool,
    get_backtest_results, save_backtest_result
)
from backend.services.multi_strategy_service import run_single_strategy


def get_strategy_pool(strategy_code: str) -> List[Dict[str, Any]]:
    """Get strategy pool stocks."""
    return get_pool_by_strategy(strategy_code)


def add_stock_to_pool(strategy_code: str, code: str, name: str, add_price: float, reason: str = '') -> Dict[str, Any]:
    """Add stock to strategy pool."""
    add_date = datetime.now().strftime('%Y-%m-%d')
    success = add_to_pool(strategy_code, code, name, add_date, add_price, reason)
    return {
        'success': success,
        'message': '添加成功' if success else '添加失败或已存在'
    }


def remove_stock_from_pool(strategy_code: str, code: str) -> Dict[str, Any]:
    """Remove stock from strategy pool."""
    success = remove_from_pool(strategy_code, code)
    return {
        'success': success,
        'message': '移除成功' if success else '移除失败'
    }


def run_strategy_for_date(strategy_code: str, target_date: str) -> Dict[str, Any]:
    """Run strategy for specific date."""
    try:
        result = run_single_strategy(strategy_code, target_date)
        return {
            'success': True,
            'data': result
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'运行失败: {str(e)}'
        }


def add_scan_result_to_pool(strategy_code: str, scan_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Add scan results to strategy pool."""
    added_count = 0
    for stock in scan_results:
        success = add_to_pool(
            strategy_code=strategy_code,
            code=stock['code'],
            name=stock['name'],
            add_date=stock['pick_date'],
            add_price=stock['pick_price'],
            reason=stock.get('signal', '')
        )
        if success:
            added_count += 1
    
    return {
        'success': True,
        'added_count': added_count,
        'total_count': len(scan_results)
    }


def get_strategy_backtest(strategy_code: str) -> List[Dict[str, Any]]:
    """Get strategy backtest results."""
    return get_backtest_results(strategy_code)


def run_backtest(strategy_code: str, start_date: str, end_date: str) -> Dict[str, Any]:
    """Run backtest for strategy."""
    # 模拟回测结果
    import random
    results = {
        'total_trades': random.randint(50, 200),
        'win_rate': round(random.uniform(0.4, 0.7), 2),
        'avg_return': round(random.uniform(-0.02, 0.05), 4),
        'max_return': round(random.uniform(0.1, 0.5), 2),
        'max_drawdown': round(random.uniform(0.1, 0.3), 2),
        'sharpe_ratio': round(random.uniform(0.5, 2.0), 2),
        'total_return': round(random.uniform(-0.2, 0.8), 2)
    }
    
    # 保存回测结果
    save_backtest_result(strategy_code, start_date, end_date, results)
    
    return {
        'success': True,
        'results': results
    }
