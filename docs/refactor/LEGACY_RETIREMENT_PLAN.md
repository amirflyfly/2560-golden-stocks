# Legacy 下线计划

## 目标
将旧 Jinja 页面和根目录散落脚本逐步收敛到 React 前端、`/api/v1` API 和 `scripts/` 运维入口，减少双轨维护成本，同时保留可回滚路径。

## 当前原则

1. **只读优先**：旧页面不再新增业务写能力；新增写操作只进入 `/api/v1`。
2. **跳转替代**：已有 React 页面覆盖的功能，旧入口展示提示并引导到新前端。
3. **脚本归档**：根目录脚本继续迁入 `scripts/`，脚本必须有用途说明和安全边界。
4. **保留回滚**：下线期间保留旧蓝图注册，遇到生产事故可临时恢复访问。

## 分阶段动作

### L1：冻结新增
- 禁止在 `backend/routes/` 旧 Jinja 路由新增业务能力。
- 新功能统一落到 `backend/api_v1/routers/` 和 React 页面。
- 文档和 PR 描述必须标明是否触碰 legacy。

### L2：入口提示
- 旧首页、策略、扫描、后台入口增加“新版前端已可用”的提示。
- 写操作入口优先改成跳转或禁用状态。

### L3：脚本迁移
- 根目录临时脚本迁入 `scripts/`。
- 脚本命名使用动词前缀，如 `validate_`、`backup_`、`sync_`。
- 高风险脚本必须默认 dry-run 或只操作项目 `data/`。

### L4：只读窗口
- legacy 只保留只读查询和备份恢复回滚入口。
- 观察至少一个发布周期，确认 React/API 覆盖核心流程。

### L5：移除窗口
- 删除旧写路由和模板。
- 保留 migration note 和回滚标签。

## 第 18 阶段只读盘点清单

> 盘点日期：2026-05-03。当前阶段只读记录，不移动、不删除、不批量改名任何文件。

### 仓库卫生发现

- 生成物/依赖目录：存在根目录 `node_modules/`、`frontend/node_modules/`、`.opencode/node_modules/`、根目录 `dist/`、`frontend/dist/`、`static/dist/`、`.pytest_cache/`、`frontend/test-results/`、大量 `__pycache__/`。
- 缓存/运行数据：`data/` 下存在约 978 个 `*.pkl`、`*.db` 等数据/缓存文件；`logs/` 下存在运行日志；这些应先区分“研究资产”和“可再生成缓存”。
- 虚拟环境：根目录 `venv/` 内存在大量第三方依赖与 `__pycache__`，应纳入本地环境忽略规则，避免污染版本库。
- 根目录前端双轨：根目录仍有 `package.json`、`package-lock.json`、`vite.config.js`、`index.html`、`dist/`，而正式前端已位于 `frontend/`。
- 根目录 Python 入口较多：如 `web_panel.py`、`strategy_2560.py`、`run_2560_backtest.py`、`scheduler.py`、`add_pick.py`、`build_dashboard_html.py` 等，需要区分正式入口、兼容包装、维护脚本和可归档文件。

### Legacy 引用发现

- 应用启动仍注册旧蓝图：`backend/__init__.py` 注册 `main_bp`、旧 `/api`、`/admin`、`strategies_bp`、`strategy_management_bp`、`strategy_scan_bp`，同时注册新 `/api/v1`。
- 应用启动仍调用 SQLite schema 初始化：`backend/__init__.py` 调用 `backend.repositories.db.ensure_schema()`。
- SQLite repository 仍被多处引用：`backend/repositories/*_repo.py`、`backend/pages/*`、`backend/routes/*`、`backend/services/*` 仍依赖 `backend.repositories.db` 或 SQLite repository。
- 运行时源码写入风险：`app.py` 在缺失 `werkzeug_patch.py` 时会创建补丁文件，应改为显式兼容模块或依赖版本约束。

### `.gitignore` 边界扩展记录

