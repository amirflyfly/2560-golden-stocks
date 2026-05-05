# 2560 Strategy 产品优化方案

## 对标结论

主流量化和投研产品的价值不是单点页面，而是完整闭环：数据接入、研究筛选、策略回测、模拟或实盘验证、风险归因、复盘沉淀、权限和运维监控。

本项目已经具备策略、扫描、行情源、任务队列、租户权限、审计、监控和 React 前端基础。核心差距在于扫描结果、选股池、复盘、回测和报表之间的流程还需要继续产品化。

## 产品缺口

1. 机会发现层不足：缺市场全景、板块热度、资金流、龙虎榜、公告新闻和因子筛选。
2. 数据质量提示需要统一：mock、fallback、provider chain、confidence、risk_level 必须出现在决策页面。
3. 复盘中心还不够重：选股池已经能编辑复盘字段，但批量复盘、审计和观察池看板仍需补齐。
4. 回测仍缺专业验证能力：还需要基准对比、参数组对比、真实成交约束和历史记录。
5. 报表仍是最小版：需要导出、数据质量区分和向候选/复盘/回测的追溯。
6. 工程双轨仍存在：旧 Jinja、旧 `/api`、SQLite legacy 仍需逐步下线。

## 已落地清单

- [x] 修复 `app.py` 启动时写 `werkzeug_patch.py` 的副作用。
- [x] 根目录 `npm test/dev/build/test:e2e` 转发到正式 `frontend/` 工程。
- [x] `frontend/Dockerfile` 使用 `npm ci`。
- [x] v1 picks API 接入 SQLite picks 仓储，支持创建和列表返回。
- [x] 首页升级为今日工作台。
- [x] 扫描页升级为任务摘要、结果表、风险解释、一键加入选股池。
- [x] 策略页增加回测表单、核心指标、交易样本、历史回测入口。
- [x] 选股池页增加指标卡、人工入池表单和统一候选表。
- [x] 修复本地 `venv` 依赖并恢复后端 pytest 回归。
- [x] 新增只读仓库卫生检查。
- [x] 新增索引清理脚本，支持 dry-run 和 `--apply`。
- [x] 清理已跟踪/暂存运行产物，hygiene 违规项从 13,532 降为 0。
- [x] 父级 Git 仓库新增 CI workflow，覆盖 hygiene、pytest、前端构建、E2E、Compose 和镜像构建。
- [x] 扫描结果增加自动轮询、分页和指定股票 K 线跳转。
- [x] 后端选股池入池支持按日期、代码、来源去重并更新。
- [x] 选股池增加复盘状态流转、成交反馈、收益字段和复盘时间线。
- [x] 选股池创建和复盘更新写入审计日志。
- [x] viewer 可读但不能执行扫描、入池和复盘写操作。
- [x] 报表页增加最小周/月聚合。
- [x] 回测页增加收益曲线、手续费/滑点输入、估算净收益和涨跌停约束提示。
- [x] 前端接入当前租户角色，viewer/editor/admin 页面操作禁用态可见。
- [x] 报表支持 CSV/JSON 导出。
- [x] 回测支持基准代码、基准收益、超额收益和基准曲线对比。
- [x] 报表区分真实行情、fallback、mock 和 unknown 数据质量。
- [x] 回测支持参数组对比。
- [x] 建立 URL map 测试，锁定 legacy admin 和 v1 admin 前缀边界。

## 后续落地清单

