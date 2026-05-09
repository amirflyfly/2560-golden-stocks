# AiStocks 项目现状与不足分析报告

> 产出阶段：项目分析 + 头脑风暴输入  
> 分析角色：许清楚（Xu）· 产品经理  
> 分析范围：仅基于当前仓库文件、文档、配置与代码阅读；本轮未修改业务代码。  
> 生成日期：2026-05-08

## 1. 执行摘要

AiStocks（当前工程多处仍命名为 `2560 Strategy`）已经从早期 Flask + Jinja + SQLite 的本地工具，演进为面向 A 股短线策略研究、扫描、复盘、回测、报表、模拟交易和运维监控的投研工作台。项目具备 React/Vite 前端、Flask `/api/v1`、模块化后端、MySQL/Alembic、Redis 任务与缓存、mootdx/akshare 行情 Provider、权限/租户/审计、Docker Compose 生产形态和较丰富的单测/E2E 资产。

但距离“上线状态”仍存在几个关键缺口：

1. **产品定位清晰但上线边界不清**：文档里已经定义“投研工作台”，但产品仍混合研究、复盘、模拟交易、实盘 Broker 边界、后台运维、Legacy 管理能力，缺少正式上线版的角色、范围、禁用项和风险提示策略。
2. **业务闭环已成型但可信度链路不足**：扫描、入池、复盘、报表、回测已串起来，但数据质量、策略样本有效性、回测假设、实盘不可用边界、复盘 SLA 还没有形成统一决策门禁。
3. **技术架构处在双轨收敛后期**：React + `/api/v1` 是主线，但 legacy Jinja、旧 `/api`、SQLite 兼容分支、根目录历史脚本仍大量存在，维护成本和误用风险高。
4. **生产化证据尚未闭合**：staging 迁移、预检、证据模板齐全，但生产 MySQL 主路径 soak、真实生产备份恢复证据、SQLite 兼容删除门禁仍未完成。
5. **前端工程仍偏“功能堆叠”**：缺少正式设计系统、信息架构分级、统一表单校验、错误态/空态/加载态规范和移动/窄屏策略。
6. **安全与合规已起步但需收敛**：CSRF、安全头、角色、审计已落地；但 live broker、备份恢复、外部推送、敏感配置、日志脱敏和内部 readiness 暴露边界仍需上线前复核。

建议 PRD 阶段采用“**先把内部投研工作台上线闭环做稳，再扩展市场发现和交易增强**”的策略。P0 聚焦上线阻断项；P1 聚焦使用效率、策略可信度和业务指标；P2 聚焦平台化、智能化和增长型能力。

## 2. 当前系统梳理

### 2.1 业务定位

根据 `docs/product/PRD.md` 与 `docs/refactor/ARCHITECTURE.md`，项目定位为：

- 面向 A 股短线策略研究和复盘的投研工作台。
- 核心闭环：市场/行情检查 → 策略扫描 → 候选解释 → 加入选股池 → K 线/标的详情 → 复盘状态流转 → 回测验证 → 周/月报归因 → 运维监控。
- 第一阶段聚焦 `2560`、首板涨停、涨停回马枪、可转债低溢价等策略，后续演进为多策略、多租户、可审计、可运维平台。
- 产品不应定位为通用行情终端，也不应在当前阶段定位为完整量化 IDE 或实盘交易系统。

### 2.2 主要用户角色

当前文档和代码中已有四类角色：

| 角色 | 当前能力 | 主要诉求 |
| --- | --- | --- |
| 策略研究员 | 策略扫描、回测、查看解释字段、看报表 | 判断策略是否值得继续验证 |
| 交易复盘用户 | 入池、更新复盘、查看 K 线、观察状态 | 快速完成每日复盘和结论沉淀 |
| 管理员 | 用户、租户、审计、系统监控、部分备份/恢复 legacy 能力 | 权限、安全、稳定性与上线证据 |
| 只读观察者 viewer | 可读不可写，前端禁用态提示 | 安全查看扫描、候选和报表 |

### 2.3 当前核心模块

#### 前端模块

前端主工程在 `frontend/`：

