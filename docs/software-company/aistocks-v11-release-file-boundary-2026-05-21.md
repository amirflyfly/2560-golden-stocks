# AiStocks v1.1 发布文件边界报告

> 文档角色：高见远（Gao）· 架构师  
> 日期：2026-05-21  
> 目标文件：`D:/AiStocks/docs/software-company/aistocks-v11-release-file-boundary-2026-05-21.md`  
> 范围声明：本报告用于收敛 v1.1 发布文件边界，不声明代码已发布，不替代 E2E、production evidence 或正式 release approval。

---

## 1. 发布范围概览

本轮 v1.1 定位为“可信投研工作台 P0 收敛版”，发布文件边界围绕以下四类交付物收敛：

### 1.1 Backend 边界

纳入后端发布边界的内容主要是：

- 数据质量门禁：`DataQualityGateService` 及扫描、回测、报表、模拟验证等 API 对 `quality_gate` / mock / fallback / unknown 的处理。
- 上线检查与生产监控：`LaunchCheckService`、monitoring/admin 路由、deploy preflight、production evidence 校验链路。
- 模拟验证与 live broker 安全边界：纸面交易、worker、task queue、repository、live broker disabled/dry-run 安全策略。
- 数据同步、行情 fallback、report summary 质量分桶等支撑 P0 验收的后端服务。

不在本轮扩大为完整 legacy 重构、完整 SQLite 退役、实盘自动交易、新外部数据源或 P1 复盘中心/策略生命周期。

### 1.2 Frontend 边界

纳入前端发布边界的内容主要是：

- 首页行动指挥台与导航收敛：突出今日、市场发现、策略扫描、选股池、回测/报表，弱化“交易”表述为“模拟验证”。
- 公共风险/质量组件：风险声明、数据质量 badge、动作阻断、上线门禁面板。
- P0 页面集成：Dashboard、Monitoring、Scans、Reports、PaperTrading、MarketSync、StockKline 等与 v1.1 可信闭环相关的页面。
- 前端 API client、样式与 nginx/build 支撑文件。

不在本轮纳入完整 UI 重设计、移动端、商业化多租户计费或复杂量化 IDE。

### 1.3 E2E / Tests 边界

纳入 E2E / 自动化边界的内容主要是：

- 发布相关 Playwright smoke：登录、workflow closure、market sync、scans、reports、paper-trading、permissions、admin/monitoring。
- 后端关键测试：data quality gate、launch check、production evidence、deploy preflight、task queue、API v1、tenant/live broker/report/paper trading。
- 当前关键状态：`frontend/e2e/workflow-closure.spec.js` route 已 patch，但 E2E 验证阻塞于 Playwright Chromium executable 缺失，尚不能判定 GO。

### 1.4 Docs / Evidence 边界

纳入文档发布边界的内容主要是：

- v1.1 增量 PRD、架构计划、QA 报告、diff review、release regression、E2E smoke report、production evidence readiness 检查。
- release file boundary 本报告自身。
- production evidence 相关 runbook/example/template，但真实目标环境 evidence bundle 尚未落盘，不可作为正式 GO 证据。

---

## 2. 文件清单（按 backend / frontend / e2e / docs 分组）

> 说明：以下清单基于当前仓库状态、v1.1 架构计划、diff review 与发布验证报告收敛；其中部分文件存在 staged/unstaged 混合状态，发布前必须按本边界二次确认 commit scope。

### 2.1 Backend

#### API / Router

- `D:/AiStocks/backend/api_v1/blueprint.py`
- `D:/AiStocks/backend/api_v1/routers/admin.py`
- `D:/AiStocks/backend/api_v1/routers/market.py`
- `D:/AiStocks/backend/api_v1/routers/monitoring.py`
- `D:/AiStocks/backend/api_v1/routers/picks.py`
- `D:/AiStocks/backend/api_v1/routers/reports.py`
- `D:/AiStocks/backend/api_v1/routers/scans.py`
- `D:/AiStocks/backend/api_v1/routers/strategies.py`
- `D:/AiStocks/backend/api_v1/routers/sync.py`
- `D:/AiStocks/backend/api_v1/routers/tasks.py`
- `D:/AiStocks/backend/api_v1/routers/trading.py`
- `D:/AiStocks/backend/routes/admin.py`

#### Application Service

- `D:/AiStocks/backend/application/backtest_api_service.py`
- `D:/AiStocks/backend/application/data_quality_gate_service.py`
- `D:/AiStocks/backend/application/launch_check_service.py`
- `D:/AiStocks/backend/application/market_api_service.py`
- `D:/AiStocks/backend/application/monitoring_service.py`
- `D:/AiStocks/backend/application/paper_trading_service.py`
- `D:/AiStocks/backend/application/pick_api_service.py`
- `D:/AiStocks/backend/application/report_api_service.py`
- `D:/AiStocks/backend/application/scan_api_service.py`
- `D:/AiStocks/backend/application/strategy_api_service.py`
- `D:/AiStocks/backend/application/sync_api_service.py`

