# 验收清单

## 1. 工程环境

- [x] 项目 `venv` 下 pytest 可运行。
- [x] `npm test` 通过。
- [x] `npm run build` 通过。
- [x] `docker compose config --quiet` 通过。
- [x] 本地 dev server 可访问。
- [x] 仓库没有被跟踪或暂存的运行产物、缓存、依赖目录。
- [x] `npm run repo:hygiene` 可检测仓库污染。
- [x] `npm run repo:clean-index` 可 dry-run 清理方案。
- [x] 父级 Git 仓库存在可执行 CI workflow。

## 2. 首页工作台

- [x] 展示 API 状态。
- [x] 展示行情源和数据质量。
- [x] mock/fallback 有明显提示。
- [x] 展示候选池数量。
- [x] 展示扫描任务数量。
- [x] 展示失败任务数量。
- [x] 快捷入口可用。

## 3. 扫描页

- [x] 可创建扫描任务。
- [x] 创建后能看到任务 ID 和状态。
- [x] 自动轮询或手动刷新可得到结果。
- [x] 结果表展示代码、名称、评分、置信度、风险、行情源、理由。
- [x] mock 数据有警示。
- [x] 可一键加入选股池。
- [x] 可跳转指定股票 K 线。
- [x] viewer 无法创建扫描。
- [x] 创建扫描写入审计。

## 4. 选股池

- [x] 可人工加入候选。
- [x] 可从扫描结果加入候选。
- [x] 重复候选可去重或更新。
- [x] 可按策略、状态、风险筛选。
- [x] 可按日期和来源筛选。
- [x] 可更新复盘状态。
- [x] 可填写复盘结论。
- [x] 可填写成交反馈。
- [x] 可查看复盘时间线。
- [x] 更新动作写入审计。

## 5. K 线页

- [x] 可从候选或扫描结果跳转并带入股票代码。
- [x] 展示最新价、涨跌幅、成交量。
- [x] 展示 MA5/MA20/MA25。
- [x] 展示数据来源和更新时间。
- [x] 展示入池和复盘标记。

## 6. 策略页和回测

- [x] 可选择策略。
- [x] 可填写回测参数。
- [x] 非法日期返回明确错误。
- [x] 展示交易次数、胜率、收益、回撤、夏普、盈亏比。
- [x] 展示交易样本。
- [x] 展示风险等级和行动建议。
- [x] 样本过少时提示低置信度。
- [x] 展示收益曲线。
- [x] 支持手续费和滑点输入。
- [x] 支持涨跌停、停牌和显式无效价格约束剔除，并展示剔除摘要。
- [x] 支持基准对比。
- [x] 支持参数组对比。
- [x] 可查看历史回测详情。
- [x] 回测写入审计。

## 7. 报表

- [x] 周报可生成。
- [x] 月报可生成。
- [x] 按策略统计入池数、验证数、胜率、收益、回撤。
- [x] mock/fallback 数据可区分。
- [x] 可从策略报表下钻到选股池和回测。
- [x] 可导出 CSV 或 JSON。

## 8. 权限与租户

- [x] 未登录无法访问受保护 API。
- [x] viewer 只读。
- [x] editor 可执行业务写操作。
- [x] admin 可管理用户和租户。
- [x] 非绑定租户拒绝访问。
- [x] disabled tenant 拒绝访问。
- [x] 写操作缺 CSRF 被拒绝。

## 9. 任务与运维

- [x] 任务列表分页。
- [x] 任务列表可筛选、排序，并返回统一生命周期状态 `queued/running/succeeded/failed/canceled/stale`。
- [x] 任务状态准确。
- [x] 失败任务展示 failure_category。
- [x] 可取消任务。
- [x] stale 任务可识别。
- [x] 日志摘要可读。
- [x] readiness 纳入任务健康摘要，生产环境存在 stale task 时不放行。

## 10. 上线前最终检查

- [x] 所有 P0/P1 缺陷关闭。
- [x] 数据库备份证据口径已固化为 `scripts/production_evidence.py` 校验项；生产实际备份仍需目标环境证据文件。
- [x] 迁移脚本已验证。
- [x] 回滚方案已确认。
- [x] 发布说明已更新。

## 11. Legacy 下线与平台化

- [x] `/app` 可作为 React 正式入口。
- [x] React 可根据 URL 参数打开指定页面和股票 K 线。
- [x] legacy K 线页跳转到 React K 线页。
- [x] legacy `/api` 响应明确标记 deprecated。
- [x] legacy K 线数据读写接口需要登录。
- [x] SQLite legacy picks schema 覆盖 v1 当前依赖字段。
- [x] 当前 picks 数据层缺少 `tenant_id` 已被文档和测试显式记录。
- [x] legacy `/reports` 跳转到 React 报表页。
- [x] legacy strategy management 写接口需要登录。
- [x] legacy `/api/scan/*` 路由标记 deprecated。
- [x] legacy dashboard/strategies/edit/deal-review/strategy pool/run/backtest 页面跳转到 React。
- [x] watchlist legacy 页面只读化。
- [x] leaderboards legacy 页面只读化。
- [x] legacy admin 用户页跳转 React admin，旧用户写接口冻结。
- [x] admin 备份/恢复/TradingAgents 配置 legacy 保留策略。
- [x] SQLAlchemy/Alembic picks 覆盖 v1 DTO 当前依赖字段。
## P6 Migration Acceptance Update - 2026-05-04

