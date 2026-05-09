# AiStocks 上线改进 PRD

> 文档角色：许清楚（Xu）· 产品经理  
> 文档目的：将现有 AiStocks 系统改造到可上线、可验收、可运维状态  
> 输入来源：`docs/software-company/aistocks-analysis.md`、现有产品/重构/部署文档与当前代码结构阅读  
> 范围说明：本 PRD 仅定义上线改进方案，不包含业务代码修改  
> 版本日期：2026-05-08

## 1. 背景与问题定义

AiStocks 当前已具备 A 股短线策略投研工作台的主体能力：React/Vite 前端、Flask `/api/v1`、MySQL/Alembic、Redis worker、mootdx/akshare 行情 Provider、多租户权限审计、策略扫描、选股池、复盘、回测、报表、监控、模拟交易和 Docker Compose 生产形态。

但系统距离“可上线状态”仍存在上线阻断项：

- 上线边界不清，系统混合投研、复盘、模拟交易、live broker、legacy 管理能力。
- 生产证据尚未闭合，production evidence、MySQL 主路径 soak、生产备份恢复证据仍待完成。
- 数据可信度链路不足，fallback、coverage、回测假设、扫描入池、模拟交易之间缺统一门禁。
- legacy Jinja、旧 `/api`、SQLite 兼容分支仍存在，需明确上线前暴露面和退役路径。
- Git 索引状态异常，当前大量 `2560_strategy/...` 删除与根目录同名文件未跟踪，影响发布可信度。
- 安全边界仍需上线前专项验证，包括租户越权、CSRF、live broker、备份恢复、日志脱敏、代理后 Cookie 行为。

本 PRD 的核心目标不是扩展所有 P1/P2 能力，而是**让现有系统达到可上线、可证明、可回滚、可持续运维的 v1.0 状态**。

## 2. 产品目标与上线边界

### 2.1 本轮产品目标

本轮目标定义为：**AiStocks 内部投研工作台上线版 v1.0**。

目标包括：

1. 用户可稳定完成“行情检查 → 策略扫描 → 候选入池 → K 线查看 → 复盘 → 回测验证 → 报表查看”的端到端业务闭环。
2. 管理员可通过系统内外证据证明当前环境满足上线前置条件：数据库、缓存、任务、schema、备份、恢复、权限、审计、监控和回滚均可验证。
3. 所有投研结果必须展示数据来源、数据质量、风险提示和非投资建议声明，避免用户误把系统输出当作实盘交易建议。
4. 生产环境默认只启用投研辅助、复盘、报表、监控与模拟验证能力，不开放自动实盘交易能力。
5. Legacy 与 SQLite 兼容能力在上线版中只能作为受控过渡能力存在，不允许成为新增主流程。

### 2.2 上线边界

#### 本轮必须纳入

- 登录、租户、角色权限。
- 今日行动指挥台。
- 行情源健康、数据质量和生产证据状态展示。
- 市场发现 MVP。
- 策略扫描、结果解释、入池、K 线跳转。
- 选股池列表、筛选、复盘状态、批量复盘、时间线。
- 策略回测、历史回测、基准对比、参数组对比、风险提示。
- 周/月报表、数据质量区分、导出、下钻。
- 模拟交易的只读/受控验证能力。
- 生产监控、任务、日志摘要、readiness、preflight/evidence 状态。
- 管理员上线检查入口。
- 安全、备份、恢复、回滚、审计、部署文档。

#### 本轮明确不做或默认隐藏

- 不做实盘自动交易上线；live broker 默认禁用、隐藏或强门禁。
- 不做完整量化 IDE。
- 不做完整通用行情终端。
- 不做移动端完整适配，只保证窄屏基础可用或明确不支持。
- 不做商业化多租户套餐/计费/数据源授权管理。
- 不做复杂 BI 自定义报表。
- 不删除所有 SQLite/legacy 兼容代码，除非 production evidence 已通过且另行进入退役任务。

### 2.3 产品原则

1. **先证明可上线，再追求功能增强**：P0 是上线门槛，P1/P2 不阻塞上线。
2. **所有结论必须带证据**：扫描、回测、报表必须显示数据质量、来源和风险。
3. **实盘能力默认关闭**：任何 live broker 能力必须 admin-only、显式配置、二次确认、审计完整。
4. **主流程只走 React + `/api/v1`**：legacy 只保留跳转、只读或受控维护入口。
5. **生产环境 fail-closed**：配置不满足安全/数据/任务/数据库要求时，不允许悄悄降级上线。
6. **验收可自动化优先**：P0 验收尽量通过脚本、E2E、readiness、evidence 文件、审计记录证明。