- [x] 补齐前端 viewer/editor/admin 禁用态提示。
- [x] 增加观察池看板：待验证、继续观察、已验证、已淘汰。
- [x] 增加 v1 批量复盘接口和前端批量状态流转。
- [x] 报表导出 CSV/JSON。
- [x] 报表区分真实行情、fallback 和 mock。
- [x] 回测加入基准对比。
- [x] 回测加入参数组对比。
- [x] 回测加入真实成交约束建模，支持涨跌停、停牌和显式无效价格剔除统计。
- [x] 回测历史支持详情查看，并关联策略回测审计轨迹。
- [x] 建立 URL map 测试，检查 legacy admin 双前缀风险。
- [x] P6 第一轮边界收敛：新增 `/app` React 入口，legacy K 线页跳转 React，legacy `/api` 标记 deprecated 并收紧 K 线数据写口登录保护。
- [x] 建立 schema 对齐矩阵和 SQLite v1 picks 字段保护测试，显式记录当前 `tenant_id` 数据层缺口。
- [x] legacy `/reports` 跳转 React 报表页，legacy strategy management 写接口和 `/api/scan/*` 路由纳入 deprecated 边界。
- [x] legacy dashboard、edit、deal-review、strategies、strategy pool/run/backtest 页面跳转 React 主流程。
- [x] watchlist legacy 页面只读化，冻结旧研究分析、Agent stream、watch/unwatch 写入口。
- [x] SQLAlchemy/Alembic picks 已补齐 v1 contract 字段和入池去重唯一约束，schema 对齐测试改为正向覆盖。
- [x] 明确 legacy admin 保留策略：用户管理已迁移，备份/恢复/TradingAgents 配置临时保留且标记 deprecated。
- [x] legacy admin 用户页跳转 React admin，旧用户写接口冻结；leaderboards 标记只读。
- [x] 统一修复 React 主入口和导航 mojibake 文案。
- [x] 补足市场发现层 MVP：基于现有行情 provider 输出市场宽度、强势样本、活跃标的和数据质量。
- [x] 修正 v1 扫描口径：优先调用策略注册表，策略不可用或无结果时才降级为行情样本。
- [ ] 继续修复剩余 mojibake 文案，优先处理可见页面和文档。
- [ ] 补足市场发现增强层：指数、板块、题材、资金流、龙虎榜、公告和异动提醒。

## 2026-05-04 多 Agent 头脑风暴追加优化

产品、投研、架构 agent 对本项目形成一致判断：当前最适合定位为 A 股短线策略发现到复盘验证的内部工作台，不应立即扩展成通用行情终端或完整量化 IDE。对标 TradingView、QuantConnect、Stock Rover、Portfolio Visualizer、东方财富、同花顺、雪球、聚宽等产品后，下一阶段优先补齐三条主线：

1. 机会发现：用市场宽度、活跃标的、强势样本、数据质量先承接扫描前判断。
2. 策略可信度：v1 扫描必须优先跑真实策略算法，并统一 `2560`、`first_limit_up` 等策略 code 口径。
3. 复盘效率：选股池升级为观察池看板，支持批量状态、风险和观察标记流转。

本轮已落地：
- [x] 新增 `/api/v1/market-discovery`，输出样本市场宽度、MA20 占比、强势样本、活跃标的和 provider 数据契约。
- [x] 新增 React `市场发现` 页面和导航入口。
- [x] 新增 `/api/v1/picks/batch/review`，批量复盘写入审计日志。
- [x] 选股池新增观察池看板、候选多选和批量复盘工具条。
- [x] v1 扫描服务新增策略 code alias，并优先调用 `backend.strategies.registry`。
- [x] 扫描页显示当前扫描口径：策略算法或行情样本兜底。
- [x] Docker build context 排除 `.env` 和 `.env.*`，避免本地密钥进入镜像层。
- [x] MySQL v1 picks/report/stock context 路径开始透传请求 `tenant_id`，避免继续固定 tenant 1。

仍需继续推进：
- [ ] 把 `strategy_repo`、任务队列、备份恢复和 TradingAgents 配置迁到完整 v1/tenant-aware 路径。
- [ ] 为生产启动增加 migration/seed 服务或启动前 schema gate。
- [ ] 将进程内任务执行器迁移到真正的 worker/queue，并避免 Redis 失败静默退回内存。
- [ ] 继续补行情超时、备份安全解压、非法参数 400 契约和 internal readiness 拆分。

## 推荐验证命令

```powershell
.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
npm run repo:hygiene
npm run build
npm test
docker compose config --quiet
```

系统 `PATH` 上的 `python` 启动器仍可能异常，继续显式使用项目 `venv` 更可靠。
## P6 Migration Progress - 2026-05-04

已落地：
- [x] SQLite legacy picks 到 MySQL `picks` v1 contract 的 dry-run planner。
- [x] 迁移脚本默认只读，支持 `--json` 输出；显式 `--apply` 才写入目标 MySQL。
- [x] 映射覆盖默认租户、股票代码/名称、交易日、来源、复盘状态、收益/回撤、验证结果、行情质量和 fallback 标记。
- [x] 迁移前置校验已要求目标库升级到 `0002_picks_v1_contract_fields`。

后续落地清单：
- [x] 在 staging MySQL 上执行 `scripts/migrate_sqlite_to_mysql.py --resolve-strategies --json`，确认策略映射和阻塞 issue。
- [x] 在 staging MySQL 上执行 `--apply` 写入迁移。
- [x] 对账源/目标行数、关键字段、默认 `tenant_id`、重复 key 跳过和 strategy_id 映射。
- [x] 完成幂等重跑、备份恢复、回滚演练，进入 SQLite 读写切流门禁确认。
## P6 Staging Pipeline Progress - 2026-05-04