- `frontend/src/app/App.jsx`：React SPA 主入口与页面路由。
- `frontend/src/api/client.js`：统一 API client、CSRF、租户 Header、请求封装。
- 页面：
  - 今日工作台：`DashboardPage.jsx`
  - 市场发现：`MarketDiscoveryPage.jsx`
  - 策略管理/回测：`StrategiesPage.jsx`
  - 策略扫描：`ScansPage.jsx`
  - 选股池：`PicksPage.jsx`
  - K 线页：`StockKlinePage.jsx`
  - 研究报表：`ReportsPage.jsx`
  - 数据中心：`MarketSyncPage.jsx`
  - 生产监控：`MonitoringPage.jsx`
  - 模拟交易：`PaperTradingPage.jsx`
  - 后台管理：`AdminPage.jsx`
- E2E：`frontend/e2e/*.spec.js` 覆盖 auth、admin、scans、reports、market-sync、paper-trading、tenant-switch、workflow-closure 等。

#### 后端模块

后端主入口：

- `app.py`：创建 Flask app，生产由 gunicorn `app:app` 启动。
- `backend/__init__.py`：应用工厂、安全基线、CSRF、安全头、legacy blueprint 和 v1 API 注册。
- `backend/api_v1/blueprint.py`：注册 `/api/v1` 路由。
- `backend/api_v1/routers/`：v1 API，覆盖 auth、admin、market、monitoring、picks、reports、scans、settings、strategies、sync、tasks、trading。
- `backend/application/`：业务编排服务，如扫描、选股池、回测、报表、监控、任务、模拟交易、实盘 broker adapter 等。
- `backend/repositories/`：SQLite/MySQL 双轨兼容仓储，生产预期走 MySQL。
- `backend/db/models/` + `alembic/versions/`：SQLAlchemy 模型和 MySQL schema 迁移。
- `backend/infrastructure/market_data/`：mootdx、akshare、fallback provider。
- `backend/infrastructure/tasks/`：任务队列、worker、handlers。
- `backend/strategies/`：策略实现。
- `backend/routes/`、`backend/pages/`、`templates/`：legacy Jinja/旧路由兼容与跳转。

### 2.4 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | React 19、Vite 8、原生 CSS、Playwright E2E |
| 后端 | Python 3.11、Flask 3、Gunicorn、SQLAlchemy 2、Alembic |
| 数据库 | MySQL 8.4 生产目标；SQLite legacy/local/test 兼容 |
| 缓存/任务 | Redis；内存 threadpool 作为开发默认；生产预期 standalone worker |
| 行情数据 | mootdx 主数据源、akshare fallback；已禁止 mock provider 作为正式环境配置 |
| 部署 | Dockerfile、docker-compose、frontend Nginx 反代 `/api/v1` |
| 测试 | pytest、Playwright、repo hygiene、deploy preflight、production evidence validator |

### 2.5 运行、测试、部署方式

#### 本地/开发

- 后端：`python app.py` 或脚本 `start_flask.sh`。
- 前端：根目录 `npm run dev` 转发到 `frontend`。
- 构建：根目录 `npm run build`。
- 后端测试：`pytest` 或根目录 `npm run test:backend`（当前脚本偏 Windows venv 路径）。
- 前端构建测试：根目录 `npm test` 实际执行 `npm --prefix frontend run build`。
- E2E：`npm run test:e2e`，由 Playwright 启动后端测试服务。

#### 生产/Compose

`docker-compose.yml` 定义：

- `mysql`：MySQL 8.4，内部网络暴露 3306。
- `redis`：Redis 7，开启 requirepass。
- `backend`：Gunicorn + Flask，内部暴露 8765，healthcheck `/api/v1/readiness`。
- `worker`：`python -m backend.infrastructure.tasks.worker`，负责任务调度/执行。
- `frontend`：Nginx + 静态 React，发布端口 `5174:5174`，反代 `/api/v1` 到 backend。

生产环境通过 `.env.example` 约束：