## 3. 目标用户与核心场景

### 3.1 目标用户

| 用户 | 权限角色 | 核心任务 | 上线版重点 |
| --- | --- | --- | --- |
| 策略研究员 | editor/admin | 扫描、解释候选、回测、查看报表 | 判断策略信号是否值得跟踪 |
| 交易复盘用户 | editor/admin | 管理选股池、更新复盘、查看 K 线 | 快速完成每日复盘闭环 |
| 管理员 | admin | 用户租户、权限审计、上线检查、系统监控 | 证明系统安全可靠可上线 |
| 只读观察者 | viewer | 查看扫描、候选、报表、K 线 | 只读可见，写操作禁用且说明原因 |

### 3.2 核心场景

#### 场景 A：每日投研启动

1. 用户登录系统。
2. 进入今日行动指挥台。
3. 查看交易日、行情源、数据质量、任务健康、失败任务、待复盘数量。
4. 如果存在阻断项，如生产证据失败、fallback 高风险、stale task、schema 异常，系统给出明确提示和下一步。
5. 用户确认今日是否可以继续扫描和复盘。

#### 场景 B：策略扫描到选股池

1. 用户选择策略和扫描参数。
2. 系统检查数据质量、coverage、生产/开发环境门禁。
3. 创建扫描任务。
4. 任务执行后展示结果表、评分、置信度、风险、数据来源、fallback 状态、入选理由。
5. 用户将候选加入选股池或跳转 K 线。
6. 系统记录来源、策略、数据质量、审计日志。

#### 场景 C：选股池到复盘

1. 用户进入选股池。
2. 查看待复盘、观察中、已验证、已淘汰状态。
3. 按日期、策略、风险、来源、数据质量筛选。
4. 更新状态、复盘结论、成交反馈、收益、回撤、持有天数。
5. 系统沉淀复盘时间线和审计记录。
6. 报表可聚合复盘结果。

#### 场景 D：策略验证到报表

1. 用户进入策略页。
2. 选择策略、回测日期、手续费、滑点、持仓约束、基准。
3. 系统输出交易次数、胜率、收益、回撤、夏普、盈亏比、曲线、交易样本、剔除原因。
4. 系统提示数据质量、样本数量、假设条件和非投资建议。
5. 周/月报按策略聚合入池、复盘、收益、风险、数据质量。

#### 场景 E：管理员上线检查

1. 管理员进入上线检查入口。
2. 查看 Git 状态检查、repo hygiene、deploy preflight、production evidence、readiness、schema revision、MySQL/Redis/worker、备份恢复、测试结果。
3. 任一 P0 未通过时，系统显示不可上线原因。
4. 全部通过后，管理员导出或保存上线验收证据。

## 4. 端到端业务闭环

上线版端到端闭环定义为：

```text
登录/租户确认
  -> 今日行动指挥台
  -> 行情与生产状态检查
  -> 策略扫描
  -> 扫描结果解释与风险提示
  -> 加入选股池
  -> K 线和标的详情查看
  -> 复盘状态流转
  -> 策略回测验证
  -> 周/月报表归因
  -> 管理员上线/运维证据
```

闭环完成标准：

- editor/admin 可完成一次完整闭环。
- viewer 可完整查看闭环结果，但不能创建扫描、入池、复盘、回测写操作、管理用户或触发高风险动作。
- 每个关键写操作均有权限校验、CSRF 校验和审计记录。
- 每个关键决策页面均展示数据来源、数据质量、风险提示。
- 管理员可以看到系统是否处于可上线状态。

## 5. 需求池

### 5.1 P0：上线必须完成项

P0 是上线门槛。任一 P0 未完成，不允许宣称系统达到上线状态。

