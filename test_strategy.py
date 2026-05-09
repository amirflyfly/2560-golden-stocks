#!/usr/bin/env python3
"""
测试2560策略的逻辑
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.strategies.strategy_2560 import Strategy2560

# 创建策略实例
strategy = Strategy2560()

# 测试scan方法
print("测试2560策略...")
try:
    # 测试最近的日期
    result = strategy.scan('2026-04-05')
    print(f"扫描结果数量: {len(result)}")
    
    if result:
        print("选中的股票:")
        for stock in result:
            print(f"  {stock['code']} - {stock['name']}: {stock['signal']}, 价格: {stock['pick_price']:.2f}")
    else:
        print("未选中股票")
        
    # 打印调试信息
    print("\n策略配置:")
    print(strategy.config)
    
except Exception as e:
    print(f"测试失败: {e}")
    import traceback
    traceback.print_exc()
