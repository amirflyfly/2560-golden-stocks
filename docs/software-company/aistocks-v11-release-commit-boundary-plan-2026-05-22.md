# AiStocks v1.1 Release Commit 边界整理方案

> 日期：2026-05-22  
> 项目根目录：`D:/AiStocks`  
> 输入依据：  
> - `docs/software-company/aistocks-v11-release-file-boundary-2026-05-21.md`  
> - `docs/software-company/aistocks-v11-git-boundary-audit-2026-05-22.md`  
> - 当前 `git status --short`  
> 约束：本文件仅规划发布 commit 边界与文件清单；不修改业务代码，不执行 `git add/reset/checkout`，不删除文件。

## 1. 当前 Git 状态摘要

当前 `git status --short` 显示工作区仍为 staged / unstaged / untracked 混合状态，包含大量 `MM`、`AM` 文件，不能直接整体提交。关键风险：

- `data/daily_selection.csv`、`data/daily_selection.json` 为运行数据改动，应排除。
- Operation Score 相关文件已进入 added/staged 范围，但疑似历史/P1 功能，需 release owner 单独确认。
- 多份 `docs/software-company/aistocks-v11-*` 仍为 untracked，属于文档/证据候选，需逐份确认，不应自动混入代码发布 commit。
- `.env` 未显示为待提交，但不得纳入；`node_modules/`、Playwright 浏览器缓存、`.workbuddy/`、`test-results/` 等不得纳入。
- 所有 `MM/AM` 文件需逐文件核对 staged 与 unstaged 片段，避免只提交半截或混入非 P0 改动。

---

## 2. A 类：建议纳入 v1.1 P0 release commit

> 原则：仅纳入 v1.1 “可信投研工作台 P0 收敛版”所需的后端、前端、测试、配置和脱敏样例。以下为候选清单，最终提交前仍需逐文件 diff 审阅，尤其是 `MM/AM` 文件。

### 2.1 Backend / API / Service

- `.github/workflows/ci.yml`
- `alembic/env.py`
- `alembic/versions/0022_stock_daily_bar_timestamps.py`
- `alembic/versions/0023_signal_review_links.py`
- `backend/api_v1/blueprint.py`
- `backend/api_v1/routers/market.py`
- `backend/api_v1/routers/monitoring.py`
- `backend/api_v1/routers/reports.py`
- `backend/api_v1/routers/sync.py`
- `backend/api_v1/routers/trading.py`
- `backend/application/backtest_api_service.py`
- `backend/application/data_quality_gate_service.py`
- `backend/application/launch_check_service.py`
- `backend/application/market_api_service.py`
- `backend/application/monitoring_service.py`
- `backend/application/paper_trading_service.py`
- `backend/application/pick_api_service.py`
- `backend/application/report_api_service.py`
- `backend/application/scan_api_service.py`
- `backend/application/strategy_api_service.py`
- `backend/application/sync_api_service.py`
- `backend/db/models/__init__.py`
- `backend/db/models/trading.py`
- `backend/infrastructure/cache/redis_client.py`
- `backend/infrastructure/market_data/fallback_provider.py`
- `backend/infrastructure/tasks/handlers.py`
- `backend/infrastructure/tasks/queue.py`
- `backend/infrastructure/tasks/worker.py`
- `backend/repositories/db.py`
- `backend/repositories/market_data_repo.py`
- `backend/repositories/paper_trading_repo.py`
- `backend/repositories/scan_repo.py`
- `backend/routes/admin.py`
- `backend/services/backup_service.py`

### 2.2 Config / Scripts

- `.env.example`：仅在确认无真实密钥、token、账号、生产地址后纳入。
- `.gitignore`
- `docker-compose.yml`
- `scripts/check_repo_hygiene.py`
- `scripts/deploy_preflight.py`
- `scripts/production_evidence.py`
- `scripts/run_e2e_backend.py`
- `scripts/validate_mysql_schema.py`