| 编号 | 需求 | 说明 |
| --- | --- | --- |
| P0-01 | Git 仓库与发布基线收敛 | 修复大量旧路径删除与新路径未跟踪的状态，确保 CI/review/release 基线可信 |
| P0-02 | 上线范围与 live broker 强门禁 | 明确上线版不开放实盘交易，live broker 默认隐藏/禁用/强审计 |
| P0-03 | Production evidence 闭环 | 完成生产证据文件、MySQL 主路径 soak、备份恢复、readiness 样本 |
| P0-04 | Migration/seed/schema 启动门禁 | 生产启动前或 readiness 中明确验证 Alembic、seed、schema、repository backend |
| P0-05 | 租户与权限越权专项验收 | 验证所有 v1 主路径、legacy 保留路径、任务和报表无跨租户越权 |
| P0-06 | 数据质量统一门禁 | mock 禁止生产；fallback/coverage 不足时有统一阻断、警示或二次确认 |
| P0-07 | 今日行动指挥台上线状态卡 | 首页必须让用户知道今日是否可扫描、可复盘、可上线 |
| P0-08 | 风险免责声明与非投资建议 | 所有策略、扫描、回测、报表、模拟交易页面展示风险声明 |
| P0-09 | Legacy 暴露面收敛 | legacy 写入口冻结、跳转或 admin-only；旧 `/api` 不承接新功能 |
| P0-10 | 安全生产实测 | CSRF、Cookie、Origin、CSP、CORS、安全头、审计脱敏、备份路径安全验证 |
| P0-11 | 全量回归与上线验收证据 | pytest、frontend build、E2E、preflight、repo hygiene、compose、核心冒烟通过 |
| P0-12 | 管理员上线检查入口 | 管理员可查看 P0 检查状态、失败原因和证据路径 |

### 5.2 P1：上线后首轮增强项

P1 不阻塞 v1.0 上线，但应进入上线后第一个迭代。

| 编号 | 需求 | 说明 |
| --- | --- | --- |
| P1-01 | 复盘 SLA 与待办队列 | T+1/T+5 复盘提醒、逾期、优先级、待办汇总 |
| P1-02 | 策略生命周期管理 | 策略版本、上线、停用、观察、变更原因、最近表现 |
| P1-03 | 数据质量业务看板增强 | coverage、延迟、缺失标的、受影响策略、不可扫描原因 |
| P1-04 | 报表策略决策视图 | 保留/观察/停用建议，数据质量剔除前后对比 |
| P1-05 | 前端页面组件化与统一请求状态 | 拆分 Scans/Picks/Strategies 大页面，统一 loading/error/empty/retry |
| P1-06 | API 契约文档 | OpenAPI 或等价接口文档，统一错误码和字段说明 |
| P1-07 | 任务详情可观测增强 | 幂等 key、worker、重试、事件、失败建议、输入摘要 |
| P1-08 | 用户手册与管理员手册 | 面向真实用户的操作说明和异常排查说明 |
| P1-09 | 导航与信息架构优化 | 将模拟交易降级为验证区，突出工作台/扫描/选股池/报表主线 |
| P1-10 | 统一文案和命名 | AiStocks、2560 Strategy、策略 code、状态文案统一 |

### 5.3 P2：中期平台化项

| 编号 | 需求 | 说明 |
| --- | --- | --- |
| P2-01 | 市场发现增强 | 指数、板块、题材、资金流、龙虎榜、公告新闻、异动提醒 |
| P2-02 | 策略实验室 | 参数版本、实验对比、样本分层、市场环境归因 |
| P2-03 | 组合与风险管理 | 多策略组合、仓位模拟、风险预算、相关性和回撤预警 |
| P2-04 | 领域事件与指标仓库 | 扫描、入池、复盘、回测、交易信号形成事件流 |
| P2-05 | 成熟任务系统 | 评估 Celery/RQ/Arq，引入优先级、延迟、死信和 worker 扩缩容 |
| P2-06 | 可观测性平台 | Prometheus/Grafana、trace id、集中日志、告警规则、SLO |
| P2-07 | 移动复盘体验 | 手机端快速复盘、提醒、状态更新、标的详情查看 |
| P2-08 | 多租户商业化能力 | 配额、策略授权、数据源授权、团队协作、使用统计 |
| P2-09 | 智能复盘助手 | 自动总结候选表现、生成周报草稿、识别复盘模式 |
| P2-10 | Legacy/SQLite 完全退役 | production evidence 通过后删除兼容分支和 legacy 查询 |

## 6. P0 需求详情与验收标准

### P0-01 Git 仓库与发布基线收敛