- 强制 `SECRET_KEY`、管理员初始密码、MySQL/Redis 密码。
- `CACHE_BACKEND=redis`、`TASK_QUEUE_BACKEND=redis`、`TASK_EXECUTION_MODE=worker`。
- repository backend 默认 MySQL。
- live trading 默认关闭且 dry-run。

## 3. 已具备的优势

### 3.1 产品闭环基础较完整

当前系统已经覆盖：

- 今日工作台展示 API、行情、任务、候选池。
- 市场发现 MVP：市场宽度、强势样本、活跃标的、行情质量。
- 策略扫描：创建任务、自动轮询、分页、解释字段、加入选股池、K 线跳转。
- 选股池：人工/扫描入池、去重、状态流转、复盘字段、批量复盘、时间线。
- 策略回测：核心指标、交易样本、收益曲线、手续费/滑点、涨跌停/停牌约束、基准对比、参数组对比、历史回测。
- 报表：周/月聚合、按策略统计、数据质量区分、导出、下钻。
- 权限与审计：admin/editor/viewer，写操作审计。
- 监控：readiness、任务状态、failure_category、日志摘要、stale 任务识别。
- 模拟交易与 live broker 边界：paper trading 已有账户、订单、持仓、信号、退出评估；live broker 默认关闭。

### 3.2 工程治理意识较强

项目已具备：

- 架构规划、PRD、ROADMAP、PROCESS、验收清单、生产证据门禁、部署 Runbook。
- Alembic 迁移到 `0022_stock_daily_bar_timestamps`。
- repo hygiene 脚本和清理脚本。
- deploy preflight 只读检查。
- production evidence 校验框架。
- SQLite 到 MySQL staging 迁移报告和 rollback drill 文档。
- 较多 pytest 与 Playwright E2E 覆盖。

### 3.3 安全基线已起步

已看到以下设计：

- Flask session cookie HttpOnly、SameSite，生产 Secure 默认开启。
- CSRF token cookie + `X-CSRF-Token` 写操作校验。
- Origin/Referer/Sec-Fetch-Site 检查。
- CSP、X-Frame-Options、X-Content-Type-Options 等安全头。
- 多租户 `X-Tenant-ID` + 用户租户绑定校验。
- 角色权限 `require_role`。
- 审计日志服务。
- `.dockerignore` 排除 `.env`、data、backups、vendor、依赖目录等。

## 4. 深度不足分析

### 4.1 产品体验与信息架构不足

1. **首页像“状态聚合”，还不是“今日行动指挥台”**  
   首页展示指标和快捷入口，但缺少交易日上下文、今日任务建议、优先处理队列、风险阻断原因、复盘待办 SLA 和一键工作流。

2. **导航中“Trading”优先级过高，可能误导定位**  
   `App.jsx` 中模拟交易被放在第一个导航组。对当前定位来说，核心应是“市场发现/策略扫描/选股池/复盘/报表”，模拟交易应作为验证增强而非主入口。

3. **扫描结果解释字段丰富但可读性仍偏技术化**  
   解释包含 score、confidence、risk、indicator_groups、strategy code、provider chain 等，但用户真正需要的是“为什么入选、能不能信、下一步做什么、什么时候复盘”。当前 UI 仍有较多指标堆叠风险。

4. **选股池有字段但缺“复盘工作流”产品化**  
   有状态、批量、时间线，但缺少：待复盘优先级、T+1/T+5 提醒、逾期复盘、复盘模板、复盘质量评分、策略结论沉淀到策略页。

5. **K 线页不是完整标的详情页**  
   已有行情、均线、来源、入池和复盘标记，但缺少与扫描解释、历史信号、同策略历史表现、新闻/公告/板块、风险事件的聚合。

6. **报表仍偏“统计表”，缺少管理决策视图**  
   报表有周/月、策略聚合、导出和下钻，但缺少策略淘汰/保留建议、异常归因、数据质量剔除前后对比、用户复盘效率、策略版本变更影响。

7. **错误态和空态没有形成统一体验标准**  
   各页面自行处理 loading/error/message。缺少统一错误分级、可恢复动作、重试入口、联系管理员/查看日志路径。

