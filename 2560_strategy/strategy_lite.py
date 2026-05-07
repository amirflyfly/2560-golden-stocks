import urllib.request
import urllib.parse
import json
import datetime
import time
import os

from scripts.maintenance.legacy_sqlite_guard import refuse_production

refuse_production("strategy_lite.py")

# 配置
CONFIG = {
    "price_limit": 30.0,
    "select_count": 5,
    "output_file": "data/selection_result.json"
}

def get_stock_info(code, market):
    """从腾讯财经获取实时行情"""
    prefix = "sh" if market == "sh" else "sz"
    url = f"http://qt.gtimg.cn/q={prefix}{code}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=5)
        data = response.read().decode('gbk') # 腾讯接口返回 GBK
        # 解析格式：v_sh600000="51.070,48.780,51.080... (具体格式需查文档，这里简化处理)
        # 简化版：直接返回原始数据做简单解析
        return data
    except:
        return None

def parse_tencent_data(data, code):
    """解析腾讯数据"""
    try:
        # 示例数据: v_sh600000="51.07,48.78,51.08,51.16,50.90,51.07...
        if not data or '=' not in data:
            return None
        content = data.split('=')[1].strip('"').strip('"').split(',')
        if len(content) < 30:
            return None
        
        current_price = float(content[1]) # 现价
        open_price = float(content[2])    # 开盘
        high = float(content[3])          # 最高
        low = float(content[4])           # 最低
        vol = int(content[6])             # 成交量 (手)
        
        # 获取均线数据需要更复杂的 K 线接口，这里简化处理：
        # 由于单点接口无法直接获取 MA25，我们采用变通方案：
        # 仅基于当前价格和简单量能进行初筛，详细 MA 计算需依赖更高级接口或本地缓存
        # 为演示效果，这里模拟返回基础数据
        return {
            "code": code,
            "price": current_price,
            "vol": vol,
            "name": content[15] if len(content) > 15 else "Unknown"
        }
    except Exception as e:
        return None

def run_selection():
    print(f"🚀 [轻量版] 启动 2560 战法选股... 时间：{datetime.datetime.now()}")
    print("⚠️ 模式说明：使用腾讯/新浪免费接口，无需安装额外库。")
    print("⚠️ 限制：仅能做基础价格筛选，复杂均线计算需升级接口。")
    
    print("\n" + "="*40)
    print(f"📅 日期：{datetime.datetime.now().strftime('%Y-%m-%d')}")
    print("2560 战法精选标的:")
    print("="*40)
    print("轻量版不再生成模拟选股结果。请使用真实行情源运行完整策略。")
    print("="*40)
    
    os.makedirs('data', exist_ok=True)
    with open(CONFIG['output_file'], 'w', encoding='utf-8') as f:
        json.dump([], f, ensure_ascii=False, indent=2)
    print(f"💾 结果已保存至：{CONFIG['output_file']}")

if __name__ == "__main__":
    run_selection()
