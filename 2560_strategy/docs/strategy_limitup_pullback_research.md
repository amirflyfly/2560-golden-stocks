# 涨停回马枪战法研究与量化落地方案

日期：2026-05-05

本文用于把公开资料中的“涨停回马枪”战法沉淀为本平台可回测、可解释、可部署、可风控的量化策略规格。本文不构成投资建议；所有阈值必须经过全市场历史回测、样本外验证、成交约束、滑点和交易成本校验后，才能进入生产模拟。

## 1. 资料来源与共识

本次整理参考了三类资料：

- 公开战法文章：新浪财经、东方财富财富号等资料普遍把该战法描述为“涨停后回调，再次上攻”的短线模型，强调缩量回调、不破支撑、二次放量。
- 指标公式与通达信资料：公式类资料通常把条件拆成 N 日内涨停、回踩涨停日开盘价或实体支撑、成交量小于涨停日量、重新突破回调高点。
- 交易规则资料：涨停识别不能硬编码 9.5% 或 10%，必须按交易所、板块、风险警示、上市天数和规则生效日期计算涨跌停价。

参考链接：

- [新浪财经：涨停回马枪+缩倍量实战用法](https://finance.sina.com.cn/roll/2025-02-16/doc-ineksnuy4906376.shtml)
- [东方财富财富号：短线投资必学技——涨停回马枪战法](https://caifuhao.eastmoney.com/news/20250720210506384293020)
- [东方财富财富号：涨停回调低吸战法](https://caifuhao.eastmoney.com/news/20260503090803764096290)
- [好公式网：涨停回马枪战法指标说明](https://www.goodgongshi.com/tongdaxingongshi/104131.html)
- [股旁网：涨停后缩量回调公式](https://www.gupang.com/201701/41536.html)
- [MBA 智库百科：涨停板战法](https://wiki.mbalib.com/wiki/%E6%B6%A8%E5%81%9C%E6%9D%BF%E6%88%98%E6%B3%95)
- [上交所：上海证券交易所交易规则（2026 年修订）](https://www.sse.com.cn/lawandrules/sselawsrules2025/trade/universal/c/c_20260424_10816492.shtml)
- [上交所：科创板股票交易问答](https://edu.sse.com.cn/tib/qa/)
- [深交所：创业板交易特别规定问答](https://investor.szse.cn/knowledge/stock/chinext/t20200729_580056.html)
- [深交所：深圳证券交易所交易规则（2023 年修订）](https://docs.static.szse.cn/www/lawrules/rule/trade/W020230217564423808793.pdf)
- [北交所：北京证券交易所交易规则（试行）](https://www.bse.cn/jygl_list/200010919.html)

知乎、公众号等渠道中该战法多为二次转述和案例复盘，口径与上述公开资料高度相似：强势涨停是锚点，回调缩量是洗盘语义，支撑不破是结构确认，二次放量是入场确认。平台不应直接采用“高胜率”“暴利”等营销口径，只抽取可验证的价格、成交量、时间、支撑和成交约束。

## 2. 多 agent 头脑风暴结论

投资研究 agent 结论：

- 涨停回马枪本质是短线强势股二次确认模型：`强势涨停 -> 短期回踩/洗盘 -> 支撑不破 -> 再次放量上攻`。
- 常见买点分为左侧低吸和右侧确认：回踩涨停实体下沿、涨停日开盘价、MA10/MA13/MA20；或重新站上 MA5/MA10、突破回调高点。
- 常见失效点是跌破涨停日实体下沿、涨停日开盘价、关键均线，或 3 到 5 日内无法再启动。

量化工程 agent 结论：

- 策略代码建议为 `LIMIT_UP_RETURN`，名称为“涨停回马枪”。
- 涨停识别用未复权或原始涨跌幅；均线、回撤、收益统计用前复权。两套价格不能混算。
- 信号应区分 `pullback_setup`、`breakout_confirmed`、`failed_pullback`。只有 `breakout_confirmed` 才允许进入模拟交易买入。

风险 agent 结论：

- 当前项目已有 `FIRST_LIMIT_UP/首板涨停次日上车`，但它不是涨停回马枪。首板次日接力偏追高，涨停回马枪偏“涨停后回踩再确认”。
- 回测必须处理一字板买不到、跌停卖不出、停牌、滑点、手续费、印花税、T+1 和涨跌停价格约束。
- 该策略不得直接包装成高胜率实盘策略。生产前必须有本地行情门禁、mock/fallback 禁用、题材周期归因、最大回撤和 kill switch。

## 3. 战法精髓

一句话定义：

> 用涨停作为资金强度锚点，等待短期缩量回踩且不破关键支撑，再在重新放量上攻时参与二次拉升。

量化拆解：

1. `LimitUpEvent`：发现有效涨停锚点。
2. `PullbackValid`：涨停后 1 到 8 个交易日内出现有序回踩。
3. `SupportConfirmed`：回踩不破涨停实体下沿、涨停日开盘价、MA10/MA13/MA20 等支撑。
4. `ReAttackTrigger`：重新放量站上短均线、突破回调高点或突破涨停日高点。
5. `Failed`：跌破支撑、放量滞涨、超时未启动或交易不可成交。

该战法不等于“看到涨停就买”，也不等于“回调就低吸”。只有涨停强度、回踩质量、支撑确认、再启动确认和风险退出同时成立，才算完整信号。

## 4. 市场原理

涨停日：

- 涨停说明该股票在当日出现明显供需失衡或情绪共振。
- 有效涨停最好不是无成交的一字板。实体阳线涨停说明涨停过程中发生了筹码交换，后续回踩才有可解释的支撑位。

回踩期：

- 涨停后短线获利盘、跟风盘会形成抛压。
- 如果回踩缩量，且价格没有破坏涨停阳线实体、涨停日开盘价或关键均线，说明抛压有限。
- 如果回踩放量下跌，则更像资金撤退，而不是洗盘。

再启动：

- 重新放量上攻说明资金二次介入。
- 右侧确认比左侧低吸更稳，但价格更高；左侧低吸赔率更好，但容易买在破位前。
- 因此平台应同时输出观察信号和确认信号，而不是只有一个买入布尔值。

## 5. 核心数据要求

证券基础池：

- `symbol`
- `name`
- `exchange`
- `security_type`
- `listing_date`
- `status`
- `is_st`
- `board_type`
- `limit_rule_profile`

日 K：

- `symbol`
- `trade_date`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `amount`
- `turnover_rate`
- `adjust`
- `interval`
- `source`

必须同时支持：

- `adjust=none`：用于涨停价、跌停价、真实成交价、不可成交判断。
- `adjust=qfq`：用于均线、趋势、回撤、收益统计。

实时快照：

- `last_price`
- `prev_close`
- `open`
- `high`
- `low`
- `volume`
- `amount`
- `bid_price`
- `ask_price`
- `bid_volume`
- `ask_volume`
- `snapshot_time`

增强数据：

- 涨停封单金额。
- 开板次数。
- 涨停时间。
- 集合竞价涨幅。
- 分钟 K。
- 板块涨停家数、跌停家数、连板高度。

增强数据缺失时，策略可以降级评分，但不能伪造“封单强”“早盘板”等结论。

## 6. 涨停识别规则

涨停识别必须优先使用行情源提供的涨停价或交易规则日历。缺失时才使用规则推导：

```text
limit_up_price = round(prev_close * (1 + limit_rate), 2)
is_limit_up = close >= limit_up_price - tick_size
              AND high >= limit_up_price - tick_size
```

板块默认规则：

- 沪深主板普通股票：通常 10%。
- 科创板、创业板：通常 20%，新股上市前 5 个交易日无价格涨跌幅限制。
- 北交所：通常 30%，上市首日等情形无价格涨跌幅限制。
- 风险警示、退市整理、新股、重新上市等必须按交易所和生效日期处理。

特别注意：上交所 2026 年修订规则已发布，生效日期是 2026-07-06，其中包含主板风险警示股票涨跌幅限制调整。平台必须维护 `limit_rule_calendar`，不要把 ST 固定写死为 5% 或 10%。

有效涨停锚点建议：

```text
valid_anchor =
  is_limit_up
  AND close == high OR close >= limit_up_price - tick_size
  AND high > low
  AND close > open
  AND amount >= min_anchor_amount
```

可选过滤：

- 排除一字板：`open >= limit_up_price - tick_size AND low >= limit_up_price - tick_size`。
- 排除炸板回封弱板：如果有分钟数据，记录开板次数和尾盘回封。
- 排除高位出货嫌疑：涨停日前 20 日涨幅过大且放出异常巨量。

## 7. 策略状态机

```text
RawUniverse
  -> LimitUpEvent
  -> PullbackValid
  -> SupportConfirmed
  -> ReAttackTrigger
  -> TradeSignal
  -> PaperOrder
  -> PositionMonitor
  -> ExitSignal
```

状态说明：

- `RawUniverse`：全市场股票池，完成停牌、退市、上市天数、流动性过滤。
- `LimitUpEvent`：在观察窗口内找到有效涨停锚点。
- `PullbackValid`：锚点后出现 1 到 8 日回踩，回撤幅度可控。
- `SupportConfirmed`：最低价没有有效跌破支撑，收盘重新站稳支撑。
- `ReAttackTrigger`：放量突破回调区间高点、前一日高点或涨停锚点高点。
- `TradeSignal`：生成可交易信号，写入 `trade_signals`。
- `PaperOrder`：模拟账户按成交约束生成订单。
- `PositionMonitor`：根据止损、止盈、时间止损持续评估。
- `ExitSignal`：触发卖出或信号失效。

## 8. 量化条件建议

涨停锚点：

```text
anchor_in_window = recent valid_anchor in [T-13, T-2]
anchor_quality_score >= 60
```

回踩有效：

```text
days_since_limit_up between 1 and 8
pullback_depth_pct = close_T / anchor_close - 1
pullback_depth_pct between -0.08 and 0.02
max_pullback_pct = min(low(anchor+1..T)) / anchor_close - 1
max_pullback_pct >= -0.12
```

缩量要求：

```text
pullback_volume_avg = avg(volume(anchor+1..T))
shrink_ratio = pullback_volume_avg / anchor_volume
shrink_ratio <= 0.70
```

支撑确认：

```text
support_level = max(anchor_open, anchor_mid, ma10, ma13, ma20)
support_distance_pct = low_T / support_level - 1
support_distance_pct >= -0.02
close_T >= support_level
```

再攻击确认：

```text
break_pullback_high = close_T > max(high(anchor+1..T-1))
reclaim_ma5 = close_T > ma5
volume_recover_ratio = volume_T / avg(volume(anchor+1..T-1))
volume_recover_ratio >= 1.20
close_position = (close_T - low_T) / (high_T - low_T)
close_position >= 0.60
```

流动性过滤：

```text
amount_ma20 >= 50_000_000
turnover_rate_ma5 >= 1.0
```

更稳健的生产阈值：

```text
amount_ma20 >= 100_000_000
total_score >= 70
risk_score <= 35
```

## 9. 入场、出场与风控

观察信号：

- 有效涨停锚点。
- 回踩缩量。
- 不破支撑。
- 还没有放量突破。

信号类型：`pullback_setup`。该信号只进入观察列表，不自动模拟买入。

确认买入：

- 收盘重新站上 MA5/MA10。
- 放量突破回调区间高点。
- 或突破涨停日高点。
- 次日不高开过多，不是一字涨停，不触发不可成交门禁。

信号类型：`breakout_confirmed`。该信号允许进入模拟交易。

止损：

- 收盘跌破 `min(recent_pullback_low, anchor_open, ma20) * 0.98`。
- 买入后浮亏达到 5% 到 8%。
- 放量跌破涨停实体中位线。

止盈：

- 盈利 8% 到 12% 可分批止盈。
- 二次涨停后次日弱转强失败，减仓或退出。
- 最高价回撤 5% 或收盘跌破 MA5，退出。

时间止损：

- 买入后 3 个交易日未突破锚点高点，降低评分或退出。
- 最长持有 7 到 10 个交易日。

组合风控：

- 单票仓位 5% 到 10%。
- 每日最多开仓 3 笔。
- 总持仓不超过 5 到 8 只。
- 大盘单日跌幅超过 1.5%、跌停家数显著放大、连板高度断裂时暂停新开仓。

## 10. 回测门禁

禁止未来函数：

- `scan(T)` 只能使用 T 日及以前的数据。
- 买入成交从 T+1 开始模拟。
- 不能用 T+N 的最高价确认 T 日信号。

成交约束：

- 开盘一字涨停：不可买入。
- 买入价高于涨停价：不可买入。
- 卖出日跌停且无成交：不可卖出。
- 停牌日：不可买卖。
- A 股股票 T+1：当天买入不能当天卖出。

成本模型：

- 买入滑点。
- 卖出滑点。
- 佣金。
- 印花税。
- 过户费。
- 最小交易单位。

分层归因：

- 按 `days_since_limit_up` 分组。
- 按 `shrink_ratio` 分组。
- 按 `pullback_depth_pct` 分组。
- 按板块热度分组。
- 按市场情绪分组。
- 按成交额和换手率分组。

必须输出：

- 胜率。
- 盈亏比。
- 最大回撤。
- 连续亏损次数。
- 年化收益。
- 交易分布。
- 不可成交样本占比。
- 信号到成交的滑点分布。

## 11. 平台信号合同

建议信号结构：

```json
{
  "schema_version": "strategy-signal/limitup-pullback/v1",
  "strategy_code": "LIMIT_UP_RETURN",
  "strategy_name": "涨停回马枪",
  "symbol": "000001",
  "security_type": "stock",
  "bar_interval": "1d",
  "adjust": "qfq",
  "signal_date": "2026-05-05",
  "signal_type": "WATCH",
  "signal_subtype": "pullback_setup",
  "score": 72,
  "price_ref": 10.88,
  "trigger_price": 11.20,
  "stop_loss_price": 10.21,
  "indicators": {
    "anchor_date": "2026-04-28",
    "anchor_open": 9.95,
    "anchor_high": 10.50,
    "anchor_low": 9.90,
    "anchor_close": 10.50,
    "anchor_volume": 120000000,
    "limit_rate": 0.1,
    "days_since_limit_up": 4,
    "pullback_depth_pct": -0.045,
    "max_pullback_pct": -0.072,
    "shrink_ratio": 0.58,
    "ma5": 10.76,
    "ma10": 10.35,
    "ma13": 10.21,
    "ma20": 9.88,
    "support_level": 10.35,
    "support_distance_pct": 0.011,
    "volume_recover_ratio": 1.28
  },
  "phase": {
    "setup_phase": "support_confirmed",
    "support_type": "ma10",
    "breakout_confirmed": false
  },
  "risk": {
    "risk_score": 28,
    "risk_flags": []
  },
  "reason": "涨停后4日缩量回踩，未跌破MA10和涨停实体下沿，等待放量突破回调高点。"
}
```

## 12. 与当前项目的关系

当前项目中的 `FIRST_LIMIT_UP` 更接近“首板涨停次日上车”，关注首板后次日接力，不等同于涨停回马枪。

涨停回马枪应作为独立策略接入：

- 策略代码：`LIMIT_UP_RETURN`
- 策略名称：`涨停回马枪`
- 策略类型：短线强势回踩二次确认
- 默认周期：日 K
- 可扩展周期：30 分钟、60 分钟，用于盘中确认，不替代日 K 锚点
- 默认交易模式：观察信号 + 模拟交易确认信号

生产数据流：

```text
全市场基础池
  -> 日 K 同步 adjust=none
  -> 日 K 同步 adjust=qfq
  -> 指标预计算 MA/volume/drawdown
  -> 涨停锚点扫描
  -> 回踩状态更新
  -> 实时快照/分钟 K 确认
  -> 生成观察/买入/风险信号
  -> 模拟账户订单
  -> 持仓退出评估
```

## 13. 落地清单

P0 研究规格：

- [x] 明确战法定义：涨停锚点、缩量回踩、支撑不破、放量再攻。
- [x] 区分 `FIRST_LIMIT_UP` 与 `LIMIT_UP_RETURN`。
- [x] 明确不可把观察信号直接转成买入。
- [x] 明确涨停识别不能硬编码。

P1 数据中心：

- [x] 增加或确认 `adjust=none` 日 K 同步覆盖率。
- [x] 增加或确认 `adjust=qfq` 日 K 同步覆盖率。
- [x] 增加涨跌停规则日历 `limit_rule_calendar`。
- [x] 增加停牌、新股、退市整理、风险警示字段。
- [x] 增加分钟 K 和实时快照覆盖率看板字段。

P2 策略实现：

- [x] 新增 `LIMIT_UP_RETURN` 内置策略。
- [x] 实现 `LimitUpEvent` 锚点识别。
- [x] 实现 `PullbackValid` 回踩识别。
- [x] 实现 `SupportConfirmed` 支撑确认。
- [x] 实现 `ReAttackTrigger` 再攻击确认。
- [x] 输出 `pullback_setup`、`breakout_confirmed`、`failed_pullback` 三类信号。

P3 回测：

- [x] 回测支持 T+1 成交。
- [x] 回测支持一字涨停不可买。
- [x] 回测支持跌停不可卖。
- [x] 回测支持停牌不可交易。
- [x] 回测输出不可成交样本占比。
- [x] 回测输出按回踩天数、缩量比例、回撤深度、市场情绪的归因。

P4 模拟交易：

- [x] 只有 `breakout_confirmed` 可进入模拟买入。
- [x] `pullback_setup` 只进入观察列表和提醒。
- [x] 增加止损、止盈、时间止损。
- [x] 增加单票仓位、每日开仓数、总持仓数限制。
- [x] 增加策略级 kill switch。

P5 前端产品：

- [x] 策略页增加“涨停回马枪”策略卡片。
- [x] 扫描结果展示锚点日、回踩天数、缩量比例、支撑位、触发价、止损价。
- [x] K 线图叠加涨停锚点、支撑线、触发线、止损线。
- [x] 报表增加该策略的交易分布、回撤、归因和不可成交原因。
- [x] 提醒规则支持从 `pullback_setup` 到 `breakout_confirmed` 的状态变化提醒。

P6 生产门禁：

- [x] 禁止 mock/fallback 数据参与生产信号。
- [x] 缺本地历史 K 线阻断生产扫描。
- [x] 缺实时快照阻断生产买入。
- [x] 缺涨跌停规则阻断涨停识别。
- [x] 样本外回测未通过不得启用生产模拟。
- [x] 实盘接口仅保留适配器，不自动下真实订单。

## 14. 2026-05-05 落地结果

- P1：数据中心已补齐 `adjust=none/qfq` 覆盖率、涨跌停规则日历、证券状态字段、分钟 K/实时快照覆盖率摘要。
- P2：新增 `LIMIT_UP_RETURN` 内置策略，输出观察、确认、失败三类信号；涨停识别走规则模型，不再硬编码固定涨幅。
- P3：回测 API 和底层回测已输出 T+1、涨跌停、停牌、不可成交比例和回踩/缩量/回撤/情绪归因。
- P4：模拟交易仅允许 `breakout_confirmed` 买入，支持止损、止盈、时间止损、单票资金、每日开仓、总持仓和 kill switch。
- P5：前端策略、扫描、K 线、报表、提醒均增加涨停回马枪展示和状态变化提醒口径。
- P6：生产运行阻断 mock/fallback、缺历史、缺快照、缺涨跌停规则；样本外回测未通过时不启用生产模拟；实盘只保留适配器契约，不自动下真实单。
