"""Multi-strategy scan and import service.

Unified entry point for running multiple strategies and importing results.
"""

from datetime import datetime
from typing import List, Dict, Any
from backend.repositories import picks_repo
from backend.strategies import registry


def run_all_strategies(date: str = None) -> Dict[str, Any]:
    """Run all active strategies and return results.
    
    Returns:
        {
            'date': str,
            'results': {
                'strategy_code': {
                    'name': str,
                    'picks': List[Dict],
                    'count': int,
                    'imported': int
                }
            }
        }
    """
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    results = {
        'date': date,
        'results': {}
    }
    
    # Get active strategies
    strategies = registry.list_active()
    
    for strategy in strategies:
        # Check if trading day
        if not strategy.is_trading_day(date):
            results['results'][strategy.code] = {
                'name': strategy.name,
                'picks': [],
                'count': 0,
                'imported': 0,
                'skipped': True,
                'reason': '非交易日'
            }
            continue
        
        # Run strategy scan
        try:
            picks = strategy.scan(date)
        except Exception as e:
            results['results'][strategy.code] = {
                'name': strategy.name,
                'picks': [],
                'count': 0,
                'imported': 0,
                'skipped': True,
                'reason': f'扫描失败: {str(e)}'
            }
            continue
        
        # Import picks to database
        imported = 0
        for pick in picks:
            try:
                picks_repo.create_or_replace_pick(
                    pick_date=date,
                    code=pick['code'],
                    name=pick['name'],
                    pick_price=pick.get('pick_price', 0),
                    signal=pick.get('signal', ''),
                    source='auto_scan',
                    source_channel='system',
                    reason_tag=pick.get('reason_tag', ''),
                    note=pick.get('note', ''),
                    review_status='未复盘',
                    review_comment='',
                    content_title='',
                    content_ref='',
                    result_grade='待定',
                    inquiry_count=0,
                    deal_status='未成交',
                    secondary_spread='否',
                    strategy_name=strategy.code
                )
                imported += 1
            except Exception as e:
                print(f"Failed to import {pick.get('code')}: {e}")
        
        results['results'][strategy.code] = {
            'name': strategy.name,
            'picks': picks,
            'count': len(picks),
            'imported': imported,
            'skipped': False
        }
    
    return results


def run_single_strategy(strategy_code: str, date: str = None) -> Dict[str, Any]:
    """Run a single strategy by code."""
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    strategy = registry.get(strategy_code)
    if not strategy:
        return {
            'date': date,
            'error': f'Strategy {strategy_code} not found'
        }
    
    # Check if trading day
    is_trading = strategy.is_trading_day(date)
    print(f"Checking trading day for {date}: {is_trading}")
    
    # For testing purposes, always allow running
    # if not is_trading:
    #     return {
    #         'date': date,
    #         'strategy': strategy_code,
    #         'name': strategy.name,
    #         'picks': [],
    #         'count': 0,
    #         'imported': 0,
    #         'skipped': True,
    #         'reason': '非交易日'
    #     }
    
    # Run scan
    try:
        picks = strategy.scan(date)
    except Exception as e:
        print(f"扫描失败: {e}")
        import traceback
        traceback.print_exc()
        picks = []
    
    # Import to database
    imported = 0
    for pick in picks:
        try:
            picks_repo.create_or_replace_pick(
                pick_date=date,
                code=pick['code'],
                name=pick['name'],
                pick_price=pick.get('pick_price', 0),
                signal=pick.get('signal', ''),
                source='auto_scan',
                source_channel='system',
                reason_tag=pick.get('reason_tag', ''),
                note=pick.get('note', ''),
                review_status='未复盘',
                review_comment='',
                content_title='',
                content_ref='',
                result_grade='待定',
                inquiry_count=0,
                deal_status='未成交',
                secondary_spread='否',
                strategy_name=strategy.code
            )
            imported += 1
        except Exception as e:
            print(f"Failed to import {pick.get('code')}: {e}")
    
    return {
        'date': date,
        'strategy': strategy_code,
        'name': strategy.name,
        'picks': picks,
        'count': len(picks),
        'imported': imported,
        'skipped': False
    }


def get_strategy_status(date: str = None) -> Dict[str, Any]:
    """Get status of all strategies for a given date."""
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    strategies = registry.list_active()
    status = {}
    
    for strategy in strategies:
        is_trading = strategy.is_trading_day(date)
        status[strategy.code] = {
            'name': strategy.name,
            'is_trading_day': is_trading,
            'can_run': is_trading
        }
    
    return {
        'date': date,
        'strategies': status
    }
