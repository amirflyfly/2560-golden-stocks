import akshare as ak
import pandas as pd
import numpy as np
import datetime as dt
import json
import os
import sys


def is_trading_day_today() -> bool:
    """尽力判断是否为A股交易日（简单冗余判断，失败默认 True 以不阻塞人工触发）。"""
    try:
        # 东方财富交易日历（若可用）
        cal = ak.tool_trade_date_hist_sina()
        if isinstance(cal, pd.DataFrame) and not cal.empty:
            today = dt.datetime.now().strftime('%Y-%m-%d')
            # 该接口一般返回 date 列
            date_col = 'date' if 'date' in cal.columns else (cal.columns[0] if len(cal.columns) > 0 else None)
            if date_col:
                return today in set(cal[date_col].astype(str).tolist())
    except Exception:
        pass

    # 退化：周一至周五认为交易日
    return dt.datetime.now().weekday() < 5


def get_stock_list():
    """获取沪深A股列表，带多源降级：
    1) ak.stock_info_a_code_name
    2) ak.stock_zh_a_spot_em
    3) ak.stock_info_sh_name_code + ak.stock_info_sz_name_code 合并
    4) 兜底少量样本
    """
    # 1. 交易所源
    try:
        df = ak.stock_info_a_code_name()
        if isinstance(df, pd.DataFrame) and not df.empty:
            return df
    except Exception as e:
        print(f"stock_info_a_code_name 失败: {e}")

    # 2. 东方财富快照
    try:
        df2 = ak.stock_zh_a_spot_em()
        if isinstance(df2, pd.DataFrame) and not df2.empty:
            return df2[[c for c in df2.columns if c in ('代码','名称','code','name')]]
    except Exception as e:
        print(f"stock_zh_a_spot_em 失败: {e}")

    # 3. 沪深单独合并
    try:
        sh = ak.stock_info_sh_name_code()
    except Exception as e:
        print(f"stock_info_sh_name_code 失败: {e}")
        sh = pd.DataFrame()
    try:
        sz = ak.stock_info_sz_name_code()
    except Exception as e:
        print(f"stock_info_sz_name_code 失败: {e}")
        sz = pd.DataFrame()

    if isinstance(sh, pd.DataFrame) and not sh.empty:
        sh = sh.rename(columns={'证券代码':'代码','证券简称':'名称'})
    if isinstance(sz, pd.DataFrame) and not sz.empty:
        sz = sz.rename(columns={'A股代码':'代码','A股简称':'名称'})

    merged = pd.concat([d for d in [sh, sz] if isinstance(d, pd.DataFrame)], ignore_index=True)
    if not merged.empty and '代码' in merged.columns and '名称' in merged.columns:
        merged = merged[['代码','名称']].dropna().drop_duplicates()
        return merged

    # 4. 兜底少量样本
    print("使用兜底样本代码集")
    return pd.DataFrame({'代码':['600000','600519','000001','000002','002594'], '名称':['浦发银行','贵州茅台','平安银行','万科A','比亚迪']})


