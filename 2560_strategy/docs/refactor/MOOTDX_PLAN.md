# mootdx 接入规划

## 目标

将 mootdx 作为首选通达信行情数据源，但不让业务层直接依赖 mootdx。

## 接入方式

定义统一接口：

```python
class MarketDataProvider:
    def get_stock_list(self): ...
    def get_daily_bars(self, symbol, start_date, end_date, adjust='qfq'): ...
    def get_trading_dates(self, start_date, end_date): ...
    def health_check(self): ...
```

实现：

- MockMarketDataProvider
- AkShareMarketDataProvider
- MootdxMarketDataProvider

## 风险

- TDX 线路不可用。
- 返回字段与 AkShare 不一致。
- 网络超时或频率限制。
- mootdx 依赖 pytdx，后续可能变化。

## 降级策略

```text
mootdx -> akshare -> cache -> error
```

## 字段标准化

内部统一使用：

```text
symbol, trade_date, open, high, low, close, volume, amount, turnover_rate, source
```
