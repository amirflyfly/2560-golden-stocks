# MySQL 索引策略

## 原则

- 所有外键字段必须加索引。
- 高频列表页按 tenant_id + created_at / trade_date 建复合索引。
- 高频详情页使用唯一键或主键查询。
- JSON 字段只存低频配置和信号，不作为高频过滤条件。

## 推荐索引

### strategies

```sql
UNIQUE KEY uk_strategies_tenant_code (tenant_id, code);
KEY idx_strategies_tenant_enabled (tenant_id, enabled);
```

### scan_tasks

```sql
KEY idx_scan_tasks_tenant_status (tenant_id, status);
KEY idx_scan_tasks_strategy_id (strategy_id);
```

### scan_results

```sql
KEY idx_scan_results_tenant_date (tenant_id, trade_date);
KEY idx_scan_results_tenant_strategy_date (tenant_id, strategy_id, trade_date);
KEY idx_scan_results_symbol_date (symbol, trade_date);
```

### picks

```sql
KEY idx_picks_tenant_date (tenant_id, trade_date);
KEY idx_picks_tenant_symbol (tenant_id, symbol);
KEY idx_picks_tenant_strategy_date (tenant_id, strategy_id, trade_date);
```

### stock_daily_bars

```sql
UNIQUE KEY uk_daily_symbol_date_source (symbol, trade_date, source);
KEY idx_daily_symbol_date (symbol, trade_date);
KEY idx_daily_trade_date (trade_date);
```