#### 用户故事

作为管理员/研发负责人，我需要明确当前仓库的真实变更范围，避免发布时混入目录迁移、删除、未跟踪文件等不确定状态。

#### 功能要求

- 清理或确认当前大量 `2560_strategy/...` 删除与根目录同名文件未跟踪的状态。
- 明确项目根目录、CI 工作目录和发布目录。
- repo hygiene 不应因为路径迁移误判。
- 发布分支必须只有本轮明确变更。

#### 验收标准

- `git status --short` 不再显示成批旧路径删除与同名新路径未跟踪的异常组合。
- CI 或本地验证命令基于当前真实项目根目录执行。
- `npm run repo:hygiene` 通过。
- `docker compose config --quiet` 通过。
- 发布说明中记录项目根目录和迁移状态。

### P0-02 上线范围与 live broker 强门禁

#### 用户故事

作为管理员，我需要确保上线版不会误触发真实交易能力，所有 live broker 功能默认关闭并可审计。

#### 功能要求

- 上线版明确标记系统仅用于投研辅助和模拟验证，不构成投资建议。
- `LIVE_TRADING_ENABLED=0`、`LIVE_TRADING_DRY_RUN=1` 为默认生产安全配置。
- live broker 菜单、按钮、API 操作必须 admin-only，并在未启用时隐藏或禁用。
- 任何 live broker 写操作必须写审计。
- 如配置不满足安全要求，readiness 或管理员上线检查应提示不可上线。

#### 验收标准

- 普通 editor/viewer 看不到或无法点击 live broker 实盘操作。
- 未启用 live trading 时，admin 也不能提交真实订单，只能看到禁用原因。
- live broker 相关 API 在非 admin 下返回 403。
- 生产 `.env` 中 live trading 默认关闭和 dry-run 开启。
- 审计日志可查询 live broker 尝试操作记录。

### P0-03 Production evidence 闭环

#### 用户故事

作为管理员，我需要有一份可验证的生产证据，证明当前系统数据库、缓存、任务、备份、恢复、schema 和主路径均满足上线要求。

#### 功能要求

- 使用 `scripts/production_evidence.py` 校验生产证据文件。
- 证据包含 MySQL backup artifact、sha256、大小、恢复校验目标。
- 证据包含 schema validation、migration reconciliation、idempotent rerun、rollback drill。
- 证据包含至少两个 readiness soak 样本。
- readiness 样本必须显示 MySQL、Redis cache、Redis task queue、worker execution、repository backends=MySQL、stale tasks=0。

#### 验收标准

- `scripts/production_evidence.py --evidence <prod-evidence-json>` 返回 passed。
- 证据文件路径在管理员上线检查页可见。
- 证据中最近一次 MySQL dump 可在隔离库恢复成功。
- 证据中 readiness `ready=true` 且所有 checks 通过。
- 未提供证据或证据失败时，上线检查显示“不可上线”。

### P0-04 Migration/seed/schema 启动门禁

#### 用户故事

作为运维人员，我需要确保服务启动或对外可用前，数据库迁移、默认租户、默认策略、schema revision 和 repository backend 都处于正确状态。

#### 功能要求

- 生产部署流程固化 Alembic upgrade、seed、schema validate、应用启动、worker 启动顺序。
- readiness 验证 expected Alembic revision。
- production repository backend 必须是 MySQL 或 auto→MySQL。
- seed 缺失时给出明确失败原因。
- 失败时不允许系统静默以 SQLite 或内存队列降级上线。

#### 验收标准

- `scripts/validate_mysql_schema.py` 通过。
- `/api/v1/readiness` 返回 `checks.schema_revision=true`、`checks.repository_backends=true`。
- 生产环境 `CACHE_BACKEND=redis`、`TASK_QUEUE_BACKEND=redis`、`TASK_EXECUTION_MODE=worker`。
- 删除默认 tenant 或默认策略后，schema/seed gate 能失败并显示原因。
- 文档中明确部署顺序和失败处理方式。

### P0-05 租户与权限越权专项验收

#### 用户故事

作为平台管理员，我需要确保用户只能访问绑定租户的数据，viewer 不能执行写操作，legacy 保留入口不能绕过权限。

#### 功能要求