已落地：
- [x] `scripts/staging_mysql_migration.py` 固化 staging 执行顺序。
- [x] 默认只执行 Alembic、seed、schema validate、resolve dry-run。
- [x] apply 仍需要二次确认 token，并自动追加 verify。
- [x] unresolved strategy、target precondition 失败、reconciliation 失败会阻断 pipeline。

后续落地清单：
- [x] 用真实 staging MySQL 跑通默认 pipeline。
- [x] 保存默认 pipeline 结果，确认 unresolved strategy 清零。
- [x] 跑通 apply pipeline 并验证 reconciliation。
- [x] 完成 apply 幂等重跑验证，第二次 `inserted=0`、`existing=6`。
- [x] 通过 `legacy_payload_json` 保留 legacy-only 字段，staging 迁移 warning 清零。
- [x] SQLite isolated backup/restore drill 通过。
- [x] MySQL staging dump/restore check 通过，恢复库中 picks=7、legacy_payload=7；迁移切片 `source=auto_scan` 为 6。
- [x] 形成 `docs/product/STAGING_MIGRATION_REPORT.md`。

## P6 Target Preconditions Progress - 2026-05-04

已落地：
- [x] 默认策略 seed：`2560`、`first_limit_up`。
- [x] schema validator 检查默认 tenant 和默认策略 seed。
- [x] migration apply gate 检查目标 tenant 和策略 seed。
- [x] 相关单测覆盖 seed 幂等性和 precondition 阻塞/成功路径。

后续落地清单：
- [x] staging MySQL 跑 Alembic、seed、schema validator。
- [x] `--resolve-strategies --json` 确认 unresolved strategy 清零。

## P6 Migration Gate Progress - 2026-05-04

已落地：
- [x] `--apply` 二次确认，避免误触写入目标库。
- [x] 写入前阻塞校验，默认拒绝未解析策略、无效源行和内部映射错误。
- [x] `--verify`/`--apply` 对账报告，输出缺失行和字段不一致。
- [x] 表名安全、缺表 count、apply gate 和 reconciliation 已纳入单测。

后续落地清单：
- [x] 在 staging MySQL 执行 `--resolve-strategies --json` 并清理阻塞项。
- [x] 在 staging MySQL 执行 `--apply --confirm-apply sqlite-to-mysql-picks --json`。
- [x] 保存对账报告并确认行数、关键字段、默认 `tenant_id`、去重结果和 strategy_id 映射。
- [x] 完成幂等重跑、备份恢复和回滚演练；生产切流前保留 soak 与最终冻结报告门禁。

## P6 Staging Migration Closure - 2026-05-04

本轮执行结果：
- [x] `--resolve-strategies --json`：`planned_rows=6`、`unresolved_strategy_rows=0`、`issues=0`、`strategy_map_size=14`。
- [x] `--apply --confirm-apply sqlite-to-mysql-picks --json`：当前 staging 已有前序迁移数据，本轮 `inserted=0`、`existing=6`、`duplicates=0`。
- [x] `--verify --json`：`expected_rows=6`、`matched_rows=6`、`missing_rows=0`、`mismatch_rows=0`、`field_mismatches=0`。
- [x] SQL 对账：MySQL `picks` 总数 7，其中迁移切片 `tenant_id=1/source=auto_scan` 为 6；另 1 行 `csv-import` 是既有 staging 烟测数据。
- [x] 约束与映射：`uk_picks_tenant_date_symbol_source` 存在；重复 key 分组 0；非默认租户行 0；空 `strategy_id` 行 0；孤立 `strategy_id` 行 0；迁移行映射到 `2560 / 2560战法`。
- [x] SQLite isolated backup/restore drill 通过：`restored_drill_rows=1`。
- [x] MySQL dump/restore/rollback drill 通过：dump 恢复到隔离 `restore_check`，恢复后 `auto_scan=6`、重复 key 0、孤立 strategy 0、非默认租户 0。
- [x] 完整 staging pipeline 通过：Alembic、seed、schema validate、resolve、apply、verify 全绿，schema revision 为 `0011_user_engagement_fields`。

切流门禁：
- [ ] 用生产冻结 SQLite 指纹复跑同一套命令。
- [ ] 保留最近一次通过校验的 MySQL dump，并记录恢复耗时。
- [ ] MySQL 读写主路径完成 soak 后，再删除 SQLite 兼容分支。
