# AiStocks v1.1 Git 边界极简审计

> 日期：2026-05-22  
> 依据：`git status --short` 与 `docs/software-company/aistocks-v11-release-file-boundary-2026-05-21.md`  
> 约束：仅审计 Git 文件边界，不修改业务代码。

## 1. 当前 Git 状态摘要

当前工作区存在 staged / unstaged / untracked 混合状态，包含多处 `MM` / `AM` 文件，不能直接整体提交。主要类型包括：

- Backend / scripts / tests / frontend 多处 P0 相关改动。
- `data/daily_selection.csv`、`data/daily_selection.json` 为未暂存运行数据改动。
- Operation Score 相关文件已出现在 staged / added 范围。
- `docs/software-company/aistocks-v11-*` 多份文档仍为 untracked。
- `.env`、`node_modules/`、Playwright 浏览器缓存未显示为待提交文件，但按发布边界不得纳入。

## 2. 可纳入 v1.1 P0 候选范围

以下仅为候选，仍需处理 `MM/AM` 的 staged 与 unstaged 片段一致性：

- 后端 P0 闭环：数据质量门禁、上线检查、行情 fallback、监控、报表、扫描、同步、模拟验证、task queue/worker、相关 repository/model/migration/config/scripts。
- 前端 P0 闭环：Dashboard、Monitoring、Scans、Reports、PaperTrading、MarketSync、StockKline、API client、风险/质量公共组件、样式、nginx。
- 测试与 E2E：data quality gate、launch check、production evidence、deploy preflight、task queue、API v1、paper trading、market sync、workflow closure 等发布相关测试。
- 文档候选：`docs/software-company/aistocks-v11-*` 中与增量 PRD、架构计划、QA、diff review、regression、E2E smoke、production evidence readiness、release file boundary 直接相关的文档；需逐份确认后再 add。
- 脱敏配置样例：`.env.example` 可候选，但必须确认不含真实密钥、token、账号、生产地址。

## 3. 建议排除

- `data/daily_selection.csv`、`data/daily_selection.json`：建议排除，属于本地运行数据/样本状态，不应进入发布 commit。
- `.env`：不得纳入，可能包含敏感配置。
- `node_modules/`、`frontend/node_modules/`：不得纳入，依赖应由 lockfile 和安装命令重建。
- Playwright 浏览器缓存（如本机 `ms-playwright` 目录）：不得纳入，属于本地工具缓存。
- `.pytest_cache/`、`__pycache__/`、logs、frontend test-results、构建产物、浏览器报告、`.workbuddy/` 等运行/缓存/临时产物：不得纳入。
- `overview.md`：未在 v1.1 发布边界报告内，建议排除或单独确认。

## 4. 需 release owner 单独确认

- Operation Score 相关文件：
  - `backend/application/operation_score_service.py`
  - `tests/test_operation_score_api.py`
  - `tests/test_operation_score_service.py`
  - `frontend/e2e/operation-score.spec.js`
  - `docs/product/OPERATION_SCORE_UPGRADE_2026-05-09.md`
  - 结论：疑似历史/P1 功能，需单独确认；未确认前建议排除出 v1.1 P0 commit。
- 所有 `MM/AM` 文件：同一文件既有暂存又有未暂存变更，需逐文件确认最终提交片段，不能按当前 index 直接发布。
- untracked `docs/software-company/aistocks-v11-*`：可作为文档候选，但需按发布边界逐份确认；草稿/重复/未完成证据文档不得自动纳入。
- `docs/software-company/aistocks-deep-analysis-improvement-prd-plan-2026-05-21.md`：名称不属于 `aistocks-v11-*` 主发布包，需单独确认。

## 5. Git 边界 GO / NO-GO 结论

**当前 Git 边界不可 GO。** 原因：

1. 工作区仍是 staged / unstaged / untracked 混合状态，多处 `MM/AM` 未完成提交片段审计。
2. 运行数据 `data/daily_selection.csv/json` 出现在工作区，必须排除。
3. Operation Score 已混入 staged/add 范围，但发布边界报告明确其需单独确认或排除。
4. 多份 untracked release docs 尚未逐份确认是否进入发布。
5. `.env`、node_modules、Playwright 缓存虽未待提交，但仍需在发布前以 repo hygiene 再次确认不得进入。
