#!/usr/bin/env python3
"""
测试股票数据服务
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.services.stock_data_service import get_stock_data_service

# 获取股票数据服务实例
stock_data = get_stock_data_service()

print("测试股票数据服务...")

# 测试1: 获取股票列表
print("\n1. 测试获取股票列表:")
try:
    stock_list = stock_data.get_stock_list()
    print(f"成功获取股票列表，共 {len(stock_list)} 只股票")
    print("前5只股票:")
    print(stock_list.head())
except Exception as e:
    print(f"获取股票列表失败: {e}")

# 测试2: 获取历史数据
print("\n2. 测试获取历史数据:")
try:
    df = stock_data.get_stock_hist(
        symbol="600519",
        start_date="2026-01-01",
        end_date="2026-04-05",
        adjust="qfq"
    )
    print(f"成功获取历史数据，共 {len(df)} 条记录")
    print("数据列:", list(df.columns))
    print("最后5条记录:")
    print(df.tail())
except Exception as e:
    print(f"获取历史数据失败: {e}")

# 测试3: 获取交易日期
print("\n3. 测试获取交易日期:")
try:
    dates = stock_data.get_trading_dates(
        start_date="2026-01-01",
        end_date="2026-01-31"
    )
    print(f"成功获取交易日期，共 {len(dates)} 个交易日")
    print("交易日期:", dates)
except Exception as e:
    print(f"获取交易日期失败: {e}")

# 测试4: 使用模拟数据源
print("\n4. 测试使用模拟数据源:")
try:
    stock_data.set_default_source("mock")
    mock_stock_list = stock_data.get_stock_list()
    print(f"成功获取模拟股票列表，共 {len(mock_stock_list)} 只股票")
    print(mock_stock_list)
    
    mock_df = stock_data.get_stock_hist(
        symbol="600519",
        start_date="2026-01-01",
        end_date="2026-01-10"
    )
    print(f"成功获取模拟历史数据，共 {len(mock_df)} 条记录")
    print(mock_df)
except Exception as e:
    print(f"使用模拟数据源失败: {e}")

# 测试5: 清除缓存
print("\n5. 测试清除缓存:")
try:
    stock_data.clear_cache()
    print("缓存清除成功")
except Exception as e:
    print(f"清除缓存失败: {e}")

print("\n测试完成!")
