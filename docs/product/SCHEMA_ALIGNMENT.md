## P6 Legacy Payload - 2026-05-04

Schema revision `0003_picks_legacy_payload_json` adds `picks.legacy_payload_json` to preserve legacy-only SQLite context. The migration now stores fields such as `pick_price`, `ma25`, `vol_ratio`, `content_title`, and `content_ref` instead of reporting them as unmapped warnings. Staging resolve/apply/verify currently reports `issues=0`.

# Schema Alignment Matrix

P6 legacy 下线前，先锁定当前事实：v1 API 已经产品化，但数据层仍主要读写 SQLite legacy 表。迁移到 MySQL/Alembic 前，不能丢失复盘、收益、行情质量和审计关联字段。

## Picks

| v1 API field | SQLite legacy column | MySQL/Alembic status | 迁移规则 |
| --- | --- | --- | --- |
| `id` | `id` | 已有基础主键 | 保持主键语义 |
| `symbol` | `code` | `symbol` 已有 | 迁移时重命名 |
| `stock_name` | `name` | `stock_name` 已有 | 迁移时重命名 |
| `trade_date` | `pick_date` | `trade_date` 已有 | 迁移时重命名 |
| `source` | `source` | `source` 已有 | 保持 |
| `source_channel` | `source_channel` | 0002 已补 | 迁移时保留 |
| `strategy_code` | `strategy_name` | `strategy_id` 已有但语义不同 | 需建立 code/id 映射 |
| `status` | `review_status` | `status` 已有 | 迁移时重命名 |
| `risk_level` | `result_grade` | 0002 已补 | 迁移时重命名 |
| `review_comment` | `review_comment` | 0002 已补 | 迁移时保留 |
| `deal_status` | `deal_status` | 0002 已补 | 迁移时保留 |
| `return_pct` | `return_pct` | 0002 已补 | 迁移时保留 |
| `max_return_pct` | `max_return_pct` | 0002 已补 | 迁移时保留 |
| `drawdown_pct` | `drawdown_pct` | 0002 已补 | 迁移时保留 |
| `holding_days` | `holding_days` | 0002 已补 | 迁移时保留 |
| `watch_flag` | `watch_flag` | 0002 已补 | 迁移时保留 |
| `validation_result` | `validation_result` | 0002 已补 | 迁移时保留 |
| `validation_note` | `validation_note` | 0002 已补 | 迁移时保留 |
| `validated_at` | `validated_at` | 0002 已补 | 迁移时保留 |
| `data_quality` | `data_quality` | 0002 已补 | 迁移时保留 |
| `market_data_source` | `market_data_source` | 0002 已补 | 迁移时保留 |
| `fallback_used` | `fallback_used` | 0002 已补 | 迁移时保留 |

## Tenant Boundary

当前 SQLite `picks` 表没有 `tenant_id`。v1 API 会校验租户请求头和用户绑定关系，但选股池数据层仍是全局池。P6 迁移时必须二选一：

- 补 `tenant_id` 并迁移历史记录到默认租户。
- 明确选股池是全局研究池，不宣称数据层租户隔离。

当前测试 `tests/test_schema_alignment.py` 锁定了这两个事实：v1 依赖字段必须存在，`tenant_id` 暂时缺失必须被显式看见。

SQLAlchemy/Alembic 目标 schema 已通过 `0002_picks_v1_contract_fields.py` 补齐 v1 picks 当前依赖字段，并增加 `tenant_id + trade_date + symbol + source` 唯一约束，承接 v1 入池去重语义。

## Backtest

当前 `backtest_results` 只持久化摘要字段，v1 响应里的参数组、收益曲线、交易样本、成交约束摘要没有完整落库。后续迁移建议优先补：

- `params_json`
- `equity_curve_json`
- `trades_json` 或 `backtest_trades`
- `execution_constraints_json`
- `benchmark_json`

## Reports

`/api/v1/reports/summary` 是从 picks 聚合出的周/月报；`/api/v1/reports` 是研究报告列表语义。P6 迁移时应保持这两个接口语义分离，避免把报表聚合和研究报告实体混成一张表。
## P6 Migration Dry Run