#### Infrastructure / Repository / Model

- `D:/AiStocks/backend/db/models/__init__.py`
- `D:/AiStocks/backend/db/models/trading.py`
- `D:/AiStocks/backend/infrastructure/cache/redis_client.py`
- `D:/AiStocks/backend/infrastructure/market_data/fallback_provider.py`
- `D:/AiStocks/backend/infrastructure/tasks/handlers.py`
- `D:/AiStocks/backend/infrastructure/tasks/queue.py`
- `D:/AiStocks/backend/infrastructure/tasks/worker.py`
- `D:/AiStocks/backend/repositories/db.py`
- `D:/AiStocks/backend/repositories/market_data_repo.py`
- `D:/AiStocks/backend/repositories/paper_trading_repo.py`
- `D:/AiStocks/backend/repositories/scan_repo.py`

#### Migration / Config / Scripts

- `D:/AiStocks/alembic/env.py`
- `D:/AiStocks/alembic/versions/0022_stock_daily_bar_timestamps.py`
- `D:/AiStocks/alembic/versions/0023_signal_review_links.py`
- `D:/AiStocks/docker-compose.yml`
- `D:/AiStocks/.env.example`
- `D:/AiStocks/scripts/check_repo_hygiene.py`
- `D:/AiStocks/scripts/deploy_preflight.py`
- `D:/AiStocks/scripts/production_evidence.py`
- `D:/AiStocks/scripts/validate_mysql_schema.py`

### 2.2 Frontend

#### App / API / Common Components

- `D:/AiStocks/frontend/src/api/client.js`
- `D:/AiStocks/frontend/src/app/App.jsx`
- `D:/AiStocks/frontend/src/auth/permissions.js`
- `D:/AiStocks/frontend/src/components/common/index.js`
- `D:/AiStocks/frontend/src/components/common/RiskDisclaimer.jsx`
- `D:/AiStocks/frontend/src/components/common/ActionBlocker.jsx`
- `D:/AiStocks/frontend/src/components/common/DataQualityGateBadge.jsx`
- `D:/AiStocks/frontend/src/components/common/LaunchGatePanel.jsx`
- `D:/AiStocks/frontend/src/components/common/RiskNotice.jsx`
- `D:/AiStocks/frontend/src/styles/main.css`

#### Pages

- `D:/AiStocks/frontend/src/pages/DashboardPage.jsx`
- `D:/AiStocks/frontend/src/pages/MarketSyncPage.jsx`
- `D:/AiStocks/frontend/src/pages/MonitoringPage.jsx`
- `D:/AiStocks/frontend/src/pages/PaperTradingPage.jsx`
- `D:/AiStocks/frontend/src/pages/ReportsPage.jsx`
- `D:/AiStocks/frontend/src/pages/ScansPage.jsx`
- `D:/AiStocks/frontend/src/pages/StockKlinePage.jsx`

#### Frontend Config

- `D:/AiStocks/frontend/package.json`
- `D:/AiStocks/frontend/package-lock.json`
- `D:/AiStocks/frontend/vite.config.js`
- `D:/AiStocks/frontend/playwright.config.js`
- `D:/AiStocks/frontend/nginx.conf`

### 2.3 E2E / Tests

#### E2E Specs

- `D:/AiStocks/frontend/e2e/admin.spec.js`
- `D:/AiStocks/frontend/e2e/auth.spec.js`
- `D:/AiStocks/frontend/e2e/market-sync.spec.js`
- `D:/AiStocks/frontend/e2e/paper-trading.spec.js`
- `D:/AiStocks/frontend/e2e/permissions.spec.js`
- `D:/AiStocks/frontend/e2e/reports.spec.js`
- `D:/AiStocks/frontend/e2e/scans.spec.js`
- `D:/AiStocks/frontend/e2e/workflow-closure.spec.js`

#### Backend / System Tests

- `D:/AiStocks/tests/test_api_v1.py`
- `D:/AiStocks/tests/test_api_v1_e2e.py`
- `D:/AiStocks/tests/test_data_quality_gate_service.py`
- `D:/AiStocks/tests/test_deploy_preflight.py`
- `D:/AiStocks/tests/test_deployment_config.py`
- `D:/AiStocks/tests/test_launch_check_service.py`
- `D:/AiStocks/tests/test_limit_up_return_production_gates.py`
- `D:/AiStocks/tests/test_live_broker_service.py`
- `D:/AiStocks/tests/test_market_data_provider.py`
- `D:/AiStocks/tests/test_paper_trading_limit_up_return.py`
- `D:/AiStocks/tests/test_pick_api_service.py`
- `D:/AiStocks/tests/test_production_evidence.py`
- `D:/AiStocks/tests/test_report_api_service.py`
- `D:/AiStocks/tests/test_schema_alignment.py`
- `D:/AiStocks/tests/test_stage9_api.py`
- `D:/AiStocks/tests/test_task_queue.py`
- `D:/AiStocks/tests/test_tenant_repository.py`

