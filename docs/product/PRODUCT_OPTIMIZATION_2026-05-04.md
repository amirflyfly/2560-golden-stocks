# 2560 Strategy 产品优化方案 - 2026-05-04

## 1. 多 Agent 头脑风暴结论

本项目最适合定位为：面向 A 股短线策略的「机会发现 - 策略扫描 - 入池观察 - 复盘验证 - 回测归因」内部投研工作台。

对标主流产品后，结论不是把本项目做成通用行情终端，而是先补齐研究闭环：

- TradingView 的优势在于 screener 过滤器、列集、保存 screen、watchlist 联动和 alerts。
- QuantConnect 的优势在于回测结果页完整呈现 equity curve、trades、logs、performance statistics、drawdown、Sharpe 等验证信息。
- JoinQuant/聚宽的优势在于清洗数据、研究环境、回测、模拟交易和策略运行闭环。

本项目已有：React/Vite 工作台、Flask `/api/v1`、策略扫描、选股池、K 线、回测、报表、租户/权限、审计、市场数据 provider、任务队列和监控。核心缺口集中在四类：

1. 机会发现层仍轻：还缺指数、板块/题材、资金流、龙虎榜、公告新闻和异动提醒。
2. 策略可信度表达不够统一：mock/fallback、样本量、费用、滑点、基准、真实成交约束需要贯穿扫描、入池、回测、报表。
3. 工作流局部断点：导航不写 URL、市场发现跳扫描不能带入真实单标的口径、扫描结果缺少回测入口、选股池批量操作有误触风险。
4. 专业图表和保存视图不足：K 线和回测曲线还只是 MVP，缺少十字光标、缩放、图例、drawdown、保存筛选和提醒。

## 2. 本轮优化方案

本轮只做低风险、高收益、能立即验证的改动，不改数据库 schema，不引入新的第三方图表库。

| 优先级 | 优化项 | 文件 | 状态 |
| --- | --- | --- | --- |
| P0 | 前端导航同步 URL，支持刷新、分享和浏览器返回 | `frontend/src/app/App.jsx`, `frontend/src/components/layout/AppShell.jsx` | 已完成 |
| P0 | 修复市场发现到扫描的误导性 CTA，单标的改为直接看 K 线 | `frontend/src/pages/MarketDiscoveryPage.jsx` | 已完成 |
| P0 | 选股池看板拆分「筛选」和「全选本列」，降低批量复盘误触 | `frontend/src/pages/PicksPage.jsx` | 已完成 |
| P0 | 批量复盘增加显式风险提示 | `frontend/src/pages/PicksPage.jsx` | 已完成 |
| P1 | 扫描结果增加「回测」入口 | `frontend/src/pages/ScansPage.jsx` | 已完成 |
| P1 | 选股池候选列表增加入池理由和 K 线入口 | `frontend/src/pages/PicksPage.jsx` | 已完成 |
| P1 | 回测结果增加“不构成投资建议”、样本量、费用、滑点、基准、数据口径提示 | `frontend/src/pages/StrategiesPage.jsx` | 已完成 |
| P1 | 样式补齐看板卡片和内联操作按钮 | `frontend/src/styles/main.css` | 已完成 |
| P0 | 移除 MySQL 选股创建依赖模块级 last insert id 的并发风险 | `backend/repositories/picks_repo.py`, `backend/application/pick_api_service.py` | 已完成 |
| P0 | 租户切换后重新拉取当前用户权限，避免跨租户按钮权限陈旧 | `frontend/src/app/App.jsx` | 已完成 |
| P1 | 扫描结果增加当前页风险/数据质量过滤、排序和最近扫描恢复查看 | `frontend/src/pages/ScansPage.jsx` | 已完成 |
| P1 | K 线页、研究报表页可见英文文案中文化 | `frontend/src/pages/StockKlinePage.jsx`, `frontend/src/pages/ReportsPage.jsx` | 已完成 |
| P1 | K 线页叠加 MA5/MA20、价格轴、入池日期标记和无数据空状态 | `frontend/src/pages/StockKlinePage.jsx`, `frontend/src/styles/main.css` | 已完成 |

## 3. 后续落地清单

下一轮按以下顺序继续：

1. K 线页升级：接入 `kline-charts` 或补坐标轴、缩放、MA 叠加、入池/复盘标记。
2. 回测页升级：收益曲线改为连线图，增加 drawdown 曲线、图例、交易分布和假设摘要。
3. 报表页升级：中文化剩余英文文案，强化 mock/fallback 独立口径和一键下钻。
4. 保存视图：扫描筛选、选股池筛选、报表周期支持保存为个人视图。
5. 提醒能力：先做选股池状态/价格条件提醒，再考虑 watchlist 级别提醒。
6. 市场发现增强：指数、板块/题材、资金流、龙虎榜、公告和异动提醒。
7. 工程层增强：生产启动 schema gate、真实 worker/queue、完整 tenant-aware strategy/task/backup 路径。

## 4. 验证记录

- `npm run build` 已通过。
- `.\venv\Scripts\python.exe -m pytest tests\test_pick_api_service.py tests\test_api_v1.py::test_pick_create_and_review_update_write_audit_logs tests\test_api_v1.py::test_batch_pick_review_updates_selected_items_and_audits -q -p no:cacheprovider` 已通过。
- 本轮改动前已确认：`.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` 通过，208 个测试通过。
- 本轮改动前已确认：`npm run repo:hygiene` 通过，违规项 0。
- 本轮改动前已确认：`docker compose config --quiet` 通过。

## 5. 对标来源

- TradingView Stock Screener 官方说明：https://www.tradingview.com/support/solutions/43000718866-what-is-the-stock-screener/
- TradingView Watchlist 过滤官方说明：https://www.tradingview.com/support/solutions/43000724549-how-to-scan-watchlist-or-flagged-list/
- TradingView Alerts 官方说明：https://www.tradingview.com/support/solutions/43000520149-creating-and-managing-alerts/
- QuantConnect Backtest Results 官方说明：https://www.quantconnect.com/docs/v2/our-platform/backtesting/results
- JoinQuant 官方首页：https://www.joinquant.com/
- JoinQuant 企业版能力说明：https://joinquant.com/enterprise