### 2.3 Frontend / UI / E2E

- `frontend/e2e/market-sync.spec.js`
- `frontend/e2e/paper-trading.spec.js`
- `frontend/e2e/workflow-closure.spec.js`
- `frontend/nginx.conf`
- `frontend/src/api/client.js`
- `frontend/src/app/App.jsx`
- `frontend/src/components/common/ActionBlocker.jsx`
- `frontend/src/components/common/DataQualityGateBadge.jsx`
- `frontend/src/components/common/LaunchGatePanel.jsx`
- `frontend/src/components/common/RiskDisclaimer.jsx`
- `frontend/src/components/common/RiskNotice.jsx`
- `frontend/src/components/common/index.js`
- `frontend/src/pages/DashboardPage.jsx`
- `frontend/src/pages/MarketSyncPage.jsx`
- `frontend/src/pages/MonitoringPage.jsx`
- `frontend/src/pages/PaperTradingPage.jsx`
- `frontend/src/pages/ReportsPage.jsx`
- `frontend/src/pages/ScansPage.jsx`
- `frontend/src/pages/StockKlinePage.jsx`
- `frontend/src/styles/main.css`

### 2.4 Tests

- `tests/test_api_v1.py`
- `tests/test_backup_restore_drill.py`
- `tests/test_data_quality_gate_service.py`
- `tests/test_deploy_preflight.py`
- `tests/test_deployment_config.py`
- `tests/test_launch_check_service.py`
- `tests/test_limit_up_return_production_gates.py`
- `tests/test_market_data_provider.py`
- `tests/test_paper_trading_limit_up_return.py`
- `tests/test_production_evidence.py`
- `tests/test_report_api_service.py`
- `tests/test_schema_alignment.py`
- `tests/test_stage9_api.py`
- `tests/test_task_queue.py`

---

## 3. B 类：建议排除 / 还原 / 不提交

> 原则：运行数据、缓存、依赖目录、敏感配置、本地测试产物、未纳入边界的临时文档，不进入 v1.1 P0 release commit。

### 3.1 明确排除

- `data/daily_selection.csv`：建议排除，属于运行数据/本地样本状态。
- `data/daily_selection.json`：建议排除，属于运行数据/本地样本状态。
- `.env`：不得纳入，可能包含敏感配置。
- `node_modules/`、`frontend/node_modules/`：不得纳入。
- Playwright 浏览器缓存，例如本机 `ms-playwright/`：不得纳入。
- `.workbuddy/`：不得纳入。
- `test-results/`、`frontend/test-results/`、Playwright report、trace、screenshot、video：不得纳入。
- `.pytest_cache/`、`__pycache__/`、logs、dist/build 产物、临时备份：不得纳入。

### 3.2 当前状态中建议排除或单独确认后排除

- `overview.md`：未在 v1.1 发布边界报告内，建议排除；如 release owner 认为有价值，应转为 D 类证据/说明附件，而不是代码发布 commit 内容。
- `docs/software-company/aistocks-deep-analysis-improvement-prd-plan-2026-05-21.md`：名称不属于 `aistocks-v11-*` 主发布包，建议不进入 v1.1 P0 release commit，除非 release owner 明确确认。

---

## 4. C 类：需 release owner 单独确认

> 原则：疑似历史/P1 功能、边界外文档、`MM/AM` 半暂存文件，必须由 release owner 确认后再决定纳入、排除或拆分提交。

### 4.1 Operation Score 相关文件

以下文件需单独确认；未确认前建议排除出 v1.1 P0 release commit：

- `backend/application/operation_score_service.py`
- `frontend/e2e/operation-score.spec.js`
- `tests/test_operation_score_api.py`
- `tests/test_operation_score_service.py`
- `docs/product/OPERATION_SCORE_UPGRADE_2026-05-09.md`

判断：Operation Score 疑似 2026-05-09 历史功能或 P1 功能，若混入本次 P0 release commit，会扩大发布边界和验证范围。