8. **文案和命名不统一**  
   项目名混用 AiStocks、2560 Strategy、2560 strategy；策略 code 混用大小写和别名；状态值中英文混用；文档仍记录 mojibake 修复任务。

### 4.2 业务闭环不足

1. **缺少上线版北极星指标和业务仪表盘**  
   PRD 中列出入池转化率、复盘完成率、回测使用率等，但系统未看到专门聚合这些产品指标的管理视图。

2. **策略生命周期没有完全闭环**  
   策略有 enabled/deployed/lifecycle 等迹象，但策略从研发、灰度、上线、停用、归档、版本对比、变更影响分析还不够产品化。

3. **扫描 → 入池 → 复盘 → 回测 → 策略优化之间反馈不足**  
   复盘结论没有清晰回流到策略参数、策略版本和下次扫描权重。

4. **市场发现层仍是 MVP**  
   文档也明确后续需补指数、板块/题材、资金流、龙虎榜、公告、新闻、异动提醒、因子筛选。当前机会发现还不足以对标主流投研工具。

5. **模拟交易与真实交易边界需要更明确**  
   Paper trading 已有较多能力，live broker API 也存在。上线版必须明确哪些页面是模拟验证、哪些实盘能力默认不可用、如何展示非投资建议和风险提示。

6. **多租户商业/运营模型缺失**  
   当前租户更多是技术隔离，缺少套餐、额度、数据源权限、策略权限、任务配额、使用审计报表等产品定义。

### 4.3 数据质量与行情体系不足

1. **行情 Provider 可用性不等于数据可信度**  
   health check 能返回 provider ok，但缺少行情覆盖率、缺失率、延迟、前复权一致性、异常价格、停牌/涨跌停状态完整性等质量评分。

2. **fallback 使用有提示，但缺决策门禁**  
   当前 fallback 会降低 confidence、提示风险，但在扫描入池、回测、模拟交易中是否强制阻断或二次确认，还需要统一规则。

3. **历史数据和实时快照口径需要分层**  
   日线同步、分钟线/快照、竞价快照、交易日历、复权方式、证券类型已逐步扩展，但用户界面和业务规则对“使用的是哪类数据”表达不足。

4. **数据中心偏运维，缺业务可理解的数据质量看板**  
   市场同步、coverage、sync state、snapshots 已有 API，但需要把“今天能不能扫描、哪些策略受影响、哪些标的缺数据”翻译成业务语言。

5. **外部数据合规与授权未见明确说明**  
   使用 mootdx、akshare 作为数据源时，需在上线 PRD/运维文档中明确数据授权、可用范围、免责声明和故障降级策略。

### 4.4 后端架构不足

1. **模块化单体方向正确，但 legacy 双轨仍重**  
   `backend/routes`、`backend/pages`、`templates`、根目录旧脚本仍大量存在。虽然很多已跳转/只读/410，但上线后仍增加攻击面、测试面和认知成本。

2. **仓储层兼容逻辑复杂**  
   `picks_repo.py` 典型体现 SQLite/MySQL 双轨、legacy row shape、`legacy_payload_json` 兼容。短期有必要，长期会拖慢迭代并增加数据一致性风险。

3. **领域层较薄**  
   `backend/domain/` 目前基本空置。大量规则散落在 application service、repository、strategy、frontend 中，如状态流转、风险等级、交易约束、数据质量门禁。

4. **任务队列仍有自研轻量队列风险**  
   当前 queue 结合 Redis 状态和 list，开发默认 threadpool。相比成熟队列，缺少并发控制、延迟任务、死信队列、任务幂等可视化、worker 扩缩容策略、任务优先级。

5. **生产启动迁移/seed gate 不完整**  
   文档中仍列出“为生产启动增加 migration/seed 服务或启动前 schema gate”。当前 backend 依赖 readiness 检查 schema revision，但启动编排层面仍需明确迁移顺序。

6. **配置体系分散**  
   `.env.example`、`backend/core/config.py`、docker-compose、worker 参数、paper/live trading 参数较多。缺少配置分组、校验报告和 UI/文档化解释。

