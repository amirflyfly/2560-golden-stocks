# 产品路线图

## 阶段原则

后续开发按“先验证、再闭环、再增强”的顺序推进。每个阶段都必须能独立验收、可回归、可被真实使用。

## P0：工程验证与仓库卫生

目标：让项目恢复可验证状态，避免在不可回归的基础上继续堆功能。

当前状态：已完成。

已交付：
- 修复本地 `venv` 依赖，后端 pytest 可运行。
- 固化后端、前端、Compose 验证命令。
- 新增 `scripts/check_repo_hygiene.py`，检测 `node_modules`、`venv`、`__pycache__`、`.pyc`、缓存、日志、数据库和 `dist` 产物。
- 新增 `scripts/clean_repo_index.py`，支持 dry-run 和 `--apply`，只从 Git 索引移除运行产物，不删除本地文件。
- 已执行索引清理，违规项从 13,532 降为 0。
- 父级 Git 仓库新增 `.github/workflows/ci.yml`，CI 工作目录指向 `2560_strategy`。

验收标准：
- `python -m pytest` 或项目 `venv` 下 pytest 通过。
- `npm test`、`npm run build`、`docker compose config --quiet` 通过。
- `npm run repo:hygiene` 通过。
- CI 能在真实 Git 根目录执行仓库卫生、后端、前端和 Compose 检查。

## P1：扫描到选股池闭环

目标：让用户从扫描结果自然进入候选跟踪。

当前状态：已完成最小闭环。

已交付：
- 扫描任务自动轮询和结果分页。
- 扫描结果可一键加入选股池。
- 入池按交易日、股票代码、来源去重并更新。
- 可从扫描结果跳转指定股票 K 线。

后续补强：
- viewer 禁用态和权限提示。
- 扫描动作审计。
- mock/fallback 数据质量提示进一步统一。

## P2：选股池复盘中心

目标：让选股池成为每日复盘主页面。

当前状态：已完成最小复盘闭环。

已交付：
- v1 选股详情、复盘更新、复盘时间线 API。
- 前端支持状态、策略、风险筛选。
- 支持复盘结论、成交状态、收益、最大收益、回撤、持有天数等字段。
- 支持单标的复盘时间线展示。

后续补强：
- 日期和来源筛选。
- 批量状态更新。
- 写操作审计。
- 观察池看板视图。

## P4：最小报表

目标：先形成周报/月报，避免一开始做复杂 BI。

当前状态：已完成最小报表。

已交付：
- 周报/月报 API 和前端展示。
- 覆盖入池数、复盘数、成交数、胜率、平均收益、高风险占比。
- 按策略聚合基础表现。

后续补强：
- CSV/JSON 导出。已完成。
- 区分真实行情、fallback 和 mock。已完成。
- 报表追溯到候选、复盘和回测记录。

## P3：回测增强

目标：让策略页承担策略验证职责。

当前状态：已完成第二轮增强。

已交付：
- 回测收益曲线展示。
- 手续费、滑点输入。
- 涨跌停约束开关和提示。
- 估算净收益展示。
- 真实成交约束建模，支持涨跌停、停牌和显式无效价格剔除统计。
- 历史回测详情和审计轨迹查看。

后续补强：
- 基准对比。已完成。
- 参数组对比。已完成。

## P5：市场发现能力

目标：补足主流投研产品的机会发现层。

交付内容：
- 指数和市场宽度。
- 板块/题材热度。
- 资金流和成交活跃度。
- 龙虎榜、公告、新闻入口。
- 因子筛选器。
- 异动提醒。

## P6：Legacy 下线与平台化

目标：减少双轨维护成本，强化平台稳定性。

当前状态：已完成第一轮边界收敛。

交付内容：
- 旧 Jinja 页面只读或跳转。
- 旧 `/api` 不再承接新功能。
- SQLite legacy 依赖矩阵逐步迁移。
- URL map 测试。
- 权限矩阵测试。
- 容器化冒烟验证。