### 4.2 所有 `MM` / `AM` 文件

当前多处文件既有 staged 又有 unstaged 变更，需确认最终提交片段是否完整一致。重点包括但不限于：

- `.env.example`
- `backend/api_v1/routers/trading.py`
- `backend/application/data_quality_gate_service.py`
- `backend/application/market_api_service.py`
- `backend/application/monitoring_service.py`
- `backend/application/paper_trading_service.py`
- `backend/application/report_api_service.py`
- `backend/application/scan_api_service.py`
- `backend/application/sync_api_service.py`
- `backend/infrastructure/market_data/fallback_provider.py`
- `backend/infrastructure/tasks/handlers.py`
- `backend/infrastructure/tasks/queue.py`
- `backend/infrastructure/tasks/worker.py`
- `backend/repositories/market_data_repo.py`
- `backend/repositories/paper_trading_repo.py`
- `docker-compose.yml`
- `frontend/e2e/workflow-closure.spec.js`
- `frontend/src/api/client.js`
- `frontend/src/pages/MonitoringPage.jsx`
- `frontend/src/pages/PaperTradingPage.jsx`
- `frontend/src/styles/main.css`
- `tests/test_api_v1.py`
- `tests/test_data_quality_gate_service.py`
- `tests/test_deployment_config.py`
- `tests/test_paper_trading_limit_up_return.py`
- `tests/test_task_queue.py`

建议：对每个 `MM/AM` 文件分别查看 `git diff --cached -- <file>` 与 `git diff -- <file>`，确认是否需要把 unstaged 片段纳入同一 release commit，或拆分为后续提交。

### 4.3 Untracked `docs/software-company/aistocks-v11-*`

以下文档为 release 文档/证据候选，但需逐份确认其用途；原则上不与代码发布 commit 混在一起，可作为 D 类证据/报告附件或单独文档 commit：

- `docs/software-company/aistocks-v11-architecture-plan-2026-05-21.md`
- `docs/software-company/aistocks-v11-e2e-smoke-report-2026-05-21.md`
- `docs/software-company/aistocks-v11-git-boundary-audit-2026-05-22.md`
- `docs/software-company/aistocks-v11-incremental-prd-2026-05-21.md`
- `docs/software-company/aistocks-v11-p0-qa-report-2026-05-21.md`
- `docs/software-company/aistocks-v11-production-evidence-execution-plan-2026-05-21.md`
- `docs/software-company/aistocks-v11-production-evidence-local-precheck-2026-05-22.md`
- `docs/software-company/aistocks-v11-production-evidence-readiness-mini-2026-05-21.md`
- `docs/software-company/aistocks-v11-release-diff-review-mini-2026-05-21.md`
- `docs/software-company/aistocks-v11-release-file-boundary-2026-05-21.md`
- `docs/software-company/aistocks-v11-release-regression-report-mini-2026-05-21.md`
- `docs/software-company/aistocks-v11-report-summary-quality-fix-2026-05-21.md`
- `docs/software-company/aistocks-v11-release-commit-boundary-plan-2026-05-22.md`

---

## 5. D 类：仅作为证据 / 报告附件，不进入代码发布 commit

> 原则：报告、审计、预检查、readiness、smoke 结果等可作为 release evidence bundle 或单独 documentation commit，不建议混入核心代码 release commit。

### 5.1 Evidence / Report 文档

- `docs/software-company/aistocks-v11-git-boundary-audit-2026-05-22.md`
- `docs/software-company/aistocks-v11-release-commit-boundary-plan-2026-05-22.md`
- `docs/software-company/aistocks-v11-e2e-smoke-report-2026-05-21.md`
- `docs/software-company/aistocks-v11-p0-qa-report-2026-05-21.md`
- `docs/software-company/aistocks-v11-production-evidence-execution-plan-2026-05-21.md`
- `docs/software-company/aistocks-v11-production-evidence-local-precheck-2026-05-22.md`
- `docs/software-company/aistocks-v11-production-evidence-readiness-mini-2026-05-21.md`
- `docs/software-company/aistocks-v11-release-diff-review-mini-2026-05-21.md`
- `docs/software-company/aistocks-v11-release-regression-report-mini-2026-05-21.md`
- `docs/software-company/aistocks-v11-report-summary-quality-fix-2026-05-21.md`