- 已补充 Python 本地缓存：`*$py.class`、`.mypy_cache/`、`.ruff_cache/`、`.coverage`、`coverage.xml`、`htmlcov/`。
- 已补充 Node 与本地工具缓存：`.opencode/node_modules/`、`.npm/`、`.pnpm-store/`、`.cache/`、`.vite/`、`frontend/.vite/`、`.opencode/cache/`。
- 已补充构建与测试产物：`static/dist/`、根目录 `playwright-report/`、根目录 `test-results/`。
- 已补充运行缓存、日志和临时文件：`data/cache/`、`logs/*.log`、`logs/*.log.*`、`*.log`、`*.tmp`、`*.temp`、`*.pid`、`*.seed`、`*.bak`。
- 本次仅更新忽略规则，不删除、不移动、不批量改名任何已存在文件；已被 Git 跟踪的文件后续需要单独建立清单并通过 `git rm --cached` 类动作小批次处理。

### 生成物清理清单

> 盘点日期：2026-05-03。当前只建立清单和风险标记，不删除、不移动、不执行 `git rm --cached`。

| 类型 | 总数 | 涉及已跟踪 | 涉及未跟踪 | 涉及已忽略 | 风险/归属 | 建议处理 |
|---|---:|---:|---:|---:|---|---|
| `__pycache__/` 目录 | 1268 | 397 | 15 | 0 | Python 字节码目录，含 `venv/` 与业务目录缓存 | 分批从 Git 索引移除后本地删除；先处理业务目录，再处理 `venv/` |
| `*.pyc` 文件 | 11303 | 3680 | 80 | 7543 | 可再生成缓存；已跟踪样例包括根目录、`backend/*/__pycache__`、`venv/` | 后续小批次 `git rm --cached` 已跟踪 pyc，再清理本地缓存 |
| `node_modules/` 目录 | 5 | 2 | 0 | 0 | 依赖目录；根目录 `node_modules/` 已大量进入 Git 索引，`frontend/node_modules/` 需保持本地依赖 | 根目录依赖需结合前端双轨判断；依赖目录不应入库 |
| `dist/` 目录 | 33 | 15 | 0 | 0 | 构建产物；包含根目录 `dist/`、`frontend/dist/`、`static/dist/` 及依赖内 dist | 根目录/静态 dist 需结合发布策略判断，依赖内 dist 随 node_modules 一并处理 |
| `.pytest_cache/` 目录 | 1 | 0 | 0 | 0 | 测试缓存 | 可直接作为本地缓存清理候选，需确认不在索引内 |
| Playwright 报告目录 | 0 | 0 | 0 | 0 | 当前未发现根目录 `playwright-report/` | 保持忽略规则，后续 CI 门禁防止进入索引 |
| `test-results/` 目录 | 1 | 0 | 0 | 0 | 前端 E2E 测试输出 | 本地缓存候选，不入库 |
| `*.log` 文件 | 5 | 0 | 2 | 3 | 运行日志；未跟踪样例含 vendor 日志，忽略样例含 `logs/app.log`、`data/e2e/app.log` | 不应入库；vendor 日志需单独确认是否可清理 |

已跟踪生成物高风险分布：

- `*.pyc` / `__pycache__` 相关已跟踪路径约 4838 项，其中 `venv/` 约 4775 项，`backend/services` 19 项，`backend/pages` 14 项，`backend/repositories` 9 项，`backend/routes` 8 项，根目录 `__pycache__` 4 项。
- `node_modules/` 已跟踪约 2140 项，集中在根目录 `node_modules/`。
- `dist/` 已跟踪约 183 项，其中根目录 `dist/` 3 项、`static/dist/` 3 项，其余多在已跟踪 `node_modules` 依赖包内。
- `*.log` 已跟踪 2 项：`err.log`、`out.log`。

首批候选处理顺序建议：

