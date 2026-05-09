# Legacy 清理记录

## 清理原则

- 不删除旧 Flask/Jinja 入口，避免破坏现有 `app.py` 与历史使用方式。
- 新功能迁移到 `frontend/` + `/api/v1` 后，旧页面进入 legacy 兼容区，只保留回退访问。
- 根目录脚本按用途归档到本清单，后续迁移到 `scripts/`、`backend/application/` 或任务队列时以此为基准。

## 已替代的 Jinja 页面

| 旧页面 | 新入口 | 状态 |
| --- | --- | --- |
| `templates/dashboard.html` | `frontend/src/pages/DashboardPage.jsx` | legacy 兼容保留 |
| `templates/strategies/index.html` | `frontend/src/pages/StrategiesPage.jsx` | legacy 兼容保留 |
| `templates/strategies/run.html` | `frontend/src/pages/ScansPage.jsx` | legacy 兼容保留 |
| `templates/strategies/stock_chart.html` | `frontend/src/pages/StockKlinePage.jsx` | legacy 兼容保留 |
| `templates/strategies/react_stock_chart.html` | `frontend/src/pages/StockKlinePage.jsx` | legacy 兼容保留 |
| `templates/strategies/pool.html` | `frontend/src/pages/PicksPage.jsx` | legacy 兼容保留 |
| `templates/admin/*.html` | `frontend/src/pages/AdminPage.jsx` | legacy 兼容保留 |
| `templates/reports.html` | `frontend/src/pages/ReportsPage.jsx` | legacy 兼容保留 |
| `templates/watchlist.html` | `frontend/src/pages/PicksPage.jsx` + 后续研究详情页 | legacy 兼容保留 |

## 根目录遗留脚本分类

### 已收敛到 `scripts/maintenance/`

- `ensure_extended_schema.py`（根目录保留兼容包装入口）
- `init_tracker_db.py`（根目录保留兼容包装入口）
- `import_picks_csv.py`（根目录保留兼容包装入口）
- `ingest_daily_picks.py`（根目录保留兼容包装入口）
- `bulk_update_reviews.py`（根目录保留兼容包装入口）
- `build_dashboard_html.py`（根目录保留兼容包装入口）

### 建议迁移到 `scripts/research/`

- `content_analytics.py`
- `daily_review_brief.py`
- `master_ledger.py`
- `report_2560.py`
- `review_metrics.py`
- `strategy_digest.py`

### 建议迁移到 `backend/strategies/` 或任务队列

- `strategy_2560.py`
- `strategy_lite.py`
- `run_2560_backtest.py`
- `first_limit_replay.py`
- `first_limit_validate.py`
- `leaderboards.py`

### 建议迁移到统一启动/部署配置

- `start.sh`
- `start_flask.sh`
- `scheduler.py`
- `web_panel.py`
- `ui_demo.py`
- `werkzeug_patch.py`

## 后续执行规则

1. 新开发不得再引用 legacy Jinja 页面作为主入口。
2. 新 API 必须走 `/api/v1`，旧 `/api/*` 仅作兼容。
3. 根目录新增脚本前应优先放入 `scripts/` 或 `backend/application/`。
4. 真正删除旧页面或移动脚本前，需要先完成端到端验收并保留回滚说明。
5. 现阶段对已迁移脚本保留根目录兼容包装入口，调度与新文档优先引用 `scripts/maintenance/` 下的新路径。