7. **同步/扫描/交易之间的一致性事务不足**  
   例如扫描结果入池、生成交易信号、paper order/fill、复盘结果、报表聚合之间没有看到事件总线或领域事件机制，后续复杂化后容易出现状态不一致。

### 4.5 前端架构不足

1. **缺少成熟状态管理与数据请求层**  
   当前以页面内 `useState/useEffect` + `api` client 为主。随着页面增多，缓存、轮询、错误重试、失效刷新、并发请求取消会变复杂。

2. **页面组件过大**  
   `ScansPage.jsx`、`PicksPage.jsx` 等承担数据请求、表单、业务规则、展示、localStorage 工具等多职责，后续维护困难。

3. **设计系统不完整**  
   有 common components，但表格、表单、筛选器、状态标签、权限禁用态、指标卡、告警、空态等没有完整规范和 Storybook/视觉回归。

4. **路由仍是轻量手写 query page**  
   `App.jsx` 通过 `?page=` 管理页面和 payload，短期可行，但不利于深链接、权限守卫、嵌套路由、浏览器行为和复杂状态恢复。

5. **前端安全策略与 CSP 存在妥协**  
   后端 CSP 允许 `'unsafe-inline'` 和 `'unsafe-eval'`，Nginx CSP 相对严格。需统一策略，确认 Vite 构建产物是否可在更严格 CSP 下运行。

6. **国际化/本地化不是系统化处理**  
   文案基本中文，但有英文分组如 Trading、字段 code 英文、状态值英文，需要统一面向中文投研用户的表达。

### 4.6 测试与质量不足

1. **测试资产多，但上线验收证据仍不等于真实通过**  
   文档中大量 `[x]`，但当前任务未实际运行全量测试。PRD/计划阶段需把“已有测试”和“本轮上线前必须重跑并归档证据”分开。

2. **根目录 git 状态异常，影响交付可信度**  
   当前 `git status --short` 显示大量 `2560_strategy/...` 删除和根目录未跟踪文件，疑似项目从子目录迁移到根目录但 Git 索引尚未清理。这会影响 CI、review、上线发布和变更审计。

3. **测试脚本偏 Windows venv 路径**  
   根 `package.json` 中 `test:backend`、`preflight`、`repo:hygiene` 使用 `venv\Scripts\python.exe`，跨平台和容器环境需明确。

4. **E2E 启动依赖本地浏览器路径**  
   `frontend/playwright.config.js` 包含 D 盘 Playwright browser 路径 fallback，CI/容器环境需稳定安装策略。

5. **缺少性能、压力、长稳测试**  
   对扫描任务、行情同步、全市场数据、Redis/MySQL 连接池、worker 并发、前端大表格渲染缺少明确压测基线。

6. **缺少安全测试清单**  
   已有部分 external_push/security 测试，但上线前还需覆盖 CSRF 绕过、租户越权、IDOR、审计脱敏、备份路径穿越、live broker 误触发等。

### 4.7 部署运维不足

1. **生产证据门禁未闭合**  
   `PRODUCTION_EVIDENCE.md` 明确要求生产证据 passed 后才能删除 SQLite 兼容。当前文档显示生产备份恢复、生产 soak 仍未完成。

2. **缺少一键标准发布流水线**  
   有 Docker Compose 和 runbook，但还需明确 CI/CD：构建镜像、打 tag、推 registry、部署、迁移、健康检查、回滚。

3. **缺少迁移/seed 编排服务**  
   生产启动时 Alembic upgrade、seed、schema validate、应用启动、worker 启动之间的顺序和失败处理需要固化。

4. **日志仍是文件 + 摘要，缺少集中化可观测性**  
   JSON rotating file log 已有，但缺少 Prometheus metrics、structured trace id、request id、OpenTelemetry、Grafana/告警规则。

5. **备份恢复能力仍部分 legacy**  
   docs 显示 admin 备份/恢复/TradingAgents 配置仍 legacy 保留。上线前需确认是否暴露给用户、是否可被误操作、是否需要只读/禁用。

6. **容器资源限制未定义**  
   Compose 未见 CPU/memory limits、restart policy、log driver、volume backup policy、healthcheck action、worker 数量扩缩容策略。