1. **索引清理优先**：先对已跟踪 `venv/`、根目录 `node_modules/`、`__pycache__/`、`*.pyc`、`err.log`、`out.log` 建立 `git rm --cached` 小批次清单，避免一次性大规模操作。
2. **工程归属确认**：根目录 `dist/`、`static/dist/`、根目录前端 `package*.json` / `vite.config.js` / `index.html` 需要等第 18 阶段“前端工程边界”确认后再处理。
3. **本地删除后置**：只有在索引清理方案确认、备份或可再生成依据明确后，才考虑本地删除；不对个人目录或项目数据资产执行递归删除。

### 项目数据分层清单

> 盘点日期：2026-05-03。当前只读分类，不删除、不移动、不压缩、不改名任何数据文件。

| 数据层 | 文件数 | 总大小 | 已跟踪 | 未跟踪 | 已忽略 | 样例 | 分类判断 | 建议处理 |
|---|---:|---:|---:|---:|---:|---|---|---|
| `data/*.db` | 2 | 396.0 KB | 1 | 0 | 1 | `data/picks.db`、`data/alembic_validation.db` | SQLite legacy/验证库；`picks.db` 可能包含业务状态，`alembic_validation.db` 为迁移验证产物 | `picks.db` 需备份后再决定迁移/下线；验证库可作为可再生成候选 |
| `data/cache/*.pkl` | 974 | 9.4 MB | 25 | 0 | 949 | `stock_hist_*_akshare.pkl`、`stock_list_akshare.pkl` | 行情缓存，可再生成；其中 25 个仍被 Git 跟踪 | 后续小批次从索引移除已跟踪 pkl；本地缓存可按行情源/日期设置保留策略 |
| `data/e2e/*` | 2 | 537.1 KB | 0 | 0 | 2 | `data/e2e/app.log`、`data/e2e/picks-e2e.db` | E2E 测试运行数据，可再生成 | 保持忽略；可在测试前后自动清理或覆盖 |
| `backups/*` | 0 | 0 B | 0 | 0 | 0 | 当前目录为空 | 备份目录，目前无实际备份文件 | 保留目录策略；真实备份不应进入 Git，需外部备份/制品存储 |
| 导入/导出 CSV | 3 | 1.9 KB | 3 | 0 | 0 | `daily_selection.csv`、`picks_import_template.csv`、`review_edit_template.csv` | 模板/轻量样例/导入导出资产 | 模板类可保留入库；每日导出类需确认是否是样例还是运行输出 |
| JSON/HTML 数据资产 | 2 | 5.5 KB | 1 | 1 | 0 | `daily_selection.json`、`dashboard.html` | `daily_selection.json` 可能为研究样例；`dashboard.html` 更像生成页面 | JSON 是否长期资产待确认；HTML 建议归入生成物候选 |

数据根目录文件明细：

- `data/picks.db`：192.0 KB，已跟踪；SQLite legacy 业务库，迁移前应视为需备份资产。
- `data/alembic_validation.db`：204.0 KB，已忽略；迁移验证库，可再生成。
- `data/daily_selection.csv`：1.0 KB，已跟踪；需确认是长期样例还是每日运行输出。
- `data/daily_selection.json`：2.3 KB，已跟踪；需确认是长期样例还是每日运行输出。
- `data/picks_import_template.csv`：450 B，已跟踪；导入模板，可保留。
- `data/review_edit_template.csv`：472 B，已跟踪；编辑模板，可保留。
- `data/dashboard.html`：3.2 KB，未跟踪；看起来是生成页面，建议纳入生成物候选。

已跟踪缓存样例：

- `data/cache/stock_list_akshare.pkl`
- `data/cache/stock_hist_000001_2025-04-06_2026-04-06_qfq_akshare.pkl`
- `data/cache/stock_hist_002594_2021-04-07_2026-04-06_qfq_akshare.pkl`
- `data/cache/stock_hist_600000_2025-04-06_2026-04-06_qfq_akshare.pkl`
- `data/cache/stock_hist_600519_2025-10-01_2026-03-30_qfq_akshare.pkl`