def _rename_hist_cols(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    mapping_cn = {
        '日期': 'date',
        '开盘': 'open',
        '收盘': 'close',
        '最高': 'high',
        '最低': 'low',
        '成交量': 'volume',
        '成交额': 'amount',
        '振幅': 'amplitude',
        '涨跌幅': 'pct_chg',
        '涨跌额': 'chg_amt',
        '换手率': 'turnover',
    }
    mapping_en_passthrough = {
        'date': 'date', 'open': 'open', 'close': 'close', 'high': 'high', 'low': 'low',
        'volume': 'volume', 'amount': 'amount', 'amplitude': 'amplitude',
        'pct_chg': 'pct_chg', 'chg_amt': 'chg_amt', 'turnover': 'turnover'
    }
    cols = list(df.columns)
    rename_map = {}
    for c in cols:
        if c in mapping_en_passthrough:
            rename_map[c] = mapping_en_passthrough[c]
        elif c in mapping_cn:
            rename_map[c] = mapping_cn[c]
        else:
            rename_map[c] = c
    return df.rename(columns=rename_map)


essential_cols = ['date', 'open', 'close', 'high', 'low', 'volume']


def calculate_2560_strategy(stock_code: str, market: str, config: dict):
    try:
        start_date = (dt.datetime.now() - dt.timedelta(days=180)).strftime('%Y%m%d')
        df = ak.stock_zh_a_hist(symbol=stock_code, period="daily", adjust="qfq", start_date=start_date)
        if df is None or df.empty:
            return False, "无数据", 0, 0, 0, ""

        df = _rename_hist_cols(df)
        for col in essential_cols:
            if col not in df.columns:
                return False, "字段缺失", 0, 0, 0, ""

        df['ma25'] = df['close'].rolling(window=25, min_periods=25).mean()
        df['ma5_vol'] = df['volume'].rolling(window=5, min_periods=5).mean()
        df['ma60_vol'] = df['volume'].rolling(window=60, min_periods=60).mean()

        if len(df) < 65 or pd.isna(df['ma25'].iloc[-1]):
            return False, "数据不足", 0, 0, 0, ""

        last = df.iloc[-1]
        prev = df.iloc[-2]
        trend_up = last['ma25'] > prev['ma25']
        vol_active = (last['ma5_vol'] > (last['ma60_vol'] * float(config['strategy'].get('vol_ratio', 1.0)))) if last['ma60_vol'] and not np.isnan(last['ma60_vol']) else False
        price_filter = last['close'] < float(config['strategy'].get('price_limit', 30.0))

        if not (trend_up and vol_active and price_filter):
            return False, "不匹配", 0, 0, 0, ""

        is_near_ma25 = abs(last['close'] - last['ma25']) / last['ma25'] < 0.05
        is_shrink_vol = last['volume'] < last['ma5_vol'] if not np.isnan(last['ma5_vol']) else False
        is_breakout = last['close'] > last['ma25']
        is_vol_explosion = last['volume'] > (last['ma5_vol'] * 1.5) if not np.isnan(last['ma5_vol']) else False

        if is_near_ma25 and is_shrink_vol:
            signal_type = "缩量回踩"
        elif is_breakout and is_vol_explosion:
            signal_type = "放量突破"
        else:
            return False, "信号不强", 0, 0, 0, ""

        vol_ratio = float(last['ma5_vol'] / last['ma60_vol']) if last['ma60_vol'] and not np.isnan(last['ma60_vol']) else 0
        date_str = str(last['date'])
        return True, signal_type, float(last['close']), float(last['ma25']), round(vol_ratio, 2), date_str

    except Exception as e:
        return False, f"错误:{str(e)}", 0, 0, 0, ""


def run_selection(config_path: str = "config.json"):
    print(f"🚀 启动 2560 战法选股程序... 时间：{dt.datetime.now()}")

    # 交易日判断
    if not is_trading_day_today():
        print("⛔ 非交易日，跳过运行。")
        os.makedirs('data', exist_ok=True)
        with open('data/daily_selection.json', 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        return

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    stock_list = get_stock_list()
    if stock_list.empty:
        print("未获取到股票列表，退出。")
        return

    code_col = '代码' if '代码' in stock_list.columns else ('code' if 'code' in stock_list.columns else None)
    name_col = '名称' if '名称' in stock_list.columns else ('name' if 'name' in stock_list.columns else None)
    if not code_col or not name_col:
        print("股票列表字段异常，退出。")
        return

    try:
        scan_limit = int(os.environ.get('SCAN_LIMIT', '500'))
    except Exception:
        scan_limit = 500

    total = len(stock_list)
    if scan_limit > 0:
        stock_list = stock_list.head(scan_limit)
    print(f"📊 开始扫描 {len(stock_list)}/{total} 只股票...")

    selected_stocks = []

    for _, row in stock_list.iterrows():
        code = str(row[code_col])
        name = str(row[name_col])

        if config['strategy'].get('exclude_st', True) and ('ST' in name.upper()):
            continue
        if config['strategy'].get('exclude_kechuang', True) and code.startswith('688'):
            continue
        if code.startswith('8') or code.startswith('4'):
            continue

        match, reason, price, ma25, vol_ratio, date = calculate_2560_strategy(code, 'sh' if code.startswith('6') else 'sz', config)
        if match:
            selected_stocks.append({
                '代码': code,
                '名称': name,
                '价格': round(price, 2),
                '信号': reason,
                '25日线': round(ma25, 2),
                '量能比': round(vol_ratio, 2),
                '日期': date
            })

    def _signal_rank(sig: str) -> int:
        return 0 if sig == '缩量回踩' else 1

    selected_stocks.sort(key=lambda x: (_signal_rank(x['信号']), -x['量能比']))
    final_n = int(config['strategy'].get('select_count', 5))
    final_stocks = selected_stocks[:final_n]

    print("\n" + "=" * 30)
    print(f"📅 日期：{dt.datetime.now().strftime('%Y-%m-%d')}")
    print(f"🎯 2560 战法精选标的 (价格<{config['strategy'].get('price_limit', 30)}元):")
    print("=" * 30)

    os.makedirs('data', exist_ok=True)
    out_json = config['output'].get('file_path', 'data/daily_selection.json')
    out_csv = out_json.replace('.json', '.csv')

    if not final_stocks:
        print("今日无符合严格 2560 战法特征的标的，建议空仓观望。")
        with open(out_json, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    else:
        df_res = pd.DataFrame(final_stocks)
        print(df_res.to_string(index=False))
        df_res.to_csv(out_csv, index=False)
        with open(out_json, 'w', encoding='utf-8') as f:
            json.dump(final_stocks, f, ensure_ascii=False, indent=2)
        print(f"\n💾 结果已保存至：{out_json}")

    print("\n⚠️ 风险提示：股市有风险，投资需谨慎。以上仅为技术选股，不构成买卖建议。")
    print("=" * 30)


if __name__ == "__main__":
    run_selection()
