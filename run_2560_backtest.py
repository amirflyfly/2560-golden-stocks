#!/usr/bin/env python3
"""
运行2026年1月1日到今天的2560策略，并将结果添加到股票池中
"""

import sys
import os

# 添加Werkzeug补丁
from scripts.maintenance.legacy_sqlite_guard import refuse_production

refuse_production("run_2560_backtest.py")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import werkzeug_patch
except ImportError:
    # 如果补丁文件不存在，创建一个
    patch_content = '''
import werkzeug.urls

# 为Werkzeug 3.1.8添加url_quote函数
if not hasattr(werkzeug.urls, 'url_quote'):
    from urllib.parse import quote
    werkzeug.urls.url_quote = quote
'''
    with open('werkzeug_patch.py', 'w') as f:
        f.write(patch_content)
    import werkzeug_patch

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from backend.services.multi_strategy_service import run_single_strategy
from backend.services.strategy_pool_service import add_scan_result_to_pool

# 导入策略模块，确保策略被注册
from backend.strategies import strategy_2560


def get_trading_dates(start_date, end_date):
    """获取交易日历"""
    try:
        import akshare as ak
        cal = ak.tool_trade_date_hist_sina()
        trade_dates = cal[cal['trade_date'] >= start_date]['trade_date'].tolist()
        trade_dates = [d for d in trade_dates if d <= end_date]
        return trade_dates
    except Exception as e:
        print(f"获取交易日历失败: {e}")
        # 简化处理：使用所有工作日
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        trade_dates = []
        current = start
        while current <= end:
            if current.weekday() < 5:  # 周一到周五
                trade_dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
        return trade_dates


def run_2560_strategy(start_date, end_date):
    """运行2560策略"""
    print(f"🚀 开始运行2026年1月1日到今天的2560策略")
    print(f"开始日期: {start_date}")
    print(f"结束日期: {end_date}")
    
    # 获取交易日历
    trade_dates = get_trading_dates(start_date, end_date)
    print(f"共 {len(trade_dates)} 个交易日")
    
    total_added = 0
    total_processed = 0
    
    for i, target_date in enumerate(trade_dates):
        print(f"\n📅 处理日期: {target_date} ({i+1}/{len(trade_dates)})")
        
        try:
            # 运行2560策略
            result = run_single_strategy('2560', target_date)
            
            # 打印调试信息
            print(f"  策略返回结果: {result}")
            
            if result and 'picks' in result:
                picks = result['picks']
                print(f"  选出 {len(picks)} 只股票")
                
                # 为每个股票添加pick_date字段
                for pick in picks:
                    pick['pick_date'] = target_date
                
                # 添加到股票池
                if picks:
                    add_result = add_scan_result_to_pool('2560', picks)
                    print(f"  成功添加 {add_result['added_count']} 只股票到股票池")
                    total_added += add_result['added_count']
            else:
                print("  未选出股票")
            
            total_processed += 1
            
        except Exception as e:
            print(f"  处理失败: {e}")
    
    print(f"\n✅ 运行完成")
    print(f"处理了 {total_processed} 个交易日")
    print(f"成功添加 {total_added} 只股票到2560策略股票池")


if __name__ == '__main__':
    # 只处理最近的5个交易日
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
    run_2560_strategy(start_date, end_date)
