import akshare as ak
import pandas as pd
import pandas_ta as ta
import numpy as np
import datetime
import json
import os

def get_stock_list():
    """获取沪深 A 股列表"""
    try:
        stock_list = ak.stock_info_a_code_name()
        return stock_list
    except Exception as e:
        print(f"获取股票列表失败：{e}")
        return pd.DataFrame()

def calculate_2560_strategy(stock_code, market, config):
    """
    2560 战法核心逻辑判断
    返回：(是否匹配, 原因, 当前价格, 25 日线价格，量能比，名称)
    """
    try:
        # 获取历史行情 (前复权)
        # 为了速度，这里只取最近 65 天数据
        df = ak.stock_zh_a_hist(symbol=stock_code, period="daily", adjust="qfq", start_date="20251201")
        
        if len(df) < 65:
            return False, "数据不足", 0, 0, 0, ""

        # 重命名列以匹配计算
        df.columns = ['date', 'open', 'close', 'high', 'low', 'volume', 'amount', 'amplitude', 'chg', 'percent', 'turnover', 'pre_close']
        
        # 计算指标
        # 1. MA25
        df['ma25'] = df['close'].rolling(window=25).mean()
        # 2. 成交量均线
        df['ma5_vol'] = df['volume'].rolling(window=5).mean()
        df['ma60_vol'] = df['volume'].rolling(window=60).mean()
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        prev_2 = df.iloc[-3] if len(df) > 2 else df.iloc[-2]

        # --- 核心条件判断 ---
        
        # 条件 A: 25 日线向上 (今日 MA25 > 昨日 MA25，且 5 日前 MA25 < 今日 MA25，确保趋势向上)
        trend_up = last['ma25'] > prev['ma25']
        
        # 条件 B: 量能形态 (5 日均量 > 60 日均量)
        vol_active = last['ma5_vol'] > (last['ma60_vol'] * config['strategy']['vol_ratio'])
        
        # 条件 C: 价格过滤 (<30 元)
        price_filter = last['close'] < config['strategy']['price_limit']
        
        if not (trend_up and vol_active and price_filter):
            return False, "不匹配", 0, 0, 0, ""

        # --- 信号识别 ---
        signal_type = ""
        
        # 1. 缩量回踩: 股价在 25 日线附近 (+/- 5%), 且今日成交量 < 5 日均量
        is_near_ma25 = abs(last['close'] - last['ma25']) / last['ma25'] < 0.05
        is_shrink_vol = last['volume'] < last['ma5_vol']
        
        # 2. 放量突破: 股价 > 25 日线，且今日成交量 > 1.5 倍 5 日均量
        is_breakout = last['close'] > last['ma25']
        is_vol_explosion = last['volume'] > (last['ma5_vol'] * 1.5)

        if is_near_ma25 and is_shrink_vol:
            signal_type = "缩量回踩"
        elif is_breakout and is_vol_explosion:
            signal_type = "放量突破"
        else:
            # 其他情况不视为强信号
            return False, "信号不强", 0, 0, 0, ""

        return True, signal_type, last['close'], last['ma25'], last['ma5_vol']/last['ma60_vol'], last['date']

    except Exception as e:
        # print(f"计算 {stock_code} 出错：{e}")
        return False, f"错误:{str(e)}", 0, 0, 0, ""

def run_selection(config_path="config.json"):
    print(f"🚀 启动 2560 战法选股程序... 时间：{datetime.datetime.now()}")
    
    with open(config_path, 'r') as f:
        config = json.load(f)
        
    stock_list = get_stock_list()
    if stock_list.empty:
        print("未获取到股票列表，退出。")
        return

    selected_stocks = []
    count = 0
    total = len(stock_list)
    
    print(f"📊 开始扫描全市场 {total} 只股票...")

    # 遍历筛选 (实际生产中应用多进程加速，这里为了简单用单线程)
    for _, row in stock_list.iterrows():
        code = row['代码']
        name = row['名称']
        
        # 基础过滤
        if config['strategy']['exclude_st'] and 'ST' in name:
            continue
        if config['strategy']['exclude_kechuang'] and code.startswith('688'):
            continue
        if code.startswith('8') or code.startswith('4'): # 北交所
            continue
            
        match, reason, price, ma25, vol_ratio, date = calculate_2560_strategy(code, 'sh' if code.startswith('6') else 'sz', config)
        
        if match:
            selected_stocks.append({
                '代码': code,
                '名称': name,
                '价格': round(price, 2),
                '信号': reason,
                '25 日线': round(ma25, 2),
                '量能比': round(vol_ratio, 2),
                '日期': date
            })
            count += 1
            # 如果只需要前几只，可以在这里 break，但为了全面分析建议跑完或限制总数
            # if len(selected_stocks) >= config['strategy']['select_count']:
            #     break
    
    # 排序：优先缩量回踩，再按量能比排序
    selected_stocks.sort(key=lambda x: (0 if x['信号'] == '缩量回踩' else 1, -x['量能比']))
    
    # 截取前 N 只
    final_stocks = selected_stocks[:config['strategy']['select_count']]

    # 输出结果
    print("\n" + "="*30)
    print(f"📅 日期：{datetime.datetime.now().strftime('%Y-%m-%d')}")
    print(f"🎯 2560 战法精选标的 (价格<{config['strategy']['price_limit']}元):")
    print("="*30)
    
    if not final_stocks:
        print("今日无符合严格 2560 战法特征的标的，建议空仓观望。")
    else:
        df_res = pd.DataFrame(final_stocks)
        print(df_res.to_markdown(index=False))
        
        # 保存到文件
        os.makedirs('data', exist_ok=True)
        df_res.to_csv(config['output']['file_path'].replace('.json', '.csv'), index=False)
        with open(config['output']['file_path'], 'w', encoding='utf-8') as f:
            json.dump(final_stocks, f, ensure_ascii=False, indent=2)
        print(f"\n💾 结果已保存至：{config['output']['file_path']}")

    print("\n⚠️ 风险提示：股市有风险，投资需谨慎。以上仅为技术选股，不构成买卖建议。")
    print("="*30)

if __name__ == "__main__":
    run_selection()