数据处理优先级建议：

1. **先备份/迁移资产**：`data/picks.db` 在 SQLite legacy 依赖矩阵完成前不得删除；需要确认是否仍被旧页面、脚本或测试依赖。
2. **缓存索引清理**：`data/cache/*.pkl` 是可再生成行情缓存，25 个已跟踪文件应纳入后续小批次 `git rm --cached` 清单。
3. **模板保留**：`picks_import_template.csv`、`review_edit_template.csv` 属于可读模板，适合保留入库。
4. **样例/运行输出待确认**：`daily_selection.csv`、`daily_selection.json` 需要确认是否为长期研究资产；若是每日输出，应移到导出目录并忽略。
5. **测试数据隔离**：`data/e2e/` 保持忽略，E2E DB 和日志均应可重建。
6. **备份目录外置**：`backups/` 目录保留，但真实备份建议存放到外部备份介质或制品系统，不提交到 Git。

### 前端工程边界收口清单

> 盘点日期：2026-05-03。当前只读评估工程归属，不删除、不移动、不重命名任何前端文件。

| 路径 | 文件数 | 大小 | Git 跟踪 | 当前用途判断 | 风险/处理建议 |
|---|---:|---:|---:|---|---|
| 根目录 `package.json` | 1 | 538 B | 1 | 旧 K 线 React/Vite 工程入口；脚本只有 `vite` / `vite build`，依赖 `kline-charts-react` | 与正式 `frontend/` 双轨，建议后续标记 legacy，待确认无引用后移除或归档 |
| 根目录 `package-lock.json` | 1 | 33.1 KB | 1 | 根目录旧前端锁文件 | 随根目录旧前端处理；不应作为正式前端依赖来源 |
| 根目录 `vite.config.js` | 1 | 419 B | 1 | 旧 Vite 配置，开发端口 3000，`/api` 代理到 8765 | 与正式前端 5174 配置冲突，建议后续归档/移除 |
| 根目录 `index.html` | 1 | 284 B | 1 | 标题为“股票K线图表”，入口 `/src/main.jsx` | 旧 K 线单页入口，不是当前微信风工作台入口 |
| 根目录 `dist/` | 3 | 887.5 KB | 3 | 旧根目录 Vite 构建产物；JS 含“K线”，不含“今日工作台/生产监控/tenant_id” | 生成物候选，需等旧入口下线确认后从索引移除 |
| `static/dist/` | 3 | 886.1 KB | 3 | 旧构建产物副本；`backend/__init__.py` 仍声明 `DIST_DIR = BASE_DIR / 'dist'`，nginx 仍代理 `/dist/` 到 backend | legacy 静态分发路径，需配合旧 Jinja/K 线入口冻结处理 |
| `frontend/package.json` | 1 | 538 B | 0 | 正式 React/Vite 前端；含 build、preview、Playwright E2E 脚本 | 应作为唯一正式前端工程；当前在仓库状态中仍未跟踪，需后续纳入 Git 索引 |
| `frontend/package-lock.json` | 1 | 30.7 KB | 0 | 正式前端锁文件 | 应纳入 Git 索引，CI 已使用 `frontend/package-lock.json` 作为缓存依赖路径 |
| `frontend/vite.config.js` | 1 | 281 B | 0 | 正式 Vite 配置，开发端口 5174，代理 `/api` 到 8765 | 应纳入 Git 索引，端口与 Docker/nginx/CI 对齐 |
| `frontend/index.html` | 1 | 74 B | 0 | 正式前端 HTML 入口 | 应纳入 Git 索引 |
| `frontend/src/` | 26 | 60.6 KB | 0 | 正式微信风工作台、API client、页面组件、E2E data-testid 来源 | 应纳入 Git 索引；这是当前产品主线 |
| `frontend/dist/` | 4 | 1.1 MB | 0 | 正式前端本地构建产物；JS 含“今日工作台/生产监控/策略扫描/tenant_id” | 本地生成物，不入库；由 CI/Docker build 重新生成 |