### 4.8 安全与合规不足

1. **live broker API 虽默认关闭，但上线风险高**  
   `/trading/live/orders`、cancel、reconcile、fills callback 已存在，虽 require admin，但需确保配置层强制 dry-run、二次确认、审计、IP allowlist 或完全隐藏。

2. **备份/恢复与文件操作风险需复核**  
   备份恢复天然高风险，需要路径安全、压缩包解压安全、权限隔离、审计和只读演练优先。

3. **审计脱敏需系统化**  
   `MonitoringService` 对日志摘要做敏感关键词 redaction，但审计日志、任务 detail、external push delivery、broker audit 是否统一脱敏需复核。

4. **CORS/CSRF/Session 在代理后需实测**  
   外部 TLS 网关终止 HTTPS，frontend HTTP 内网转发。Cookie Secure、SameSite、Origin/Referer、X-Forwarded-Proto 的生产行为需真实验收。

5. **缺少免责声明和投资风险提示**  
   面向股票策略、回测和模拟交易，必须在产品显著位置说明“非投资建议、数据可能延迟或错误、回测不代表未来收益”。

6. **多租户越权是 P0 风险**  
   后端多数 v1 通过 `get_authenticated_tenant_context`，但 legacy、repositories、report、strategy、task 等是否 100% tenant-aware 需要专项审计。

### 4.9 文档与研发过程不足

1. **文档很多，但状态可能过度乐观**  
   多份文档大量 `[x]`，但仍保留“后续仍需推进”的关键项。PRD 阶段需要重建一份“上线版真实状态表”，区分已实现、已验证、待验证、待设计、暂不做。

2. **缺少用户手册/管理员手册**  
   有 runbook 和开发文档，但缺少面向最终用户的“每日怎么用、异常怎么看、复盘怎么填、策略报告怎么看”。

3. **缺少 API 契约文档**  
   `/api/v1` 路由较多，但未见 OpenAPI/Swagger 或机器可读契约。

4. **缺少决策记录与 PRD 的映射关系**  
   ADR 有基础，但每个产品功能、技术任务、验收测试、上线证据之间的 traceability 不完整。

## 5. P0/P1/P2 改进建议

### 5.1 P0：上线阻断项（必须先完成）

| 编号 | 建议 | 验收标准 |
| --- | --- | --- |
| P0-1 | 修复 Git 仓库迁移/索引状态，消除大量旧路径删除与新路径未跟踪的混乱 | `git status --short` 只保留本轮明确变更；CI 能基于真实路径运行 |
| P0-2 | 明确上线范围：内部投研工作台，不开放实盘交易；live broker UI/API 默认隐藏或强门禁 | 普通用户不可见 live broker 操作；生产 `LIVE_TRADING_ENABLED=0` 验证通过 |
| P0-3 | 完成生产 MySQL 主路径证据闭环 | `scripts/production_evidence.py --evidence ...` 返回 passed，包含备份、恢复、readiness、soak 样本 |
| P0-4 | 固化生产迁移/seed 启动顺序 | Compose/CI 中有 Alembic upgrade、seed、schema validate、app/worker 启动顺序；失败时不启动服务或 readiness 不通过 |
| P0-5 | 完成租户越权专项审计 | v1、legacy 保留入口、repositories、tasks、reports、trading 全部覆盖 tenant 测试 |
| P0-6 | 统一数据质量决策门禁 | mock 禁止生产；fallback/coverage 不足时扫描、入池、回测、paper trading 的阻断/确认规则一致 |
| P0-7 | 全量回归并归档上线证据 | pytest、frontend build、E2E、repo hygiene、deploy preflight、docker compose config/build、核心冒烟全部通过 |
| P0-8 | 补齐投资风险与数据免责声明 | 登录后首页、扫描、回测、模拟交易、报表均有清晰非投资建议提示 |
| P0-9 | 收敛 legacy 暴露面 | legacy 写入口 410/登录保护/跳转策略复核；未替代的备份恢复功能默认 admin only 且有审计 |
| P0-10 | 安全配置生产实测 | HTTPS 网关后 Cookie Secure、CSRF、Origin、CSP、安全头、HSTS、CORS 行为通过测试 |

