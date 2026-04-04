"""Strategy pool repository."""

from typing import List, Dict, Any
from backend.repositories.db import q, q1, execute, execute_many


def get_pool_by_strategy(strategy_code: str) -> List[Dict[str, Any]]:
    """Get pool stocks by strategy code."""
    return q(
        """
        SELECT * FROM strategy_pools 
        WHERE strategy_code = ? AND status = 'active'
        ORDER BY add_date DESC
        """,
        (strategy_code,)
    )


def add_to_pool(strategy_code: str, code: str, name: str, add_date: str, add_price: float, reason: str = '') -> bool:
    """Add stock to strategy pool."""
    try:
        execute(
            """
            INSERT OR IGNORE INTO strategy_pools 
            (strategy_code, code, name, add_date, add_price, reason)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (strategy_code, code, name, add_date, add_price, reason)
        )
        return True
    except Exception:
        return False


def remove_from_pool(strategy_code: str, code: str) -> bool:
    """Remove stock from strategy pool."""
    try:
        execute(
            "UPDATE strategy_pools SET status = 'removed' WHERE strategy_code = ? AND code = ?",
            (strategy_code, code)
        )
        return True
    except Exception:
        return False


def get_backtest_results(strategy_code: str) -> List[Dict[str, Any]]:
    """Get backtest results by strategy."""
    return q(
        """
        SELECT * FROM backtest_results 
        WHERE strategy_code = ?
        ORDER BY backtest_date DESC
        """,
        (strategy_code,)
    )


def save_backtest_result(strategy_code: str, start_date: str, end_date: str, results: Dict[str, Any]) -> bool:
    """Save backtest result."""
    try:
        execute(
            """
            INSERT INTO backtest_results 
            (strategy_code, start_date, end_date, total_trades, win_rate, avg_return, 
             max_return, max_drawdown, sharpe_ratio, total_return)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                strategy_code,
                start_date,
                end_date,
                results.get('total_trades'),
                results.get('win_rate'),
                results.get('avg_return'),
                results.get('max_return'),
                results.get('max_drawdown'),
                results.get('sharpe_ratio'),
                results.get('total_return')
            )
        )
        return True
    except Exception:
        return False
