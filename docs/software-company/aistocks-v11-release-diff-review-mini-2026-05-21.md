# AiStocks v1.1 发布前极简 Git Diff 审阅（2026-05-21）

## A 工作区变更概览

- `git status --short` 显示工作区非常大：同时存在 staged、unstaged、untracked 三类变更。
- `git diff --stat` 仅统计未暂存变更：38 个文件，约 4282 行新增、140 行删除。
- 关键现象：多处 `MM/AM` 文件表示同一文件既有暂存又有未暂存变更，例如 `.env.example`、`backend/api_v1/routers/trading.py`、`backend/application/data_quality_gate_service.py`、`frontend/src/pages/PaperTradingPage.jsx`、`tests/test_task_queue.py`。
- 另有未跟踪文件：4 个 `frontend/src/components/common/*` 新组件，以及多份 `docs/software-company/*2026-05-21.md` 文档。

## B 明显属于 v1.1 P0 的文件

- 风险声明 / 数据质量门禁 / 上线门禁前端：`frontend/src/components/common/RiskDisclaimer.jsx`、`DataQualityGateBadge.jsx`、`RiskNotice.jsx`、`ActionBlocker.jsx`、`LaunchGatePanel.jsx`、`frontend/src/components/common/index.js`。
- P0 页面集成：`frontend/src/app/App.jsx`、`frontend/src/pages/DashboardPage.jsx`、`frontend/src/pages/MonitoringPage.jsx`、`frontend/src/pages/ScansPage.jsx`、`frontend/src/pages/ReportsPage.jsx`、`frontend/src/pages/PaperTradingPage.jsx`、`frontend/src/styles/main.css`。
- P0 后端门禁与检查：`backend/application/data_quality_gate_service.py`、`backend/application/launch_check_service.py`、`backend/routes/admin.py`。
- P0 自动化 / 模拟盘闭环 / 数据时效：`backend/api_v1/routers/trading.py`、`backend/application/paper_trading_service.py`、`backend/application/strategy_api_service.py`、`backend/application/sync_api_service.py`、`backend/infrastructure/tasks/*`、`backend/repositories/paper_trading_repo.py`、`backend/repositories/market_data_repo.py`。
- 对应测试：`tests/test_data_quality_gate_service.py`、`tests/test_launch_check_service.py`、`tests/test_limit_up_return_production_gates.py`、`tests/test_paper_trading_limit_up_return.py`、`tests/test_task_queue.py`。

## C 疑似历史/无关变更

- Operation Score 相关：`backend/application/operation_score_service.py`、`frontend/e2e/operation-score.spec.js`、`tests/test_operation_score_api.py`、`tests/test_operation_score_service.py`、`docs/product/OPERATION_SCORE_UPGRADE_2026-05-09.md`，更像 2026-05-09 历史功能，不应混入 v1.1 P0 发布 commit，除非用户确认。
- 大范围文档/配置/CI/迁移：`.github/workflows/ci.yml`、`.gitignore`、`alembic/*`、`docs/product/*`、`scripts/*`、`frontend/nginx.conf`，需要确认是否属于本轮发布边界。
- 数据样例：`data/daily_selection.csv`、`data/daily_selection.json` 属运行数据/样例数据，发布前应确认是否需要提交。
- 既 staged 又 unstaged 的 `MM/AM` 文件存在边界不清风险，不能直接一次性提交。

## D 发布前必须确认项

- 最高风险：当前工作区混有 v1.1 P0、历史 Operation Score、配置/CI/迁移、运行数据和未跟踪文档；若直接提交，发布边界不可审计。
- 必须先确认 commit 边界：是否只提交 P0 风险声明、数据质量门禁、上线门禁、模拟盘闭环和相关测试。
- 必须处理 `MM/AM` 文件：明确 staged 与 unstaged 哪一部分属于本轮，避免半成品或历史修改进入发布。
- 必须确认未跟踪前端组件是否纳入提交；否则引用这些组件的页面可能在 clean checkout 下构建失败。
- 必须确认生产环境配置默认值，尤其是 worker 定时、行情时效、模拟盘监控频率、`docker-compose.yml` 和 `.env.example` 的新增项。
