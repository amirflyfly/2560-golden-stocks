"""首板涨停第二天上车策略 - First Limit-Up Next Day Entry Strategy.

================================================================================
策略核心逻辑深度解析
================================================================================

一、为什么首板涨停第二天能上车？

1. 【筹码结构好】
   - 首板意味着前期没有获利盘抛压
   - 涨停价成为新的成本锚点，第二天高开显示资金愿意接力
   - 散户在首板当天很难买入，第二天才有上车机会

2. 【资金意图明确】
   - 首板封死说明主力资金强势
   - 第二天高开说明主力不想给低位筹码，志在高远
   - 竞价放量说明资金抢筹意愿强烈

3. 【市场情绪传导】
   - 首板涨停引发市场关注
   - 晚上复盘被各路资金发现
   - 第二天竞价形成抢筹效应

二、首板形态分析（分时图特征）

1. 【涨停时间】
   - 早盘涨停（10点前）：最强，主力意图坚决
   - 上午涨停（10-11:30）：较强，有准备但略显犹豫
   - 下午涨停（13:00-14:00）：一般，跟风或偷袭
   - 尾盘涨停（14:00后）：较弱，封单不坚决

2. 【封板质量】
   - 一字板：最强，但买不到，第二天风险大
   - 秒板：很强，开盘即涨停，显示资金饥渴
   - 稳步封板：较好，有节奏地拉升后封死
   - 反复开板：较差，抛压大或主力实力不足
   - 尾盘偷袭：最差，非主力行为

3. 【量能特征】
   - 缩量涨停：最好，筹码锁定良好
   - 温和放量：较好，有换手但不过分
   - 爆量涨停：一般，分歧大，需要第二天确认
   - 天量涨停：较差，可能是出货

4. 【封单金额】
   - 封单金额大：显示资金实力
   - 封单坚决：不开板，显示决心
   - 撤单少：不是诱多

三、除首板形态外的关键因素

1. 【板块效应】⭐⭐⭐⭐⭐
   - 所属板块当天有多只涨停
   - 板块龙头效应明显
   - 第二天板块继续强势
   - 同板块有连板股

2. 【市场情绪】⭐⭐⭐⭐
   - 当天涨停家数>50家：情绪好
   - 当天跌停家数<5家：情绪稳定
   - 连板股数量多：接力意愿强
   - 高标股表现：空间板是否断板

3. 【龙虎榜数据】⭐⭐⭐⭐
   - 知名游资介入：章盟主、赵老哥、作手新一
   - 机构买入：有基本面支撑
   - 买入金额均匀：不是独食
   - 无大金额卖出：无主力出货

4. 【个股基本面】⭐⭐⭐
   - 有热点题材概念
   - 近期有利好消息
   - 流通市值适中（50-200亿最佳）
   - 股价位置不高（非高位）

5. 【大盘环境】⭐⭐⭐
   - 大盘不暴跌
   - 成交量不萎缩
   - 北向资金流向
   - 外围市场表现

四、第二天上车条件（按重要性排序）

1. 【竞价高开】2%-5%最佳
   - <2%：太弱，可能低开低走
   - 2%-5%：强势但不过分，有空间
   - >5%：风险大，可能高开低走

2. 【竞价量能】
   - 竞价成交量>昨日5%
   - 量比>2
   - 竞价金额>1000万

3. 【竞价走势】
   - 竞价最后一分钟向上：抢筹
   - 竞价未出现大幅回落：抛压小
   - 竞价未出现天地板：情绪稳定

4. 【板块竞价】
   - 同板块有高开股
   - 板块龙头继续强势
   - 无大面积低开

五、风险控制

1. 【绝不买入的情况】
   - 竞价高开>7%（风险收益比差）
   - 竞价量能<昨日3%（无人关注）
   - 大盘暴跌>1.5%
   - 板块龙头跌停
   - 首板反复开板>3次

2. 【止损条件】
   - 买入后跌破首板涨停价
   - 当天收盘跌停
   - 第二天低开低走不修复

================================================================================
"""

