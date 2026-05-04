"""Strategy pool service."""

from math import sqrt
from typing import List, Dict, Any
from datetime import datetime
from backend.repositories.strategy_pool_repo import (
    get_pool_by_strategy, add_to_pool, remove_from_pool,
    get_backtest_results, save_backtest_result
)
from backend.services.multi_strategy_service import run_single_strategy
from backend.strategies import registry
from backend.services.stock_data_service import get_stock_data_service


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


def _calculate_equity_curve(trades: List[Dict[str, Any]]) -> List[float]:
    equity = [1.0]
    current = 1.0
    for trade in trades:
        current *= 1 + float(trade.get('return_pct', 0))
        equity.append(current)
    return equity


def _calculate_max_drawdown(equity_curve: List[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            drawdown = (peak - value) / peak
            max_drawdown = max(max_drawdown, drawdown)
    return max_drawdown


def _build_summary(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not trades:
        return {
            'total_trades': 0,
            'win_rate': 0,
            'avg_return': 0,
            'max_return': 0,
            'max_loss': 0,
            'max_drawdown': 0,
            'sharpe_ratio': 0,
            'total_return': 0,
            'avg_holding_days': 0,
            'profit_factor': 0,
            'avg_win_return': 0,
            'avg_loss_return': 0,
            'best_trade': None,
            'worst_trade': None,
            'trades': []
        }

    returns = [float(t.get('return_pct', 0)) for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    equity_curve = _calculate_equity_curve(trades)
    total_return = equity_curve[-1] - 1
    avg_return = sum(returns) / len(returns)
    variance = sum((r - avg_return) ** 2 for r in returns) / len(returns) if returns else 0
    std_dev = variance ** 0.5
    sharpe_ratio = 0 if std_dev == 0 else (avg_return / std_dev) * sqrt(len(returns))
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0)
    avg_holding_days = sum(int(t.get('holding_days', 0)) for t in trades) / len(trades)
    best_trade = max(trades, key=lambda t: float(t.get('return_pct', 0)))
    worst_trade = min(trades, key=lambda t: float(t.get('return_pct', 0)))

    return {
        'total_trades': len(trades),
        'win_rate': len(wins) / len(trades),
        'avg_return': avg_return,
        'max_return': max(returns),
        'max_loss': min(returns),
        'max_drawdown': _calculate_max_drawdown(equity_curve),
        'sharpe_ratio': sharpe_ratio,
        'total_return': total_return,
        'avg_holding_days': avg_holding_days,
        'profit_factor': profit_factor,
        'avg_win_return': (sum(wins) / len(wins)) if wins else 0,
        'avg_loss_return': (sum(losses) / len(losses)) if losses else 0,
        'best_trade': best_trade,
        'worst_trade': worst_trade,
        'trades': trades,
    }


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _pick_entry_price(hist_df, fallback_price: float) -> float:
    if hist_df is None or hist_df.empty:
        return fallback_price
    row = hist_df.iloc[0]
    return _safe_float(row.get('open')) or _safe_float(row.get('close')) or fallback_price


def _pick_exit_price(hist_df) -> float:
    if hist_df is None or hist_df.empty:
        return 0.0
    row = hist_df.iloc[-1]
    return _safe_float(row.get('close')) or _safe_float(row.get('open'))


def run_backtest(
    strategy_code: str,
    start_date: str,
    end_date: str,
    *,
    holding_days: int = 5,
    max_positions_per_day: int = 3,
) -> Dict[str, Any]:
    """Run backtest for strategy."""
    strategy = registry.get(strategy_code)
    if not strategy:
        return {
            'success': False,
            'message': f'策略不存在: {strategy_code}'
        }

    stock_data = get_stock_data_service()
    trading_dates = stock_data.get_trading_dates(start_date, end_date)
    if len(trading_dates) < 2:
        return {
            'success': False,
            'message': '回测区间内有效交易日不足'
        }

    holding_days = max(1, int(holding_days))
    max_positions_per_day = max(1, int(max_positions_per_day))
    trades = []

    for index, trade_date in enumerate(trading_dates[:-1]):
        try:
            scan_results = strategy.scan(trade_date)
        except Exception:
            scan_results = []

        if not scan_results:
            continue

        ordered_results = sorted(
            scan_results,
            key=lambda item: (
                _safe_float(item.get('risk_score', 50)),
                -_safe_float(item.get('total_score', item.get('limit_up_score', 0))),
                -_safe_float(item.get('vol_ratio', 0))
            )
        )

        entry_date = trading_dates[index + 1]
        exit_index = min(index + holding_days, len(trading_dates) - 1)
        exit_date = trading_dates[exit_index]

        for pick in ordered_results[:max_positions_per_day]:
            code = (pick.get('code') or '').strip()
            if not code:
                continue

            name = pick.get('name', '')
            signal = pick.get('signal', '')
            fallback_price = _safe_float(pick.get('pick_price'))

            entry_hist = stock_data.get_stock_hist(code, entry_date, entry_date, adjust='qfq')
            exit_hist = stock_data.get_stock_hist(code, exit_date, exit_date, adjust='qfq')

            entry_price = _pick_entry_price(entry_hist, fallback_price)
            exit_price = _pick_exit_price(exit_hist)
            if entry_price <= 0 or exit_price <= 0:
                continue

            return_pct = (exit_price - entry_price) / entry_price
            trades.append({
                'strategy_code': strategy_code,
                'strategy_name': strategy.name,
                'signal_date': trade_date,
                'entry_date': entry_date,
                'exit_date': exit_date,
                'holding_days': exit_index - index,
                'code': code,
                'name': name,
                'signal': signal,
                'reason_tag': pick.get('reason_tag', ''),
                'note': pick.get('note', ''),
                'entry_price': round(entry_price, 4),
                'exit_price': round(exit_price, 4),
                'return_pct': round(return_pct, 4),
                'risk_score': round(_safe_float(pick.get('risk_score', 0)), 2),
                'score': round(_safe_float(pick.get('total_score', pick.get('limit_up_score', 0))), 2),
            })

    results = _build_summary(trades)

    save_backtest_result(strategy_code, start_date, end_date, results)

    return {
        'success': True,
        'results': results,
        'meta': {
            'strategy_code': strategy_code,
            'strategy_name': strategy.name,
            'start_date': start_date,
            'end_date': end_date,
            'holding_days': holding_days,
            'max_positions_per_day': max_positions_per_day,
            'trade_days': len(trading_dates)
        }
    }
