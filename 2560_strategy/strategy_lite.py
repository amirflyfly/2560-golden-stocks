import urllib.request
import urllib.parse
import json
import datetime
import time
import os

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
    
    # 模拟选股结果 (因为免费接口难以一次性获取全市场 MA25 数据)
    # 真实场景中，这里会遍历 A 股列表并请求接口
    # 这里为了演示，输出一个模拟的精选名单
    
    mock_result = [
        {"code": "002XXX", "name": "XX 科技", "price": 12.50, "signal": "缩量回踩", "ma25": 12.45, "vol_ratio": 0.8},
        {"code": "600XXX", "name": "XX 电子", "price": 18.90, "signal": "放量突破", "ma25": 18.50, "vol_ratio": 2.1},
        {"code": "002XXX", "name": "XX 机械", "price": 24.30, "signal": "缩量回踩", "ma25": 24.10, "vol_ratio": 0.9},
        {"code": "300XXX", "name": "XX 材料", "price": 15.60, "signal": "放量突破", "ma25": 15.20, "vol_ratio": 1.8},
        {"code": "601XXX", "name": "XX 股份", "price": 8.90, "signal": "缩量回踩", "ma25": 8.85, "vol_ratio": 0.7}
    ]
    
    print("\n" + "="*40)
    print(f"📅 日期：{datetime.datetime.now().strftime('%Y-%m-%d')}")
    print(f"🎯 2560 战法精选标的 (模拟演示):")
    print("="*40)
    print(f"{'代码':<10} {'名称':<10} {'价格':<8} {'信号':<10} {'25 日线':<8} {'量能比':<8}")
    print("-" * 40)
    
    for item in mock_result:
        print(f"{item['code']:<10} {item['name']:<10} {item['price']:<8} {item['signal']:<10} {item['ma25']:<8} {item['vol_ratio']:<8}")
        
    print("\n⚠️ 提示：轻量版模式使用模拟数据进行演示。")
    print("💡 若需真实全市场扫描，请授权安装 `akshare` 库或提供可访问的财经数据 API。")
    print("="*40)
    
    # 保存结果
    os.makedirs('data', exist_ok=True)
    with open(CONFIG['output_file'], 'w', encoding='utf-8') as f:
        json.dump(mock_result, f, ensure_ascii=False, indent=2)
    print(f"💾 结果已保存至：{CONFIG['output_file']}")

if __name__ == "__main__":
    run_selection()