### 2.4 Docs / Evidence

- `D:/AiStocks/docs/software-company/aistocks-v11-incremental-prd-2026-05-21.md`
- `D:/AiStocks/docs/software-company/aistocks-v11-architecture-plan-2026-05-21.md`
- `D:/AiStocks/docs/software-company/aistocks-v11-p0-qa-report-2026-05-21.md`
- `D:/AiStocks/docs/software-company/aistocks-v11-release-diff-review-mini-2026-05-21.md`
- `D:/AiStocks/docs/software-company/aistocks-v11-release-regression-report-mini-2026-05-21.md`
- `D:/AiStocks/docs/software-company/aistocks-v11-e2e-smoke-report-2026-05-21.md`
- `D:/AiStocks/docs/software-company/aistocks-v11-production-evidence-readiness-mini-2026-05-21.md`
- `D:/AiStocks/docs/software-company/aistocks-v11-report-summary-quality-fix-2026-05-21.md`
- `D:/AiStocks/docs/software-company/aistocks-v11-release-file-boundary-2026-05-21.md`
- `D:/AiStocks/docs/product/PRODUCTION_EVIDENCE.example.json`
- `D:/AiStocks/docs/product/PRODUCTION_EVIDENCE.md`
- `D:/AiStocks/docs/product/PRODUCTION_EVIDENCE_RUNBOOK_2026-05-09.md`

---

## 3. 不纳入发布范围的文件/目录

以下内容不应默认进入 v1.1 发布边界，除非 release owner 单独确认：

### 3.1 运行数据 / 缓存 / 临时产物

- `D:/AiStocks/data/cache/`
- `D:/AiStocks/data/daily_selection.csv`
- `D:/AiStocks/data/daily_selection.json`
- `D:/AiStocks/.pytest_cache/`
- `D:/AiStocks/__pycache__/`
- `D:/AiStocks/backend/**/__pycache__/`
- `D:/AiStocks/dist/`
- `D:/AiStocks/logs/`
- `D:/AiStocks/.tmp/`
- `D:/AiStocks/backups/` 中除 `.gitkeep` 以外的运行备份文件

原因：这些属于本地运行状态、测试缓存、构建产物或样本数据，容易污染发布 commit，且不可作为真实 production evidence。

### 3.2 依赖目录 / 本地环境

- `D:/AiStocks/frontend/node_modules/`
- `D:/AiStocks/.env`
- 本机 Playwright 浏览器缓存目录，例如 `C:/Users/amir/AppData/Local/ms-playwright/`

原因：依赖应由 lockfile 与安装命令重建；`.env` 可能包含敏感配置，不进入发布。

### 3.3 历史或疑似非 v1.1 P0 功能

- Operation Score 相关文件默认不作为 v1.1 P0 边界，除非 release owner 确认：
  - `D:/AiStocks/backend/application/operation_score_service.py`
  - `D:/AiStocks/tests/test_operation_score_api.py`
  - `D:/AiStocks/tests/test_operation_score_service.py`
  - `D:/AiStocks/frontend/e2e/operation-score.spec.js`
  - `D:/AiStocks/docs/product/OPERATION_SCORE_UPGRADE_2026-05-09.md`

原因：diff review 已标记其更像 2026-05-09 历史功能，直接混入 v1.1 P0 会扩大发布边界。

### 3.4 P1/P2 预研与非关键实验

- 完整复盘中心 v1、策略生命周期 v1、复杂外部数据源、市场题材/新闻/龙虎榜增强、商业化多租户计费、完整量化 IDE 等相关新增文件。
- 未在本报告 2.x 文件清单列出的实验性脚本、临时验证脚本、草稿文档。

原因：v1.1 当前目标是 P0 可信闭环，不应因 P1/P2 预研扩大发布风险。

---

## 4. 风险边界

### 4.1 Production Evidence 风险

- 当前 production evidence readiness 结论为 `NOT_READY`。
- `scripts/production_evidence.py` 依赖当前运行环境内部 readiness；若脚本不在目标 staging/production 环境执行，不能证明真实 production 状态。
- 真实目标环境 evidence bundle 尚未落盘，例如 `docs/product/PRODUCTION_EVIDENCE.prod.json` 未被确认为合格证据。
- 因此 production evidence 缺失仍是 GO 阻断项，不允许用本地 mini test PASS 替代。

### 4.2 E2E 风险