- 所有 v1 主路径使用登录态和 `X-Tenant-ID` 校验。
- 非绑定租户返回 403。
- viewer 只读，不能创建扫描、入池、复盘、回测写操作、管理用户或触发交易。
- legacy 保留路径必须登录保护、只读、跳转或 410。
- 任务、报表、交易、设置、审计查询不能跨租户泄露。

#### 验收标准

- 自动化测试覆盖 admin/editor/viewer 三类角色。
- 自动化测试覆盖非绑定租户访问失败。
- viewer 写操作返回 403 或前端禁用且后端拒绝。
- legacy 写入口不能绕过登录与权限。
- 审计记录包含用户、租户、动作、资源和结果。

### P0-06 数据质量统一门禁

#### 用户故事

作为策略研究员，我需要知道当前扫描、回测和报表是否基于可信数据，并在数据不可信时被阻断或要求二次确认。

#### 功能要求

- 生产环境禁止 mock provider 和 mock fallback。
- 所有扫描结果、入池候选、K 线、回测、报表展示 provider、actual_provider、data_quality、fallback_used。
- fallback、coverage 不足、主源不可用时显示统一风险警示。
- 高风险数据质量下，入池、回测、模拟交易应阻断或要求二次确认。
- 报表可区分或剔除 fallback/unknown 数据。

#### 验收标准

- `MARKET_DATA_PROVIDER=mock` 或 fallback 包含 mock 时生产启动失败。
- 扫描结果每行展示数据质量字段。
- fallback 时首页和扫描页有醒目警示。
- 报表中 fallback/unknown 不与 primary 混淆。
- 数据质量不足时，用户可看到明确原因和建议动作。

### P0-07 今日行动指挥台上线状态卡

#### 用户故事

作为每日使用者，我希望一进入系统就知道今天是否可以继续扫描和复盘，以及有哪些阻断项。

#### 功能要求

首页升级为今日行动指挥台，展示：

- 当前交易日或最近数据日期。
- API、MySQL、Redis、worker、schema、任务健康。
- 行情源、数据质量、coverage/fallback 状态。
- 今日扫描任务数、失败任务数、运行中任务数。
- 待复盘、观察中、高风险候选数。
- 上线检查状态，仅 admin 可见详细入口。
- 风险免责声明。

#### 验收标准

- 首页首屏能判断“可扫描 / 建议谨慎 / 不可上线”。
- 失败任务数大于 0 时首页可见。
- fallback 或行情异常时首页可见。
- admin 可点击进入上线检查入口。
- viewer 只能查看，不显示可写快捷动作或按钮禁用说明明确。

### P0-08 风险免责声明与非投资建议

#### 用户故事

作为用户，我需要明确系统输出仅用于研究和复盘，不构成投资建议，避免误用扫描、回测或模拟交易结果。

#### 功能要求

- 登录页或首次进入系统展示风险声明。
- 扫描、回测、报表、模拟交易、K 线页展示简明风险提示。
- 回测结果必须说明历史表现不代表未来收益。
- 数据质量异常时风险提示升级。
- 导出报表包含免责声明。

#### 验收标准

- 关键页面存在可见的非投资建议提示。
- 回测页显示“回测不代表未来收益”。
- 报表导出文件包含 disclaimer 字段或页脚。
- fallback/unknown 数据下提示风险更高。
- E2E 或组件测试能验证关键文案存在。

### P0-09 Legacy 暴露面收敛

#### 用户故事

作为管理员，我需要确保旧页面和旧 API 不再承接主流程，不增加安全和维护风险。

#### 功能要求

- 主流程统一进入 React `/app` 或 frontend SPA。
- 旧 `/api` 返回 deprecated/410 或 successor link。
- legacy Jinja 页面只读、跳转或 admin-only。
- legacy 写入口必须登录保护、权限保护和审计，能冻结则冻结。
- legacy 保留清单必须在文档和管理员页面可见。

#### 验收标准

- legacy 主流程页面跳转 React。
- legacy `/api` 不支持新增主功能。
- 未登录访问 legacy 敏感入口失败。
- legacy 写入口要么 410，要么 admin-only 且有审计。
- 上线检查显示 legacy 保留项与风险等级。

### P0-10 安全生产实测

#### 用户故事

作为管理员，我需要确认系统在真实 HTTPS 网关和生产配置下，安全基线可用且不会被绕过。

#### 功能要求