from typing import List, Dict, Any, Optional, Tuple
from backend.strategies import BaseStrategy, register_strategy
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os


@register_strategy
class StrategyFirstLimitUp(BaseStrategy):
    """首板涨停第二天上车策略 - 深度优化版.

    核心逻辑:
    1. 首板识别：当日涨停，且前5个交易日未涨停
    2. 首板质量评分：涨停时间、封板质量、量能、封单
    3. 板块效应：所属板块强度、同板块涨停数
    4. 市场情绪：当日涨停家数、连板股数量
    5. 第二天上车：竞价高开、量能、板块联动

    评分维度:
    - 首板形态分 (40分): 涨停时间、封板质量、量能
    - 板块效应分 (25分): 板块涨停数、板块持续性
    - 市场情绪分 (20分): 市场涨跌家数、连板股数量
    - 资金实力分 (15分): 封单金额、龙虎榜数据
    """

    def __init__(self):
        super().__init__()
        self.config = self._load_config()
        self.essential_cols = ['date', 'open', 'close', 'high', 'low', 'volume', 'pct_chg', 'turnover']
        self.market_data_cache = {}  # 缓存市场数据

    def _load_config(self) -> dict:
        """加载策略配置."""
        config_path = "config.json"
        default_config = {
            'strategy': {
                # 基础筛选
                'price_limit': 100.0,
                'exclude_st': True,
                'exclude_kechuang': True,
                'select_count': 10,
                'scan_limit': 500,
                'min_circulating_market_cap': 30,  # 最小流通市值(亿)
                'max_circulating_market_cap': 300,  # 最大流通市值(亿)

                # 首板条件
                'limit_up_threshold': 9.9,
                'no_limit_up_days': 5,
                'min_turnover': 3.0,  # 最小换手率
                'max_turnover': 35.0,  # 最大换手率
                'min_limit_amount': 50000000,  # 最小封单金额(5000万)

                # 涨停时间权重
                'early_limit_bonus': 15,  # 早盘涨停加分
                'morning_limit_bonus': 10,  # 上午涨停加分
                'afternoon_limit_bonus': 0,  # 下午涨停加分
                'late_limit_penalty': -10,  # 尾盘涨停扣分

                # 封板质量
                'one_word_bonus': 20,  # 一字板加分
                'quick_limit_bonus': 15,  # 秒板加分
                'steady_limit_bonus': 10,  # 稳步封板加分
                'reopen_penalty_per_time': -5,  # 每次开板扣分

                # 板块效应
                'sector_limit_up_threshold': 3,  # 板块最少涨停数
                'sector_leader_bonus': 15,  # 板块龙头加分
                'sector_strong_bonus': 10,  # 板块强势加分

                # 市场情绪
                'market_good_limit_count': 50,  # 情绪好：涨停家数>
                'market_bad_limit_down_count': 10,  # 情绪差：跌停家数>
                'high_board_intact_bonus': 10,  # 高标完好加分

                # 第二天上车条件
                'open_high_min': 2.0,
                'open_high_max': 6.0,
                'min_volume_ratio': 0.05,  # 竞价量能/昨日成交量
                'min_quantity_ratio': 2.0,  # 最小量比
                'min_auction_amount': 5000000,  # 最小竞价金额(500万)

                # 风险控制
                'min_total_score': 60,  # 最低综合评分
                'max_risk_score': 40,  # 最大风险评分
                'market_drop_threshold': -1.5,
            },
            'output': {
                'file_path': 'data/first_limit_up_selection.json'
            }
        }

        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    for key, value in default_config.items():
                        if key not in loaded_config:
                            loaded_config[key] = value
                        elif isinstance(value, dict):
                            for sub_key, sub_value in value.items():
                                if sub_key not in loaded_config[key]:
                                    loaded_config[key][sub_key] = sub_value
                    return loaded_config
            except Exception as e:
                print(f"加载配置失败: {e}, 使用默认配置")
                return default_config
        return default_config

    def get_code(self) -> str:
        return 'FIRST_LIMIT_UP'

    def get_name(self) -> str:
        return '首板涨停次日上车'

    def get_description(self) -> str:
        return '首板涨停后，综合评估板块效应、市场情绪、资金实力，第二天竞价上车'

    def get_category(self) -> str:
        return '短线策略'

    def get_parameters(self) -> Dict[str, Any]:
        """返回策略可调参数."""
        return {
            'price_limit': {
                'name': '价格上限',
                'type': 'float',
                'default': 100.0,
                'min': 10.0,
                'max': 1000.0,
                'description': '选股价格上限'
            },
            'select_count': {
                'name': '选股数量',
                'type': 'int',
                'default': 10,
                'min': 1,
                'max': 30,
                'description': '最终选出的股票数量'
            },
            'min_turnover': {
                'name': '最小换手率',
                'type': 'float',
                'default': 3.0,
                'min': 1.0,
                'max': 20.0,
                'description': '首板最小换手率(%)'
            },
            'max_turnover': {
                'name': '最大换手率',
                'type': 'float',
                'default': 35.0,
                'min': 10.0,
                'max': 50.0,
                'description': '首板最大换手率(%)'
            },
            'sector_limit_up_threshold': {
                'name': '板块涨停阈值',
                'type': 'int',
                'default': 3,
                'min': 1,
                'max': 10,
                'description': '板块最少涨停家数'
            },
            'open_high_min': {
                'name': '最小高开幅度',
                'type': 'float',
                'default': 2.0,
                'min': 0.0,
                'max': 5.0,
                'description': '第二天最小高开幅度(%)'
            },
            'open_high_max': {
                'name': '最大高开幅度',
                'type': 'float',
                'default': 6.0,
                'min': 3.0,
                'max': 15.0,
                'description': '第二天最大高开幅度(%)'
            },
            'min_total_score': {
                'name': '最低综合评分',
                'type': 'int',
                'default': 60,
                'min': 40,
                'max': 80,
                'description': '入选最低综合评分'
            }
        }

    def _rename_hist_cols(self, df: pd.DataFrame) -> pd.DataFrame:
        """重命名历史数据列."""
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

        cols = list(df.columns)
        rename_map = {}
        for c in cols:
            if c in mapping_cn:
                rename_map[c] = mapping_cn[c]
            else:
                rename_map[c] = c
        return df.rename(columns=rename_map)

    def _get_market_type(self, code: str) -> str:
        """判断股票所属市场."""
        if code.startswith('6'):
            return 'sh'
        elif code.startswith('0') or code.startswith('3'):
            return 'sz'
        elif code.startswith('8') or code.startswith('4'):
            return 'bj'
        return 'sz'

    def _is_limit_up(self, pct_chg: float, market: str = 'sh') -> bool:
        """判断是否为涨停."""
        if market in ['cy', 'kc']:
            return pct_chg >= 19.9
        return pct_chg >= 9.9

    def _check_no_recent_limit_up(self, df: pd.DataFrame, current_idx: int, days: int = 5, market: str = 'sh') -> bool:
        """检查前N天是否没有涨停."""
        if current_idx < days:
            return False

        for i in range(current_idx - days, current_idx):
            if i < 0:
                continue
            pct_chg = float(df.iloc[i].get('pct_chg', 0))
            if self._is_limit_up(pct_chg, market):
                return False
        return True

    def _get_market_sentiment(self, date: str = None) -> Dict[str, Any]:
        """获取市场情绪数据."""
        try:
            # 获取当日涨停跌停数据
            if date:
                zt_df = ak.stock_zt_pool_em(date=date)
                dt_df = ak.stock_zt_pool_dtgc_em(date=date)
            else:
                today = datetime.now().strftime('%Y%m%d')
                zt_df = ak.stock_zt_pool_em(date=today)
                dt_df = ak.stock_zt_pool_dtgc_em(date=today)

            limit_up_count = len(zt_df) if zt_df is not None else 0
            limit_down_count = len(dt_df) if dt_df is not None else 0

            # 计算情绪分数
            sentiment_score = 50
            if limit_up_count > 80:
                sentiment_score += 20
            elif limit_up_count > 50:
                sentiment_score += 10
            elif limit_up_count < 20:
                sentiment_score -= 20

            if limit_down_count < 5:
                sentiment_score += 10
            elif limit_down_count > 20:
                sentiment_score -= 20

            return {
                'limit_up_count': limit_up_count,
                'limit_down_count': limit_down_count,
                'sentiment_score': min(max(sentiment_score, 0), 100),
                'is_good_market': limit_up_count >= 50 and limit_down_count < 10
            }
        except Exception as e:
            print(f"获取市场情绪失败: {e}")
            return {
                'limit_up_count': 0,
                'limit_down_count': 0,
                'sentiment_score': 50,
                'is_good_market': True
            }

    def _get_sector_data(self, stock_code: str, date: str = None) -> Dict[str, Any]:
        """获取股票所属板块数据."""
        try:
            # 获取股票所属概念板块
            sector_df = ak.stock_board_concept_name_ths()
            if sector_df is None or sector_df.empty:
                return {'sector_name': '未知', 'sector_limit_count': 0, 'sector_score': 0}

            # 这里简化处理，实际应该获取个股所属板块
            # 然后统计板块内涨停数量
            return {
                'sector_name': '待分析',
                'sector_limit_count': 0,
                'sector_score': 10  # 默认给基础分
            }
        except Exception as e:
            print(f"获取板块数据失败: {e}")
            return {'sector_name': '未知', 'sector_limit_count': 0, 'sector_score': 0}

    def _calculate_limit_up_quality_score(self, df: pd.DataFrame, limit_up_idx: int,
                                          market: str = 'sh') -> Tuple[float, Dict[str, Any]]:
        """计算首板质量评分.

        评分维度:
        - 涨停时间 (40分)
        - 封板质量 (30分)
        - 量能特征 (20分)
        - 封单金额 (10分)
        """
        config = self.config['strategy']
        score = 0.0
        details = {}

        if limit_up_idx < 0 or limit_up_idx >= len(df):
            return 0, details

        limit_up_day = df.iloc[limit_up_idx]
        prev_day = df.iloc[limit_up_idx - 1] if limit_up_idx > 0 else limit_up_day

        # 1. 涨停时间评分 (40分)
        # 注意：这里用日线数据无法精确判断涨停时间
        # 实际应该用分时数据，这里用换手率作为间接判断
        turnover = float(limit_up_day.get('turnover', 0))

        # 早盘涨停特征：换手率适中，不是天量
        if turnover < 10:
            time_score = config.get('early_limit_bonus', 15)
            time_desc = "早盘涨停特征"
        elif turnover < 20:
            time_score = config.get('morning_limit_bonus', 10)
            time_desc = "上午涨停特征"
        elif turnover < 30:
            time_score = config.get('afternoon_limit_bonus', 0)
            time_desc = "下午涨停特征"
        else:
            time_score = config.get('late_limit_penalty', -10)
            time_desc = "尾盘涨停特征"

        score += max(time_score, 0)
        details['time_score'] = max(time_score, 0)
        details['time_desc'] = time_desc

        # 2. 封板质量评分 (30分)
        # 用振幅判断：振幅小说明封板坚决
        amplitude = float(limit_up_day.get('amplitude', 0))
        if amplitude < 5:
            quality_score = 30
            quality_desc = "封板坚决"
        elif amplitude < 8:
            quality_score = 20
            quality_desc = "封板较好"
        elif amplitude < 12:
            quality_score = 10
            quality_desc = "封板一般"
        else:
            quality_score = 0
            quality_desc = "反复开板"

        score += quality_score
        details['quality_score'] = quality_score
        details['quality_desc'] = quality_desc

        # 3. 量能特征评分 (20分)
        volume_ratio = float(limit_up_day.get('volume', 0)) / float(prev_day.get('volume', 1))

        if 1.5 <= volume_ratio <= 3:
            vol_score = 20
            vol_desc = "量能完美"
        elif 1 <= volume_ratio < 1.5:
            vol_score = 15
            vol_desc = "量能较好"
        elif 3 < volume_ratio <= 5:
            vol_score = 10
            vol_desc = "量能偏大"
        elif volume_ratio > 5:
            vol_score = 5
            vol_desc = "天量涨停"
        else:
            vol_score = 10
            vol_desc = "缩量涨停"

        score += vol_score
        details['vol_score'] = vol_score
        details['vol_desc'] = vol_desc
        details['volume_ratio'] = round(volume_ratio, 2)

        # 4. 换手率评分 (10分)
        if 5 <= turnover <= 15:
            turnover_score = 10
            turnover_desc = "换手理想"
        elif 3 <= turnover < 5:
            turnover_score = 8
            turnover_desc = "换手偏低"
        elif 15 < turnover <= 25:
            turnover_score = 6
            turnover_desc = "换手偏高"
        elif turnover > 25:
            turnover_score = 3
            turnover_desc = "换手过高"
        else:
            turnover_score = 5
            turnover_desc = "换手过低"

        score += turnover_score
        details['turnover_score'] = turnover_score
        details['turnover_desc'] = turnover_desc

        return min(score, 100), details

    def _calculate_comprehensive_score(self, limit_up_score: float, limit_up_details: Dict,
                                       sector_data: Dict, market_sentiment: Dict) -> Tuple[float, Dict[str, Any]]:
        """计算综合评分."""
        config = self.config['strategy']

        # 基础分：首板质量 (占50%)
        base_score = limit_up_score * 0.5

        # 板块效应分 (占25%)
        sector_score = sector_data.get('sector_score', 0)
        if sector_data.get('sector_limit_count', 0) >= config.get('sector_limit_up_threshold', 3):
            sector_score += config.get('sector_strong_bonus', 10)
        sector_score = min(sector_score, 25)

        # 市场情绪分 (占15%)
        sentiment_score = market_sentiment.get('sentiment_score', 50) * 0.15

        # 市场环境加分/扣分
        if market_sentiment.get('is_good_market', True):
            market_bonus = 10
        else:
            market_bonus = -10

        total_score = base_score + sector_score + sentiment_score + market_bonus

        details = {
            'limit_up_score': round(limit_up_score, 1),
            'limit_up_details': limit_up_details,
            'sector_score': round(sector_score, 1),
            'sentiment_score': round(sentiment_score, 1),
            'market_bonus': market_bonus,
            'total_score': round(total_score, 1)
        }

        return total_score, details

    def _get_realtime_data(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """获取实时行情数据."""
        try:
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                stock_data = df[df['代码'] == stock_code]
                if not stock_data.empty:
                    row = stock_data.iloc[0]
                    return {
                        'open': float(row.get('开盘', 0)),
                        'prev_close': float(row.get('昨收', 0)),
                        'volume': float(row.get('成交量', 0)),
                        'amount': float(row.get('成交额', 0)),
                        'pct_chg': float(row.get('涨跌幅', 0)),
                        'quantity_ratio': float(row.get('量比', 0)),
                    }
        except Exception as e:
            print(f"获取实时数据失败 {stock_code}: {e}")
        return None

    def _analyze_first_limit_up(self, stock_code: str, stock_name: str,
                                target_date: str = None) -> Tuple[bool, str, Dict[str, Any]]:
        """分析首板涨停股票.

        Returns:
            (是否匹配, 信号类型, 详细信息)
        """
        config = self.config['strategy']

        try:
            market = self._get_market_type(stock_code)

            # 获取历史数据
            if target_date:
                end_date = datetime.strptime(target_date, '%Y-%m-%d')
                start_date = end_date - timedelta(days=60)
                start_str = start_date.strftime('%Y%m%d')
                end_str = end_date.strftime('%Y%m%d')

                df = ak.stock_zh_a_hist(
                    symbol=stock_code,
                    period="daily",
                    adjust="qfq",
                    start_date=start_str,
                    end_date=end_str
                )
            else:
                start_date = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')
                df = ak.stock_zh_a_hist(
                    symbol=stock_code,
                    period="daily",
                    adjust="qfq",
                    start_date=start_date
                )

            if df is None or df.empty:
                return False, "无数据", {}

            df = self._rename_hist_cols(df)

            for col in self.essential_cols:
                if col not in df.columns:
                    return False, "字段缺失", {}

            if len(df) < 10:
                return False, "数据不足", {}

            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else last

            # 基础筛选
            price_limit = float(config.get('price_limit', 100.0))
            if float(last['close']) > price_limit:
                return False, "价格过高", {}

            # 检查是否涨停
            if not self._is_limit_up(float(last.get('pct_chg', 0)), market):
                return False, "非涨停", {}

            # 检查是否首板
            if not self._check_no_recent_limit_up(df, len(df) - 1, config.get('no_limit_up_days', 5), market):
                return False, "非首板", {}

            # 换手率筛选
            turnover = float(last.get('turnover', 0))
            min_turnover = float(config.get('min_turnover', 3.0))
            max_turnover = float(config.get('max_turnover', 35.0))
            if turnover < min_turnover or turnover > max_turnover:
                return False, f"换手率不达标({turnover:.1f}%)", {}

            # 获取市场情绪
            market_sentiment = self._get_market_sentiment(target_date)

            # 获取板块数据
            sector_data = self._get_sector_data(stock_code, target_date)

            # 计算首板质量评分
            limit_up_score, limit_up_details = self._calculate_limit_up_quality_score(
                df, len(df) - 1, market
            )

            # 计算综合评分
            total_score, score_details = self._calculate_comprehensive_score(
                limit_up_score, limit_up_details, sector_data, market_sentiment
            )

            # 检查最低评分要求
            min_total_score = float(config.get('min_total_score', 60))
            if total_score < min_total_score:
                return False, f"综合评分不足({total_score:.0f}<{min_total_score})", {}

            # 风险评分
            risk_score = 100 - total_score
            max_risk = float(config.get('max_risk_score', 40))
            if risk_score > max_risk:
                return False, f"风险过高({risk_score:.0f}>{max_risk})", {}

            # 获取实时数据（第二天竞价）
            realtime = self._get_realtime_data(stock_code)

            # 判断上车信号
            entry_signal = ""
            entry_strength = 0

            if realtime:
                open_price = realtime.get('open', 0)
                prev_close = realtime.get('prev_close', 0)
                quantity_ratio = realtime.get('quantity_ratio', 0)

                if prev_close > 0:
                    open_pct = ((open_price - prev_close) / prev_close) * 100

                    open_high_min = float(config.get('open_high_min', 2.0))
                    open_high_max = float(config.get('open_high_max', 6.0))
                    min_quantity_ratio = float(config.get('min_quantity_ratio', 2.0))

                    if open_high_min <= open_pct <= open_high_max:
                        if quantity_ratio >= min_quantity_ratio:
                            entry_signal = "竞价强势"
                            entry_strength = 3
                        else:
                            entry_signal = "竞价高开"
                            entry_strength = 2
                    elif open_pct > open_high_max:
                        entry_signal = "高开过大"
                        entry_strength = 1
                    elif open_pct > 0:
                        entry_signal = "小幅高开"
                        entry_strength = 1
                    else:
                        entry_signal = "低开"
                        entry_strength = 0

                    score_details['open_pct'] = round(open_pct, 2)
                    score_details['quantity_ratio'] = round(quantity_ratio, 2)
            else:
                entry_signal = "首板待观察"
                entry_strength = 1

            # 构建结果
            result = {
                'code': stock_code,
                'name': stock_name,
                'pick_price': float(last['close']),
                'signal': entry_signal,
                'signal_strength': entry_strength,
                'limit_up_date': str(last['date']),
                'limit_up_score': round(limit_up_score, 1),
                'total_score': round(total_score, 1),
                'risk_score': round(risk_score, 1),
                'turnover': round(turnover, 2),
                'volume': int(last['volume']),
                'pct_chg': round(float(last.get('pct_chg', 0)), 2),
                'market_sentiment': market_sentiment.get('sentiment_score', 50),
                'limit_up_count': market_sentiment.get('limit_up_count', 0),
                'limit_down_count': market_sentiment.get('limit_down_count', 0),
                'score_details': score_details,
                'reason_tag': entry_signal,
                'note': f"首板分:{limit_up_score:.0f} 综合:{total_score:.0f} 风险:{risk_score:.0f} {limit_up_details.get('time_desc', '')}"
            }

            if realtime:
                result['open_price'] = realtime.get('open', 0)
                result['quantity_ratio'] = realtime.get('quantity_ratio', 0)

            return True, entry_signal, result

        except Exception as e:
            import traceback
            print(f"分析错误 {stock_code}: {e}")
            print(traceback.format_exc())
            return False, f"错误:{str(e)}", {}

    def scan(self, date: str = None) -> List[Dict[str, Any]]:
        """运行首板涨停策略扫描.

        Args:
            date: 目标日期 (YYYY-MM-DD格式), None表示今天

        Returns:
            选股结果列表
        """
        print(f"🚀 启动首板涨停次日上车策略... 时间: {datetime.now()}")
        if date:
            print(f"📅 回测日期: {date}")

        config = self.config['strategy']

        # 获取市场情绪（只获取一次）
        market_sentiment = self._get_market_sentiment(date)
        print(f"📊 市场情绪: 涨停{market_sentiment['limit_up_count']}家 跌停{market_sentiment['limit_down_count']}家 "
              f"情绪分:{market_sentiment['sentiment_score']}")

        if not market_sentiment.get('is_good_market', True):
            print("⚠️ 市场情绪较差，谨慎操作")

        stock_list = self._get_stock_list()
        if stock_list.empty:
            print("未获取到股票列表")
            return []

        code_col = '代码' if '代码' in stock_list.columns else ('code' if 'code' in stock_list.columns else None)
        name_col = '名称' if '名称' in stock_list.columns else ('name' if 'name' in stock_list.columns else None)

        if not code_col or not name_col:
            print("股票列表字段异常")
            return []

        scan_limit = config.get('scan_limit', 500)
        if scan_limit > 0 and len(stock_list) > scan_limit:
            stock_list = stock_list.head(scan_limit)

        print(f"📊 开始扫描 {len(stock_list)} 只股票，寻找首板涨停...")

        selected_stocks = []
        processed = 0

        for _, row in stock_list.iterrows():
            code = str(row[code_col])
            name = str(row[name_col])

            if self._should_exclude(code, name):
                continue

            match, reason, result = self._analyze_first_limit_up(code, name, date)

            if match:
                selected_stocks.append(result)

            processed += 1
            if processed % 100 == 0:
                print(f"  已处理 {processed}/{len(stock_list)} 只, 选中 {len(selected_stocks)} 只")

        print(f"✅ 扫描完成: 共处理 {processed} 只, 初选 {len(selected_stocks)} 只")

        selected_stocks = self._sort_and_filter(selected_stocks)
        self._save_results(selected_stocks, date)

        return selected_stocks

    def _get_stock_list(self) -> pd.DataFrame:
        """获取股票列表."""
        try:
            df = ak.stock_info_a_code_name()
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
        except Exception as e:
            print(f"stock_info_a_code_name 失败: {e}")

        try:
            df2 = ak.stock_zh_a_spot_em()
            if isinstance(df2, pd.DataFrame) and not df2.empty:
                return df2[[c for c in df2.columns if c in ('代码', '名称', 'code', 'name')]]
        except Exception as e:
            print(f"stock_zh_a_spot_em 失败: {e}")

        try:
            sh = ak.stock_info_sh_name_code()
        except Exception:
            sh = pd.DataFrame()
        try:
            sz = ak.stock_info_sz_name_code()
        except Exception:
            sz = pd.DataFrame()

        if isinstance(sh, pd.DataFrame) and not sh.empty:
            sh = sh.rename(columns={'证券代码': '代码', '证券简称': '名称'})
        if isinstance(sz, pd.DataFrame) and not sz.empty:
            sz = sz.rename(columns={'A股代码': '代码', 'A股简称': '名称'})

        merged = pd.concat([d for d in [sh, sz] if isinstance(d, pd.DataFrame)], ignore_index=True)
        if not merged.empty and '代码' in merged.columns and '名称' in merged.columns:
            merged = merged[['代码', '名称']].dropna().drop_duplicates()
            return merged

        return pd.DataFrame({
            '代码': ['600000', '600519', '000001', '000002', '002594'],
            '名称': ['浦发银行', '贵州茅台', '平安银行', '万科A', '比亚迪']
        })

    def _should_exclude(self, code: str, name: str) -> bool:
        """检查是否应该排除该股票."""
        config = self.config['strategy']

        if config.get('exclude_st', True) and ('ST' in name.upper() or '*ST' in name.upper()):
            return True
        if config.get('exclude_kechuang', True) and code.startswith('688'):
            return True
        if code.startswith('8') or code.startswith('4'):
            return True

        return False

    def _sort_and_filter(self, stocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """排序和筛选股票."""
        config = self.config['strategy']

        def sort_key(x):
            signal_rank = {'竞价强势': 0, '竞价高开': 1, '小幅高开': 2, '首板待观察': 3, '高开过大': 4, '低开': 5}
            return (
                signal_rank.get(x['signal'], 6),
                -x.get('signal_strength', 0),
                -x.get('total_score', 0),
                -x.get('limit_up_score', 0),
                x.get('risk_score', 100)
            )

        stocks.sort(key=sort_key)

        select_count = config.get('select_count', 10)
        return stocks[:select_count]

    def _save_results(self, stocks: List[Dict[str, Any]], date: str = None):
        """保存选股结果."""
        os.makedirs('data', exist_ok=True)

        out_json = self.config['output'].get('file_path', 'data/first_limit_up_selection.json')
        with open(out_json, 'w', encoding='utf-8') as f:
            json.dump(stocks, f, ensure_ascii=False, indent=2)

        if stocks:
            df = pd.DataFrame(stocks)
            out_csv = out_json.replace('.json', '.csv')
            df.to_csv(out_csv, index=False, encoding='utf-8-sig')

        print(f"💾 结果已保存至: {out_json}")

    def backtest(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """回测策略.

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            回测结果统计
        """
        print(f"📊 开始回测: {start_date} 至 {end_date}")

        try:
            cal = ak.tool_trade_date_hist_sina()
            trade_dates = cal[cal['trade_date'] >= start_date]['trade_date'].tolist()
            trade_dates = [d for d in trade_dates if d <= end_date]
        except Exception:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            trade_dates = []
            current = start
            while current <= end:
                if current.weekday() < 5:
                    trade_dates.append(current.strftime('%Y-%m-%d'))
                current += timedelta(days=1)

        all_signals = []
        daily_results = []

        for trade_date in trade_dates:
            signals = self.scan(trade_date)
            daily_results.append({
                'date': trade_date,
                'count': len(signals),
                'signals': signals
            })
            all_signals.extend(signals)

        total_signals = len(all_signals)
        signal_types = {}
        for s in all_signals:
            signal_types[s['signal']] = signal_types.get(s['signal'], 0) + 1

        avg_score = sum(s.get('total_score', 0) for s in all_signals) / total_signals if total_signals > 0 else 0
        avg_risk = sum(s.get('risk_score', 0) for s in all_signals) / total_signals if total_signals > 0 else 0

        result = {
            'start_date': start_date,
            'end_date': end_date,
            'total_trading_days': len(trade_dates),
            'total_signals': total_signals,
            'avg_signals_per_day': round(total_signals / len(trade_dates), 2) if trade_dates else 0,
            'signal_types': signal_types,
            'avg_total_score': round(avg_score, 2),
            'avg_risk_score': round(avg_risk, 2),
            'daily_results': daily_results
        }

        print(f"✅ 回测完成: 共 {total_signals} 个信号, 平均每日 {result['avg_signals_per_day']} 个")

        return result