正式前端依据：

- `docker-compose.yml` 的 `frontend.build.context` 指向 `./frontend`，生产镜像只构建 `frontend/`。
- `frontend/Dockerfile` 在 `frontend/` 内执行 `npm run build`，并将 `/app/dist` 复制到 nginx 静态目录。
- `.github/workflows/ci.yml` 的前端 job 使用 `working-directory: frontend`，执行 `npm ci`、`npm run build` 和 `npm run test:e2e`。
- `frontend/nginx.conf` 监听 5174，托管 React SPA，并将 `/api/` 反代到 `backend:8765`。
- `frontend/src/api/client.js` 使用 `VITE_API_BASE || '/api/v1'`，与第 8-17 阶段 API v1 主线一致。

边界结论：

- **正式唯一前端工程应确认为 `frontend/`**。
- 根目录 `package.json`、`package-lock.json`、`vite.config.js`、`index.html`、`dist/` 属于旧 K 线/Vite 工程或历史构建产物，不应继续作为推荐开发入口。
- `static/dist/` 与 backend `/dist` 代理仍属于 legacy 兼容路径，不能在冻结旧 Jinja/K 线入口前直接删除。
- 下一步若进入实际清理，应先把 `frontend/` 正式源文件纳入 Git，再分批对根目录旧前端构建产物和依赖做索引清理；实际删除需另行确认。

### Python 根目录入口收口清单

> 盘点日期：2026-05-03。当前只读梳理脚本归属，不移动、不删除、不批量改名。

| 类别 | 根目录文件 | 当前判断 | 主要风险 | 建议处理 |
|---|---|---|---|---|
| 正式应用入口 | `app.py` | Flask/gunicorn 生产入口，Dockerfile 与 `start_flask.sh` 仍引用 | 仍包含/依赖 legacy 兼容逻辑，但短期不可移除 | 保留根目录入口；后续仅收敛内部 legacy 副作用 |
| 兼容包装入口 | `ensure_extended_schema.py`、`init_tracker_db.py`、`import_picks_csv.py`、`ingest_daily_picks.py`、`bulk_update_reviews.py`、`build_dashboard_html.py` | 已迁入 `scripts/maintenance/`，根目录文件仅 `runpy` 转发 | 根目录仍有包装文件，但风险低；可维持一段兼容窗口 | 标记兼容包装；后续发布说明确认后可移除根包装 |
| legacy HTTP/Jinja 入口 | `web_panel.py` | 旧 `HTTPServer` 面板，直接依赖 `backend.repositories.db`、旧 pages/routes/services | 与 Flask/React/API v1 双轨，容易继续产生旧写入口 | 标记 legacy，只读/冻结；待旧入口确认无用后移除或归档 |
| 定时任务编排入口 | `scheduler.py` | APScheduler 编排早盘/尾盘任务，已部分改用 `scripts/maintenance/*` | 仍调用多项根目录策略/报表脚本，且写 `data/render_dashboard_ping.log` | 保留但标记待迁移；后续拆到任务队列或 `scripts/scheduler/` |
| 策略扫描/回测入口 | `strategy_2560.py`、`run_2560_backtest.py`、`strategy_lite.py`、`first_limit_replay.py`、`first_limit_validate.py` | 旧策略/研究执行脚本；部分仍依赖 akshare/pandas/sqlite3/backend.services | 与新 `/api/v1` 扫描/回测服务双轨；`run_2560_backtest.py` 还会创建 `werkzeug_patch.py` | 建立迁移矩阵：保留研究脚本但迁入 `scripts/research/` 或改为 API/服务入口 |
| 报表/复盘/研究输出 | `report_2560.py`、`strategy_digest.py`、`review_metrics.py`、`leaderboards.py`、`master_ledger.py`、`daily_review_brief.py`、`content_analytics.py` | 研究/运营报表脚本，多被 `scheduler.py` 编排 | 多数直接读写 SQLite/CSV/行情，数据边界不清 | 迁入 `scripts/reports/` 或 `scripts/research/`，补 dry-run/输出目录说明 |
| 手工数据操作 | `add_pick.py` | 手动写 `data/picks.db` 的 SQLite CLI | 绕过 API v1、审计、权限、多租户 | 标记高风险 legacy 写入口；后续改为 `/api/v1/picks` 或维护脚本且默认 dry-run |
| 测试/演示散落入口 | `test_stock_data_service.py`、`test_strategy.py`、`ui_demo.py` | 根目录测试/演示文件，不在标准 `tests/` 目录 | 容易被误认为正式入口；`ui_demo.py` 另起 Flask demo | 迁入 `tests/` 或 `scripts/demo/`，不应长期留根目录 |
| 兼容补丁 | `werkzeug_patch.py` | Werkzeug 兼容补丁模块，被 `app.py` 和 `run_2560_backtest.py` 引用 | 运行时创建补丁风险仍存在于 `run_2560_backtest.py` | 第 18 阶段后续“移除运行时源码写入风险”统一处理 |