- [x] SQLite 到 MySQL picks 迁移 dry-run planner 已落地，默认只读、不写目标库。
- [x] dry-run 覆盖字段映射、默认 `tenant_id=1`、重复 key 报告、归档跳过和策略 id 未解析报告。
- [x] `scripts/validate_mysql_schema.py` 已检查 `0002_picks_v1_contract_fields`、picks v1 columns 和 `uk_picks_tenant_date_symbol_source`。
- [x] `tests/test_sqlite_to_mysql_migration.py` 已覆盖 dry-run 不改 SQLite 源库。
- [x] staging MySQL 写入迁移已验证，证据见 `docs/product/STAGING_MIGRATION_REPORT.md`。
- [x] 迁移后源/目标行数、关键字段、tenant 默认映射和去重约束已对账。
- [x] staging 幂等重跑、SQLite isolated backup/restore 和 MySQL dump/restore check 已完成。
## P6 Staging Pipeline Acceptance Update - 2026-05-04

- [x] staging 迁移顺序已固化为 `scripts/staging_mysql_migration.py`。
- [x] pipeline 默认只执行 Alembic、seed、schema validate 和 resolve dry-run，不写 picks。
- [x] pipeline 对 unresolved strategy、target precondition 失败、reconciliation 失败返回非 0。
- [x] `--apply` 模式仍需要 `--confirm-apply sqlite-to-mysql-picks`。
- [x] deploy preflight 纳入 staging migration pipeline 脚本检查。
- [x] `cryptography` 已纳入依赖，支持 PyMySQL 连接 MySQL 8 `caching_sha2_password`。
- [x] staging MySQL 已实际跑通 pipeline 默认模式。
- [x] staging MySQL 已实际跑通 apply + verify 模式。
- [x] staging MySQL 已验证 apply 幂等重跑：第二次 `inserted=0`、`existing=6`。
- [x] staging MySQL 数据库层抽查通过：`picks` 共 6 条，`tenant_id=1/source=auto_scan`。
- [x] legacy-only 字段已通过 `legacy_payload_json` 保留，staging resolve/apply/verify 均为 `issues=0`。
- [x] staging MySQL 抽查通过：6/6 条 `picks.legacy_payload_json IS NOT NULL`。
- [x] SQLite isolated backup/restore drill 通过。
- [x] MySQL staging dump/restore check 通过，恢复库 `restore_check` 中 picks=6、legacy_payload=6。
- [x] staging 迁移报告已沉淀到 `docs/product/STAGING_MIGRATION_REPORT.md`。

## P6 Target Preconditions Acceptance Update - 2026-05-04

- [x] MySQL seed 脚本幂等创建默认策略 `2560` 和 `first_limit_up`。
- [x] MySQL schema validator 检查默认 tenant 和默认策略 seed。
- [x] migration apply gate 检查目标 tenant 和策略 seed，缺失时阻塞写入。
- [x] 单测覆盖默认策略 seed 幂等性、缺 tenant 阻塞和 precondition 成功路径。
- [x] staging MySQL 已实际执行 seed 和 schema validator。

## P6 Migration Gate Acceptance Update - 2026-05-04

- [x] `--apply` 写入需要 `--confirm-apply sqlite-to-mysql-picks` 二次确认。
- [x] 写入前阻塞校验覆盖未解析策略、无效源行、内部映射错误和无效行跳过。
- [x] 阻塞校验失败时脚本非 0 退出且不写入目标库。
- [x] 迁移脚本可输出 JSON 对账报告，包含 `expected_rows`、`matched_rows`、`missing_rows`、`mismatch_rows` 和字段差异。
- [x] dry-run/apply 报告包含 SQLite 源库 `sha256`、大小和修改时间，用于确认 apply 与 dry-run 使用同一份源数据。
- [x] 单测覆盖 apply 门禁、对账缺失、字段 mismatch、SQLite 表名安全和缺表 count。
- [x] MySQL schema validator 失败路径已纳入单测，覆盖缺表、缺索引、缺字段、缺唯一约束和 Alembic revision 不匹配。
- [x] staging MySQL 写入迁移已执行，统一以 `P6 Staging Pipeline Acceptance Update` 和 `STAGING_MIGRATION_REPORT.md` 为准。
- [x] staging 写入后对账报告确认源/目标行数、关键字段、tenant 默认映射和去重结果一致。
- [x] staging 幂等重跑、备份恢复和回滚演练已完成。

## P6 Production Soak Gates - 2026-05-04

- [x] 生产证据模板、校验脚本和门禁文档已落地：`docs/product/PRODUCTION_EVIDENCE.md`。
- [ ] 生产数据库备份已执行并完成恢复校验，且通过 `scripts/production_evidence.py`。
- [ ] 生产 MySQL 主路径完成 soak，确认写入、备份恢复、迁移回滚演练稳定，且通过 `scripts/production_evidence.py`。
- [ ] 生产证据通过后删除 SQLite 写路径。
- [ ] SQLite 写路径删除后，再删除 `_repo_backend`、legacy repository 分支和 `legacy_payload_json` 兼容查询。