已交付：
- 新增 React 正式入口 `/app`，支持 `?page=` 和 `?symbol=` 启动参数。
- legacy `/strategies/stock-chart` 跳转到 `/app?page=kline`，不再渲染旧 K 线页。
- legacy `/api` 响应增加 deprecated header 和 `/api/v1` successor link。
- legacy `/api/stock-data`、`/api/save-stock-data` 纳入登录保护。
- 新增 schema 对齐矩阵，测试锁定 v1 picks 依赖字段和当前 tenant 边界缺口。
- legacy `/reports` 跳转 React 报表页。
- legacy strategy management 写接口纳入登录保护并标记 deprecated。
- legacy `/api/scan/*` 路由标记 deprecated。
- legacy `/`、`/edit`、`/deal-review`、`/strategies/`、`/strategies/pool/*`、`/strategies/run/*`、`/strategies/backtest/*` 跳转 React 主流程。
- React `/app` 支持 picks 状态和策略筛选启动参数。
- watchlist legacy 页面进入只读模式，旧研究分析、Agent stream、watch/unwatch 写入口返回 410。
- SQLAlchemy/Alembic picks 已补齐 v1 contract 字段，并增加入池去重唯一约束。
- legacy `/admin/users` 跳转 React admin，旧用户创建/启停/重置密码写入口返回 410。
- leaderboards legacy 页面标记只读。
- 新增 legacy admin 保留策略，明确备份/恢复/TradingAgents 配置临时保留条件和替代标准。

后续补强：
- 为 admin 备份/恢复/TradingAgents 配置补 React/v1 替代能力。
- 设计 SQLite legacy 数据迁移到目标 MySQL schema 的执行脚本。

## 推荐执行顺序

1. P0 工程验证与仓库卫生。
2. P1 扫描到选股池闭环。
3. P2 选股池复盘中心。
4. P4 最小报表。
5. P3 回测增强。
6. P5 市场发现能力。
7. P6 Legacy 下线与平台化。
## P6 Migration Update - 2026-05-04

当前状态更新：P6 已完成第一轮 legacy 边界收敛，并新增 SQLite legacy picks 到 MySQL 目标 schema 的迁移 dry-run planner。

已交付：
- `scripts/migrate_sqlite_to_mysql.py` 默认 dry-run，只读生成迁移计划。
- 支持 picks 字段映射、默认租户映射、策略 id 解析报告、归档跳过、重复 key 报告。
- `tests/test_sqlite_to_mysql_migration.py` 锁定 dry-run 不写源库、字段映射和去重行为。
- `scripts/validate_mysql_schema.py` 已要求目标库迁移到 `0002_picks_v1_contract_fields`，并检查 picks v1 columns 和唯一约束。

下一步仍不能直接宣称生产迁移完成。后续 P6 补强顺序：
- 在 staging MySQL 执行 `--apply` 写入迁移。
- 对账源/目标行数、关键字段、默认 `tenant_id`、重复 key 跳过和 `strategy_id` 解析。
- 做幂等重跑、备份恢复、回滚演练。
- 对账通过后再推进 SQLite 读写切流和 legacy 数据层下线。
## P6 Staging Migration Result - 2026-05-04

真实 Docker Compose staging 已跑通：
- 默认 pipeline 通过，`unresolved_strategy_rows=0`。
- apply pipeline 通过，首次 `inserted=6`、`existing=0`。
- verify reconciliation 通过，`matched_rows=6`、`missing_rows=0`、`mismatch_rows=0`。
- 幂等重跑通过，第二次 `inserted=0`、`existing=6`。
- 数据库层抽查通过，MySQL `picks` 共 6 条，均为 `tenant_id=1/source=auto_scan`。
- `0003_picks_legacy_payload_json` 已落地，legacy-only 字段进入 `legacy_payload_json`，staging 迁移 `issues=0`。
- 结果记录在 `docs/product/STAGING_MIGRATION_REPORT.md`。