### 5.2 P1：核心体验与可信度提升（上线后首个增强版本）

| 编号 | 建议 | 验收标准 |
| --- | --- | --- |
| P1-1 | 首页升级为“今日行动指挥台” | 显示交易日、行情质量、待复盘、失败任务、今日建议动作和阻断原因 |
| P1-2 | 重构导航优先级 | 工作台/市场发现/扫描/选股池/报表为主线；模拟交易降级到验证区 |
| P1-3 | 选股池增加复盘 SLA 和待办队列 | 支持 T+1/T+5 待复盘、逾期、优先级、批量完成 |
| P1-4 | 策略生命周期产品化 | 策略状态、版本、上线/停用原因、最近表现、回测/复盘反馈聚合 |
| P1-5 | 数据质量看板业务化 | 显示覆盖率、缺失标的、延迟、fallback 影响策略、可扫描/不可扫描判断 |
| P1-6 | 报表增加策略决策视图 | 输出保留/观察/停用建议，展示真实行情 vs fallback 剔除前后表现 |
| P1-7 | 前端拆分大页面并引入统一请求状态 | Scans/Picks/Strategies 拆组件；统一 loading/error/empty/retry |
| P1-8 | API 契约与错误码文档 | 生成或维护 OpenAPI；统一业务错误码、字段说明和分页规范 |
| P1-9 | 任务队列可观测性增强 | 任务详情包含幂等 key、重试、worker、事件、输入摘要、失败建议 |
| P1-10 | 用户手册与管理员手册 | 新用户可按文档完成登录、扫描、入池、复盘、报表、异常排查 |

### 5.3 P2：平台化与竞争力增强（中期规划）

| 编号 | 建议 | 验收标准 |
| --- | --- | --- |
| P2-1 | 市场发现增强层 | 指数、板块/题材、资金流、龙虎榜、公告新闻、异动提醒、因子筛选 |
| P2-2 | 策略实验室 | 策略参数版本、实验对比、样本分层、市场环境归因、策略淘汰机制 |
| P2-3 | 组合与风险管理 | 多策略组合、仓位模拟、风险预算、回撤预警、相关性分析 |
| P2-4 | 领域事件和指标体系 | 扫描、入池、复盘、回测、交易信号形成事件流和产品指标仓库 |
| P2-5 | 成熟任务系统替换或增强 | 引入 Celery/RQ/Arq 等，支持优先级、延迟、死信、worker 扩缩容 |
| P2-6 | 可观测性平台 | Prometheus/Grafana、日志集中化、trace id、告警规则、SLO/SLA |
| P2-7 | 移动/窄屏复盘体验 | 手机端快速复盘、提醒、状态更新和标的详情查看 |
| P2-8 | 多租户商业化能力 | 配额、套餐、数据源授权、策略授权、团队协作和使用统计 |
| P2-9 | 智能复盘助手 | 自动总结候选表现、识别复盘模式、生成周报结论草稿 |
| P2-10 | Legacy/SQLite 完全退役 | 生产证据通过后删除兼容分支，仓储模型和领域 DTO 统一 |

## 6. 建议的改进 PRD 初稿方向

### 6.1 下一版产品目标

建议下一版命名为：**AiStocks 内部投研工作台上线版 v1.0**。

目标：

1. 让用户每天能稳定完成“行情检查 → 策略扫描 → 候选入池 → 复盘 → 报表查看”的核心流程。
2. 让所有策略结论都有数据质量、策略解释、风险提示和复盘证据。
3. 让管理员可以证明系统满足上线所需的安全、备份、监控、回滚和审计要求。
4. 明确系统只提供投研辅助和模拟验证，不提供默认实盘交易能力，不构成投资建议。

### 6.2 v1.0 推荐范围

#### 必做

- 今日行动指挥台。
- 策略扫描可信度门禁。
- 选股池复盘 SLA 与待办。
- 报表决策视图最小版。
- 生产证据闭环。
- 租户/权限/CSRF/数据质量/备份恢复安全验收。
- Legacy 写入口与 live broker 风险收敛。

