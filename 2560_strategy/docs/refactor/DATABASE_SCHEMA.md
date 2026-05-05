# MySQL 数据库规划

## 总原则

- 使用 MySQL 8.x。
- 字符集使用 utf8mb4。
- 金融价格、金额、比例使用 DECIMAL，避免 FLOAT。
- 所有业务表保留 created_at / updated_at。
- 可删除业务表使用 deleted_at 软删除。
- 多租户业务表必须带 tenant_id。
- 所有外键字段必须有索引。

## 租户与用户

```sql
CREATE TABLE tenants (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(128) NOT NULL,
  code VARCHAR(64) NOT NULL UNIQUE,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  plan VARCHAR(32) NOT NULL DEFAULT 'default',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE users (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  username VARCHAR(64) NOT NULL UNIQUE,
  email VARCHAR(255),
  password_hash VARCHAR(255) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  last_login_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE roles (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id BIGINT NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(128) NOT NULL,
  is_system TINYINT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_roles_tenant_code (tenant_id, code),
  KEY idx_roles_tenant_id (tenant_id)
);

CREATE TABLE user_tenants (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  tenant_id BIGINT NOT NULL,
  role_id BIGINT NOT NULL,
  is_default TINYINT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_user_tenant (user_id, tenant_id),
  KEY idx_user_tenants_user_id (user_id),
  KEY idx_user_tenants_tenant_id (tenant_id),
  KEY idx_user_tenants_role_id (role_id)
);
```

## 股票与行情

股票和行情作为公共数据，不带 tenant_id。

```sql
CREATE TABLE stocks (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  symbol VARCHAR(16) NOT NULL UNIQUE,
  exchange VARCHAR(16) NOT NULL,
  name VARCHAR(128) NOT NULL,
  market VARCHAR(32),
  industry VARCHAR(128),
  listing_date DATE NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_stocks_exchange (exchange),
  KEY idx_stocks_name (name)
);

CREATE TABLE stock_daily_bars (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  symbol VARCHAR(16) NOT NULL,
  trade_date DATE NOT NULL,
  open DECIMAL(18,4),
  high DECIMAL(18,4),
  low DECIMAL(18,4),
  close DECIMAL(18,4),
  volume BIGINT,
  amount DECIMAL(24,4),
  turnover_rate DECIMAL(12,4),
  source VARCHAR(32) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_daily_symbol_date_source (symbol, trade_date, source),
  KEY idx_daily_symbol_date (symbol, trade_date),
  KEY idx_daily_trade_date (trade_date)
);
```

## 策略与扫描

```sql
CREATE TABLE strategies (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id BIGINT NOT NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(128) NOT NULL,
  category VARCHAR(64),
  description TEXT,
  config_json JSON,
  enabled TINYINT NOT NULL DEFAULT 1,
  created_by BIGINT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  deleted_at DATETIME NULL,
  UNIQUE KEY uk_strategies_tenant_code (tenant_id, code),
  KEY idx_strategies_tenant_enabled (tenant_id, enabled)
);

CREATE TABLE scan_tasks (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id BIGINT NOT NULL,
  strategy_id BIGINT NOT NULL,
  task_no VARCHAR(64) NOT NULL UNIQUE,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  params_json JSON,
  started_at DATETIME NULL,
  finished_at DATETIME NULL,
  error_message TEXT,
  created_by BIGINT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_scan_tasks_tenant_status (tenant_id, status),
  KEY idx_scan_tasks_strategy_id (strategy_id)
);

CREATE TABLE scan_results (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id BIGINT NOT NULL,
  scan_task_id BIGINT NOT NULL,
  strategy_id BIGINT NOT NULL,
  symbol VARCHAR(16) NOT NULL,
  stock_name VARCHAR(128),
  trade_date DATE NOT NULL,
  score DECIMAL(12,4),
  signals_json JSON,
  reason TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_scan_results_tenant_date (tenant_id, trade_date),
  KEY idx_scan_results_tenant_strategy_date (tenant_id, strategy_id, trade_date),
  KEY idx_scan_results_symbol_date (symbol, trade_date)
);
```