根目录脚本引用关系发现：

- `scheduler.py` 仍直接调用：`strategy_2560.py`、`report_2560.py`、`first_limit_replay.py`、`first_limit_validate.py`、`review_metrics.py`、`leaderboards.py`、`master_ledger.py`、`daily_review_brief.py`、`strategy_digest.py`，并调用已迁移维护脚本 `scripts/maintenance/init_tracker_db.py`、`scripts/maintenance/ingest_daily_picks.py`。
- `Dockerfile` 与 `start_flask.sh` 仍引用 `app.py`，因此 `app.py` 是保留入口。
- `web_panel.py` 相关能力已被多个 `backend/*` legacy 模块间接引用，说明旧 HTTP 面板仍未完全断开。
- `werkzeug_patch.py` 被 `app.py`、`run_2560_backtest.py` 引用；其中 `run_2560_backtest.py` 仍有缺失时写文件逻辑。

Python 根入口收口顺序建议：

1. **先冻结高风险写入口**：`add_pick.py`、`web_panel.py`、旧 Jinja/HTTP 写能力应先只读化或跳转到 `/api/v1`。
2. **保留正式启动链路**：`app.py`、Dockerfile、gunicorn 入口不动，避免影响生产启动。
3. **迁移兼容包装**：已迁入 `scripts/maintenance/` 的根包装入口可以保留一个发布周期，再统一移除。
4. **拆分 scheduler**：把 `scheduler.py` 中调用的研究/报表脚本先归类到 `scripts/research/`、`scripts/reports/` 或任务队列入口，再考虑删除根脚本。
5. **消除运行时源码写入**：`run_2560_backtest.py` 的 `werkzeug_patch.py` 自动创建逻辑应与 `app.py` 补丁逻辑一并改造。

## 验收清单

- [x] 新前端覆盖首页、策略、扫描、K线、选股池、报告、监控、同步、后台管理。
- [x] `/api/v1` 覆盖核心写操作并有 CSRF、多租户、权限测试。
- [ ] 旧 Jinja 写入口不再作为推荐路径。
- [ ] 根目录无未归档运维脚本。
- [x] 备份恢复 runbook 已验证。
- [x] 完成第 18 阶段只读盘点，不执行文件删除/移动。
- [ ] 完成 SQLite legacy 依赖矩阵并确定迁移/下线顺序。
- [ ] 完成仓库卫生 CI 门禁，防止生成物、缓存和本地依赖重新进入版本库。

## 回滚方式

- 保留 `backend/__init__.py` 中旧蓝图注册，短期不删除。
- 若新前端出现阻塞问题，可临时开放旧只读入口。
- 恢复写能力前必须确认审计日志、CSRF 和租户边界仍然生效。