#### 暂不做或隐藏

- 实盘交易下单。
- 移动端完整适配。
- 完整量化 IDE。
- 复杂 BI 自定义报表。
- 大规模商业多租户套餐。

### 6.3 v1.0 关键验收指标

| 指标 | 目标 |
| --- | --- |
| 核心流程完成率 | 管理员/编辑用户可完成一次端到端扫描、入池、复盘、报表闭环 |
| 数据质量可见性 | 所有扫描、入池、回测、报表结果显示数据源和质量 |
| 高风险误用防护 | mock 禁止生产；fallback 或 coverage 不足时有阻断或二次确认 |
| 权限正确性 | viewer 无写能力；非绑定租户不可访问；admin-only 动作受控 |
| 生产 readiness | MySQL、Redis、worker、schema、任务健康均通过 |
| 备份恢复证据 | 最近一次 MySQL dump 可在隔离环境恢复并通过校验 |
| 回归测试 | 后端、前端、E2E、preflight、evidence validator 全绿 |

## 7. 研发与测试改造计划建议

### 7.1 阶段 A：上线阻断修复

1. 清理/确认 Git 索引迁移状态。
2. 固化 CI 与本地命令，消除平台路径假设。
3. 完成生产证据文件和 soak。
4. 关闭或隐藏 live broker 实盘能力。
5. 租户/权限/legacy 越权测试补齐。
6. 统一免责声明和数据质量门禁。

### 7.2 阶段 B：核心 PRD 实现

1. 首页今日行动指挥台。
2. 选股池复盘待办/SLA。
3. 报表策略决策视图。
4. 数据质量业务看板。
5. 前端统一错误/空态/加载态。
6. API 契约文档。

### 7.3 阶段 C：系统测试与上线验收

1. 单元测试与集成测试。
2. Playwright 核心路径 E2E。
3. Docker Compose staging 完整冒烟。
4. 生产证据门禁。
5. 安全专项测试。
6. 备份恢复与回滚演练。
7. 上线 checklist 签署。

## 8. 关键风险清单

| 风险 | 等级 | 说明 | 建议 |
| --- | --- | --- | --- |
| Git 工作区大量删除/未跟踪 | 高 | 影响发布、CI、代码审查 | P0 先修复 |
| 生产证据未 passed | 高 | 不能证明可上线 | P0 完成 evidence |
| live broker 误触发 | 高 | 可能造成真实交易风险 | 默认隐藏/禁用/强审计 |
| 租户越权 | 高 | 多租户平台核心安全风险 | 专项测试和代码审计 |
| fallback 数据误用 | 高 | 投研结论可信度风险 | 统一门禁与警示 |
| legacy 双轨长期存在 | 中高 | 维护成本、安全面、测试面扩大 | 分阶段退役 |
| 自研任务队列复杂化 | 中 | 扩容和故障恢复能力有限 | 短期增强观测，中期评估替换 |
| 前端页面臃肿 | 中 | 迭代效率下降 | P1 组件化拆分 |
| 文档状态过度乐观 | 中 | 验收误判 | 建立真实状态矩阵 |

## 9. 结论

AiStocks 当前不是从零开始的项目，而是已经具备较完整功能和较强工程治理基础的投研工作台。真正的挑战不在于“再堆功能”，而在于：

1. **收敛上线范围**：明确内部投研辅助，不开放实盘交易，不泛化为通用行情终端。
2. **证明生产可靠**：生产证据、备份恢复、soak、CI、回归、安全验收要闭合。
3. **提升决策可信度**：数据质量、策略解释、复盘证据、回测假设必须成为每个结论的组成部分。
4. **降低双轨复杂度**：逐步退役 legacy/SQLite 兼容，统一 React + `/api/v1` + MySQL 主路径。
5. **把复盘做成核心体验**：从“字段可填”升级为“每日待办、SLA、结论沉淀、策略反馈”。

建议后续 PRD 以 P0 上线阻断项为第一阶段，先让系统达到可安全上线、可证明上线、可持续回归的状态，再进入 P1/P2 的体验增强与平台化扩展。