本轮已落地 `scripts/migrate_sqlite_to_mysql.py` 的 picks 迁移 dry-run planner。默认执行只读取 SQLite，不写 MySQL；只有显式传入 `--apply` 才会连接目标库写入。

当前 dry-run 覆盖：
- SQLite `picks` 到目标 MySQL `picks` v1 contract 字段映射。
- 默认 `tenant_id=1` 承接 legacy 全局数据池。
- `code -> symbol`、`name -> stock_name`、`pick_date -> trade_date`、`review_status -> status`、`result_grade -> risk_level`。
- `watch_flag`、`fallback_used` 布尔归一化，日期/时间空串转空值。
- 按 `(tenant_id, trade_date, symbol, source)` 报告重复记录。
- 归档记录默认跳过，可用 `--include-archived` 纳入。
- 未解析的 `strategy_name/source -> strategy_id` 会作为 unresolved strategy issue 报告。

验收命令：

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_schema_alignment.py tests\test_sqlite_to_mysql_migration.py -q -p no:cacheprovider
.\venv\Scripts\python.exe scripts\migrate_sqlite_to_mysql.py --json
```

边界说明：dry-run 已验证映射计划，不代表生产数据已经迁移完成。生产级完成条件仍包括 staging MySQL 写入、行数/字段/tenant 映射对账、幂等重跑、备份恢复和读写切换验收。
## P6 Staging Pipeline - 2026-05-04

`scripts/staging_mysql_migration.py` 固化 staging 迁移顺序：
1. `python -m alembic upgrade head`
2. `python scripts/bootstrap_mysql_seed.py`
3. `python scripts/validate_mysql_schema.py`
4. `python scripts/migrate_sqlite_to_mysql.py --resolve-strategies --json`

默认模式不会写入 picks。只有显式传入：

```powershell
.\venv\Scripts\python.exe scripts\staging_mysql_migration.py --apply --confirm-apply sqlite-to-mysql-picks
```

才会执行 apply 和 verify。pipeline 会在 unresolved strategy、目标前置条件失败或 reconciliation 失败时非 0 退出。

## P6 Target Preconditions - 2026-05-04

本轮补齐 staging 写入前置条件：
- `scripts/bootstrap_mysql_seed.py` 幂等创建默认策略 `2560` 和 `first_limit_up`。
- `scripts/validate_mysql_schema.py` 除 schema/revision 外，还检查默认 tenant 和默认策略 seed。
- `scripts/migrate_sqlite_to_mysql.py` 在连接目标库后检查 `tenant_id` 是否存在、策略 seed 是否存在；缺失时阻塞 `--apply`。

这一步的目标是让 `--resolve-strategies` 在 staging 库中能解析 legacy `strategy_name/source`，并避免向不存在 tenant 的目标库写入 picks。

## P6 Pre-write Gate And Reconciliation - 2026-05-04

本轮新增 `scripts/migrate_sqlite_to_mysql.py` 的写入前阻塞校验和对账报告能力。

`--apply` 现在需要显式二次确认：

```powershell
.\venv\Scripts\python.exe scripts\migrate_sqlite_to_mysql.py --apply --confirm-apply sqlite-to-mysql-picks
```

默认阻塞项：
- 未解析 `strategy_name/source -> strategy_id`。
- 源行缺少必填字段或日期不可转换。
- 内部映射出现目标字段不一致。
- 无效行被跳过但未显式允许。

默认 warning 项：
- legacy 源字段存在但当前 `Pick` 目标表没有槽位，例如 `pick_price`、`ma25`、`vol_ratio`、`content_ref`。
- 源库重复 key 行会被报告并跳过。

写入或 `--verify` 后会输出 reconciliation：
- `expected_rows`
- `matched_rows`
- `missing_rows`
- `mismatch_rows`
- `field_mismatches`

dry-run/apply 报告同时包含 SQLite 源库指纹：
- `path`
- `size_bytes`
- `mtime`
- `sha256`

边界说明：这只是 staging 写入前的安全能力和对账能力，不代表生产迁移、切流或回滚演练已经完成。