- `frontend/e2e/workflow-closure.spec.js` 是当前发布相关 E2E 关键文件。
- 当前状态已记录：workflow-closure route 已 patch。
- 但 E2E 验证阻塞于 Playwright Chromium executable 缺失：`C:\Users\amir\AppData\Local\ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe`。
- 因测试未进入用例执行，不能判定 workflow closure 单 spec PASS，也不能判定发布相关 E2E GO。

### 4.3 Mock / Stub / Fallback 风险

- v1.1 允许开发和测试环境使用 mock/stub，但生产主流程必须阻断 mock 数据源。
- fallback/unknown 数据不得静默展示为正常数据，必须在首页、扫描、报表、模拟验证等路径显示警示或二次确认。
- 当前发布边界包含 `DataQualityGateService`、market fallback provider、report summary 质量分桶等文件，commit 时必须避免只提交前端提示而漏掉后端兜底。

### 4.4 外部推送 / Live Broker 风险

- v1.1 不开放实盘自动交易，live broker 必须保持 disabled/dry-run 或等价安全策略。
- 外部推送、日报推送、broker 相关功能只能纳入“模拟验证/通知验证”边界，不得升级为真实交易指令。
- 外部推送失败不能阻塞普通投研读路径，但必须在 E2E/日志中可定位；涉及 token、webhook、broker 配置不得进入文档明文或前端展示。

### 4.5 Git 工作区边界风险

- 当前工作区存在 staged、unstaged、untracked 混合状态，多处 `MM/AM` 文件说明同一文件既有暂存又有未暂存变更。
- 若直接一次性提交，可能混入历史功能、临时数据或半成品修改。
- 发布前必须按本报告文件边界重整 commit scope，尤其区分 v1.1 P0 与 Operation Score/运行数据/文档草稿。

---

## 5. 发布门槛

进入 GO 前至少满足以下门槛：

### 5.1 环境门槛

1. 安装 Playwright Chromium / browsers，消除 executable 缺失阻塞。
2. 确认测试环境依赖完整：frontend dependencies、backend Python dependencies、MySQL/Redis/worker 如测试需要均可用。
3. 确认 `.env` 不进入提交，`.env.example` 仅保留脱敏默认值。

### 5.2 E2E 门槛

1. 单 spec 复测通过：`D:/AiStocks/frontend/e2e/workflow-closure.spec.js`。
2. 发布相关 E2E 通过或有明确豁免：`auth`、`admin`、`permissions`、`market-sync`、`scans`、`reports`、`paper-trading`、`workflow-closure`。
3. `D:/AiStocks/docs/software-company/aistocks-v11-e2e-smoke-report-2026-05-21.md` 补充真实执行时间、命令输出摘要、通过率、失败详情与最终结论，不得停留在骨架。

### 5.3 后端 / Build / Preflight 门槛

1. 后端关键测试通过：data quality gate、launch check、production evidence、deploy preflight、task queue、API v1、tenant、live broker、report、paper trading。
2. 前端 production build 通过。
3. `scripts/deploy_preflight.py` 通过。
4. `scripts/check_repo_hygiene.py` 通过，且发布 commit 不含临时数据、缓存、敏感配置。

### 5.4 Production Evidence 门槛

1. 在目标 staging/production 环境执行 production evidence 采集，而不是仅在普通本机环境采集。
2. 真实 evidence plan 与 bundle 落盘：至少明确目标路径、采集命令、readiness samples、验证命令和结果。
3. evidence 验证通过；若缺失，只能标记为“不可正式 GO / 内部试运行待补证据”。

### 5.5 发布边界门槛

1. 按本报告 2.x 清单确认纳入文件。
2. 按本报告第 3 节排除运行数据、缓存、依赖目录、敏感配置、历史/实验功能。
3. 处理 `MM/AM` 文件，确保 staged 与 unstaged 片段均经过审阅。
4. release notes 记录已知风险、rollback plan、证据路径和 E2E/production evidence 状态。

---

## 6. 结论

当前 v1.1 文件边界**可以收敛**：backend、frontend、E2E、docs 四类边界已可按 P0 可信闭环组织，核心文件集中在数据质量门禁、上线检查、风险声明、模拟验证边界、workflow closure 与发布证据文档。

但当前仍存在阻塞项，不能判定 GO：

1. **环境验证阻塞**：`workflow-closure` route 已 patch，但 Playwright Chromium 缺失导致 E2E 未进入真实用例执行，发布相关 E2E 未证明通过。
2. **Production evidence 未落盘**：目标 staging/production 环境的真实 production evidence bundle 尚未形成并验证通过。
3. **工作区边界需整理**：当前 Git 工作区混有 staged/unstaged/untracked 变更，且存在疑似历史功能与运行数据，发布前必须按本报告边界重整提交范围。

因此当前结论为：**文件边界清晰度已足够进入收敛整理；发布 GO 仍被 E2E 环境验证与 production evidence 缺失阻塞。**