- 验证 Session Cookie Secure、HttpOnly、SameSite。
- 验证 CSRF token 写操作保护。
- 验证 Origin/Referer/Sec-Fetch-Site 策略。
- 验证 CSP、X-Frame-Options、X-Content-Type-Options、HSTS。
- 验证 CORS 仅允许白名单。
- 验证日志和审计敏感字段脱敏。
- 验证备份恢复路径安全和高风险操作确认。

#### 验收标准

- 跨站写请求被拒绝。
- 缺 CSRF 的写操作被拒绝。
- 非白名单 Origin 不允许带凭证访问 API。
- 安全头在 frontend 和 backend 响应中存在且一致策略可解释。
- 日志摘要中 password/token/cookie/database_url 不明文出现。
- 备份/恢复操作仅 admin 可见并有审计。

### P0-11 全量回归与上线验收证据

#### 用户故事

作为上线负责人，我需要一组明确命令证明当前版本已通过工程、功能、安全、部署验收。

#### 功能要求

上线前至少运行并归档：

- 后端 pytest。
- 前端 build。
- Playwright E2E 核心路径。
- repo hygiene。
- deploy preflight。
- docker compose config。
- Docker build 或 staging compose 启动冒烟。
- production evidence。
- 核心业务手工或自动冒烟。

#### 验收标准

- 所有命令返回 0。
- 失败项必须有修复记录，不允许标记“无关”后跳过。
- 验收报告包含命令、执行时间、环境、结果、负责人。
- 管理员上线检查入口可展示最近结果或证据路径。

### P0-12 管理员上线检查入口

#### 用户故事

作为管理员，我需要一个集中页面查看系统是否满足上线要求，而不是分散查看多个脚本和文档。

#### 功能要求

管理员上线检查入口展示：

- Repo/Git 状态检查。
- Hygiene/preflight 状态。
- Production evidence 状态。
- Readiness 状态。
- MySQL/Redis/worker/schema 状态。
- 数据质量和 provider 状态。
- Legacy 保留风险。
- Live broker 配置状态。
- 最近测试结果和证据路径。
- 一键复制验收摘要。

#### 验收标准

- 入口仅 admin 可见。
- 任一 P0 失败时显示“不可上线”。
- 每项失败显示原因、建议动作和证据来源。
- 全部通过时显示“满足上线前置条件”。
- 检查结果不泄露密钥、token、数据库密码。

## 7. UI/交互改进要求

### 7.1 今日行动指挥台

#### 信息架构

首页首屏建议分为四块：

1. **今日状态结论**  
   - 状态：可正常使用 / 谨慎使用 / 不可上线 / 不可扫描。
   - 原因摘要：如 fallback、stale task、生产证据失败、schema 不匹配。

2. **行动入口**  
   - 创建扫描。
   - 查看待复盘。
   - 查看市场发现。
   - 运行回测。
   - 查看报表。
   - 管理员上线检查。

3. **风险与数据质量**  
   - provider chain。
   - actual provider。
   - data_quality。
   - fallback_used。
   - coverage/更新时间。
   - 非投资建议提示。

4. **待办和异常**  
   - 待复盘。
   - 观察中高风险。
   - 失败任务。
   - 运行中/卡住任务。
   - 最近扫描。

#### 交互要求

- 使用颜色表达状态，但不能只依赖颜色，必须有文字说明。
- 高风险状态显示明确下一步：同步行情、查看监控、联系管理员、等待任务恢复等。
- viewer 看到只读入口；写按钮禁用并说明原因。
- admin 看到上线检查卡片，普通用户只看到系统健康摘要。

### 7.2 风险免责声明

#### 页面要求

- 登录页或首次进入：完整免责声明。
- 首页：简版免责声明。
- 扫描页：结果区顶部提示“策略扫描仅供研究”。
- 回测页：指标区提示“历史回测不代表未来收益”。
- 报表页：导出和页面均带免责声明。
- 模拟交易页：明确“模拟交易不代表真实成交”。

#### 文案示例

> 本系统仅用于策略研究、模拟验证和复盘管理，不构成任何投资建议。行情数据可能延迟、缺失或降级，回测结果不代表未来收益。请勿将扫描、回测或报表结果直接作为实盘交易依据。

### 7.3 数据质量与生产证据展示

#### 用户侧展示