剩余生产切流前问题：
- 生产切流前仍需备份恢复演练和读写切换方案确认。

## P6 Staging Pipeline Update - 2026-05-04

已交付：
- 新增 `scripts/staging_mysql_migration.py`，把 staging 顺序固化为 Alembic upgrade、seed、schema validate、resolve dry-run。
- 默认模式不写 picks；只有显式 `--apply --confirm-apply sqlite-to-mysql-picks` 才进入写入和 verify。
- pipeline 会在 `unresolved_strategy_rows > 0`、target preconditions 失败或 reconciliation 失败时返回非 0。
- 部署 preflight 已把 staging migration pipeline 纳入必备脚本检查。

标准执行：

```powershell
.\venv\Scripts\python.exe scripts\staging_mysql_migration.py
.\venv\Scripts\python.exe scripts\staging_mysql_migration.py --apply --confirm-apply sqlite-to-mysql-picks
```

## P6 Target Seed Update - 2026-05-04

已交付：
- MySQL seed 脚本幂等创建默认策略 `2560` 和 `first_limit_up`。
- schema validator 增加默认 tenant 与默认策略 seed 检查。
- migration apply gate 增加目标 tenant/strategy seed precondition，缺失时阻塞写入。
- 单测覆盖默认策略 seed 幂等性、缺 tenant 阻塞、precondition 成功路径。

后续 staging 顺序：
- 跑 Alembic 到 `0002_picks_v1_contract_fields`。
- 跑 `scripts/bootstrap_mysql_seed.py`。
- 跑 `scripts/validate_mysql_schema.py`。
- 再跑 `scripts/migrate_sqlite_to_mysql.py --resolve-strategies --json`。

## P6 Migration Gate Update - 2026-05-04

已交付：
- `--apply` 增加 `--confirm-apply sqlite-to-mysql-picks` 二次确认，避免误触写入。
- 写入前阻塞校验已落地，未解析策略、无效源行、内部映射错误会阻止写入并返回非 0。
- 写入或 `--verify` 后会生成 reconciliation，对比计划行与目标库实际行，报告缺失和字段不一致。
- 迁移测试覆盖 apply 门禁、对账缺失、字段 mismatch、SQLite 表名安全和缺表 count。

后续仍按原顺序推进：
- staging MySQL 先跑 `--resolve-strategies --json`。
- 阻塞项清零后再跑 `--apply --confirm-apply sqlite-to-mysql-picks --json`。
- 保存对账报告并确认行数、关键字段、默认 `tenant_id`、去重结果和 strategy_id 映射一致。
- 完成幂等重跑、备份恢复和回滚演练后，再推进 SQLite 读写切流。

## Product Closure Update - 2026-05-04

已补齐本轮遗留体验项：

- 首页 Dashboard 展示候选池数量、扫描任务数量和失败任务数量，失败任务不再只从最近任务页估算。
- K 线页展示行情来源、更新时间、数据质量、入池标记、复盘标记和该股票历史入池记录。
- 报表策略行返回并展示 drilldown，可跳转到选股池筛选和对应策略回测页。
- 回测 API 返回组合级资金曲线、基准曲线、超额收益序列、风险归因和实验参数字段。

P6 SQLite 退役状态：

- 生产环境已经 fail-closed：生产配置禁止 SQLite URL、SQLite repository backend、`INIT_SQLITE_SCHEMA=1` 和 legacy SQLite 写入口。
- 仍保留 SQLite 兼容分支用于本地测试、迁移回滚和生产 soak 前的应急读取。
- 最终删除 SQLite 兼容分支的进入条件：生产 MySQL 主路径连续 soak 通过、备份恢复演练通过、迁移对账报告冻结、legacy 页面替代能力完成。