### 5.2 Product / Runbook 文档

以下文档可作为发布支撑材料，但建议与代码 release commit 分离，或由 release owner 明确确认后进入文档 commit：

- `docs/product/PRODUCTION_EVIDENCE.example.json`
- `docs/product/PRODUCTION_EVIDENCE.md`
- `docs/product/PRODUCTION_EVIDENCE_RUNBOOK_2026-05-09.md`
- `docs/OPTIMIZATION_PLAN.md`
- `docs/software-company/aistocks-analysis.md`
- `docs/software-company/aistocks-architecture-plan.md`
- `docs/software-company/aistocks-v11-incremental-prd-2026-05-21.md`
- `docs/software-company/aistocks-v11-architecture-plan-2026-05-21.md`
- `docs/software-company/aistocks-v11-release-file-boundary-2026-05-21.md`

---

## 6. 建议的安全操作顺序（仅建议，不执行）

1. **冻结当前工作区审阅窗口**：不要直接 `git add .`，先保存当前 `git status --short` 与文件边界计划。
2. **先做排除确认**：确认 `data/daily_selection.*`、`.env`、`node_modules/`、Playwright 缓存、`.workbuddy/`、`test-results/`、`overview.md` 不进入 release commit。
3. **处理 Operation Score 决策**：release owner 明确选择“纳入并扩大验证范围”或“排除/延后到 P1”；默认不纳入 P0。
4. **逐个审阅 `MM/AM` 文件**：分别查看 cached 与 unstaged diff，确认每个文件是否完整纳入 A 类，或拆出后续提交。
5. **按 A 类清单构造代码 release commit**：只选择 P0 后端、前端、测试、配置、脱敏样例；避免使用通配式 `git add .`。
6. **将 D 类文档/证据分离**：如需入库，建议单独 documentation/evidence commit；如仅交付附件，则不进入代码 release commit。
7. **执行 repo hygiene 验证**：在真正提交前运行 hygiene 检查，确认无敏感配置、运行数据、缓存、依赖目录、测试产物。
8. **最终复核**：再次运行 `git status --short` 与 `git diff --cached --name-status`，确认 staged 文件只包含 A 类和经 owner 明确批准的 C 类。

可参考但本次未执行的安全命令类型：

```bash
# 仅查看，不修改
git -C D:/AiStocks status --short
git -C D:/AiStocks diff --cached -- <file>
git -C D:/AiStocks diff -- <file>
git -C D:/AiStocks diff --cached --name-status

# 如 release owner 确认排除某个已 staged 文件，可考虑仅取消暂存，不删除工作区内容
# git -C D:/AiStocks restore --staged -- <file>
```

---

## 7. 当前边界结论

**当前 release commit 边界不可直接 GO。**

原因：

1. 工作区仍存在 staged / unstaged / untracked 混合状态，大量 `MM/AM` 文件未完成片段级审阅。
2. `data/daily_selection.csv`、`data/daily_selection.json` 属于运行数据，必须排除。
3. Operation Score 相关文件已混入 added/staged 范围，但疑似历史/P1 功能，需 release owner 单独确认。
4. untracked `docs/software-company/aistocks-v11-*` 文档较多，应按 D 类证据/报告或单独文档 commit 处理，不应自动进入代码 release commit。
5. `.env`、`node_modules/`、Playwright 缓存、`.workbuddy/`、`test-results/` 等虽未全部出现在当前 status 中，但发布前必须再次确认不得纳入。

建议进入下一步：由 release owner 先确认 C 类文件去留，再由工程执行 A/B/D 分类 staging 与 hygiene 验证。