- `primary`：可正常使用。
- `fallback`：谨慎使用，需复核。
- `unknown`：提示数据质量未知。
- `mock`：生产禁止，开发环境仅链路验证。

#### 管理员侧展示

- production evidence 是否通过。
- 最近 readiness 样本。
- MySQL dump/restore 状态。
- schema revision。
- worker/task queue 状态。
- repository backend。
- stale tasks。

### 7.4 管理员上线检查入口

建议放在：

- 导航“运维”分组下新增“上线检查”；或
- 今日行动指挥台 admin-only 卡片跳转；或
- MonitoringPage 增加“上线门禁”tab。

页面状态：

| 状态 | 表达 |
| --- | --- |
| 全部通过 | 绿色：满足上线前置条件 |
| 有警告 | 黄色：可内部试运行，不建议正式上线 |
| 有失败 | 红色：不可上线 |
| 证据缺失 | 灰/黄：待补充证据 |

## 8. 非功能需求

### 8.1 安全

- 生产环境必须使用强 `SECRET_KEY`。
- Session Cookie 生产必须 Secure、HttpOnly、SameSite 合理配置。
- 写操作必须 CSRF 校验。
- 所有 v1 API 必须进行登录和租户绑定校验。
- role-based access control 必须在前后端双重生效。
- live broker 写操作 admin-only、默认关闭、审计完整。
- 审计日志、任务 detail、日志摘要不得明文暴露 password、token、cookie、database_url、redis_url。
- legacy 敏感入口必须登录保护、只读、跳转、410 或 admin-only。

### 8.2 性能

- 今日行动指挥台首屏聚合接口目标响应 < 1.5 秒，若无法聚合则允许分区加载。
- 列表必须分页：扫描、任务、选股池、报表、审计日志。
- 长任务必须异步，不阻塞 HTTP 请求。
- 全市场扫描和行情同步应有 batch、limit、timeout 和进度反馈。
- 前端大表格需避免一次性渲染过多行，上线版默认 page_size 可控。

### 8.3 可靠性

- 生产环境禁止 mock。
- Redis 不可用时生产不可静默退回内存队列。
- MySQL 不可用时 readiness 失败。
- schema revision 不匹配时 readiness 失败。
- stale task 大于 0 时生产 readiness 失败或至少上线检查失败。
- 备份恢复必须先在隔离环境演练，不允许直接覆盖生产。
- 所有高风险脚本默认 dry-run，写入需要显式确认。

### 8.4 可观测性

- readiness 覆盖 database、schema、cache、task_queue、tasks、repository_backends。
- 任务应记录 status、created_at、started_at、heartbeat_at、finished_at、duration、failure_category、events。
- 监控页展示失败任务、stale 任务、日志摘要、市场数据健康。
- 日志使用结构化 JSON 或可解析格式。
- 管理员上线检查展示证据路径和最近执行时间。

### 8.5 部署

- 生产部署必须使用 Docker Compose 或等价编排。
- 仅 frontend gateway 暴露外部端口；MySQL、Redis、backend 仅内部网络访问。
- 外部 TLS 网关负责证书、HTTPS、HSTS、HTTP→HTTPS。
- 部署流程必须包含：拉取版本、依赖安装/镜像构建、迁移、seed、schema validate、启动、readiness、冒烟、证据归档。
- 回滚流程必须明确镜像/代码回滚和数据库兼容策略。

### 8.6 文档

上线前至少具备：

- 用户手册：登录、扫描、入池、复盘、回测、报表。
- 管理员手册：用户租户、审计、监控、上线检查、故障排查。
- 部署 Runbook：发布、迁移、备份、恢复、回滚。
- 风险声明：非投资建议、数据质量、回测假设、模拟交易边界。
- API 契约或接口说明。
- P0 上线验收报告。

### 8.7 合规声明

- 系统输出仅供研究和复盘，不构成投资建议。
- 行情数据来源、延迟、缺失、fallback 风险需对用户可见。
- 回测仅基于历史数据和假设条件，不代表未来收益。
- 模拟交易不代表真实成交。
- 如未来开放 live broker，必须另行完成合规、风控、审批、审计和授权流程。

## 9. 上线验收清单

### 9.1 产品验收

- [ ] 用户可完成端到端闭环：登录 → 首页 → 扫描 → 入池 → K 线 → 复盘 → 回测 → 报表。
- [ ] viewer 可读不可写，禁用原因明确。
- [ ] 首页可判断今日系统状态和数据质量。
- [ ] 扫描、回测、报表均显示风险免责声明。
- [ ] 数据质量 primary/fallback/unknown/mock 表达一致。
- [ ] 管理员可进入上线检查入口。

### 9.2 工程验收

- [ ] Git 工作区和发布分支状态清晰。
- [ ] `npm run repo:hygiene` 通过。
- [ ] 后端 pytest 通过。
- [ ] 前端 build 通过。
- [ ] Playwright E2E 核心路径通过。
- [ ] `docker compose config --quiet` 通过。
- [ ] Docker build 或 staging compose 冒烟通过。

### 9.3 生产证据验收

- [ ] production evidence 校验 passed。
- [ ] MySQL dump 已生成并记录 sha256/大小。
- [ ] MySQL dump 已在隔离环境恢复并校验。
- [ ] readiness 至少两个 soak 样本通过。
- [ ] schema revision 匹配 expected revision。
- [ ] repository backend 全部为 MySQL 或生产 auto→MySQL。
- [ ] Redis cache/task queue/worker 运行正常。
- [ ] stale tasks 为 0。

### 9.4 安全验收

- [ ] 未登录不能访问受保护 API。
- [ ] 非绑定租户访问被拒绝。
- [ ] viewer 写操作被拒绝。
- [ ] 缺 CSRF 写操作被拒绝。
- [ ] 跨站写请求被拒绝。
- [ ] 安全头存在。
- [ ] live broker 默认关闭且不可误触发。
- [ ] 敏感字段不出现在日志摘要和审计展示中。
- [ ] legacy 敏感入口已收敛。

### 9.5 运维验收

- [ ] deploy preflight 通过。
- [ ] 备份恢复 Runbook 可执行。
- [ ] 回滚流程已演练或至少具备隔离演练证据。
- [ ] 监控页显示 database/cache/task/market/logs 状态。
- [ ] 管理员上线检查页可展示最近证据。
- [ ] 发布说明记录版本、时间、负责人、证据路径、已知风险。

## 10. 待确认问题

1. 上线版名称是否统一为 AiStocks，还是继续沿用 2560 Strategy？
2. 本轮是否允许修改 Git 索引/目录结构以收敛 `2560_strategy` 迁移状态？
3. live broker 在 v1.0 中是完全隐藏、只显示禁用状态，还是保留 admin-only 配置查看？
4. production evidence 的目标环境是哪一套：本机 Docker Compose staging、正式生产服务器，还是用户指定环境？
5. 上线检查入口是新增页面，还是放入现有 MonitoringPage/AdminPage？
6. 数据质量不足时，哪些动作必须硬阻断，哪些动作允许二次确认？
7. 是否需要在 v1.0 上线前完全删除 SQLite 写路径，还是按现有门禁保留到 production evidence passed 后再退役？
8. 是否需要支持外部 HTTPS 网关配置检测，还是仅在 runbook 中人工确认？
9. 用户手册和管理员手册是否作为本轮 P0 交付物，还是只要求上线验收清单？
10. 本轮上线是否需要生成正式 Release Notes 和版本号？

## 11. 推荐执行顺序

1. **P0-01 Git/发布基线收敛**：先保证后续所有变更和验证可信。
2. **P0-02/P0-09 安全边界收敛**：live broker、legacy 暴露面先降风险。
3. **P0-03/P0-04 生产证据与启动门禁**：补齐可上线证明。
4. **P0-05/P0-10 权限与安全专项**：完成越权和生产安全实测。
5. **P0-06/P0-07/P0-08/P0-12 UI 与风险展示**：让用户和管理员看得懂上线状态与风险。
6. **P0-11 全量回归**：所有测试、构建、preflight、evidence、冒烟通过。
7. **整理上线验收报告和待确认问题闭环**。

## 12. 成功标准

当满足以下条件时，可以认为 AiStocks 达到本轮“可上线状态”：

- 业务用户可完成核心投研闭环。
- 管理员可证明生产依赖、schema、备份、恢复、任务、监控、安全均可用。
- 数据质量和风险提示在所有关键决策页面可见。
- live broker 和 legacy 能力不会造成误用或越权。
- 全量回归和 production evidence 通过。
- 发布分支清晰、文档完整、回滚路径明确。
