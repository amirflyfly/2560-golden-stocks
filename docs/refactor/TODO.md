# 2560 strategy 重构 TODO

## 0. 基线与规划

- [x] 生成重构 TODO 清单
- [x] 固化当前功能清单和验收用例
- [x] 梳理旧路由到新 API 的映射表
- [x] 建立重构 ADR 文档

## 1. 后端 API 与配置基础

- [x] 建立新 API 分层目录
- [x] 建立统一配置模块
- [x] 建立统一 API 响应结构
- [x] 建立统一异常处理
- [x] 建立健康检查接口
- [x] 建立认证与租户上下文依赖

## 2. MySQL 与多租户数据层

- [x] 引入 SQLAlchemy 2.x
- [x] 引入 Alembic 迁移框架
- [x] 设计 MySQL 基础模型
- [x] 实现 tenants / users / roles / permissions 模型
- [x] 实现业务表 tenant_id 规范
- [x] 实现 SQLite 到 MySQL 迁移脚本
- [x] 编写多租户隔离测试

## 3. 行情数据源与 mootdx

- [x] 建立 MarketDataProvider 抽象接口
- [x] 实现 Mock provider
- [x] 实现 AkShare provider 兼容层
- [x] 实现 Mootdx provider
- [x] 实现数据源选择配置
- [x] 实现数据源健康检查
- [x] 实现 mootdx 失败降级策略
- [x] 将策略扫描改为依赖统一数据源接口

## 4. 策略、扫描与选股 API

- [x] 实现策略管理 API
- [x] 实现扫描任务 API
- [x] 实现扫描结果 API
- [x] 实现选股池 API
- [x] 实现研究报告 API
- [x] 实现分页、排序、过滤统一规范

## 5. 前端分离

- [x] 建立 frontend 独立应用目录
- [x] 建立 API client
- [x] 建立登录与租户切换页面
- [x] 迁移首页看板
- [x] 迁移策略管理页面
- [x] 迁移策略扫描页面
- [x] 迁移股票 K 线页面
- [x] 迁移选股池页面
- [x] 迁移后台管理页面

## 6. 异步任务与生产化

- [x] 引入 Redis 配置
- [x] 引入任务队列
- [x] 扫描任务异步化
- [x] 行情同步任务化
- [x] 建立 Docker Compose
- [x] 建立日志与任务状态追踪

## 7. 验证与清理

- [x] 后端新增骨架语法与模型导入验证通过
- [x] 前端构建通过
- [x] 多租户隔离测试通过
- [x] mootdx provider 测试通过
- [x] 清理废弃 Jinja 页面
- [x] 清理根目录遗留脚本

## 8. 新阶段：生产验收与安全加固

- [x] 固化生产环境变量模板，避免默认密钥、默认账号、debug 配置进入生产
- [x] 验证 Docker Compose 下 MySQL / Redis / backend / frontend 联合启动（MySQL/Redis/backend healthy，frontend Vite 200 OK，backend /api/v1/health 200 OK，Redis PONG）
- [x] 执行真实 MySQL schema 迁移与基础数据初始化验收（容器内 Alembic upgrade head、bootstrap_mysql_seed.py、validate_mysql_schema.py 通过；核心表 seed 数量与 alembic_version 已核对）
- [x] 执行 /api/v1 端到端验收：健康检查、策略、扫描、结果、选股池、报告、任务状态
- [x] 执行 React 前端端到端验收：租户切换、看板、策略管理、扫描、K 线、选股池、后台管理
- [x] 加固认证与多租户边界：默认账号治理、租户头校验、角色权限落地检查
- [x] 加固安全基线：CORS、CSRF、CSP、错误信息脱敏、生产日志级别
- [x] 验证 mootdx 真实数据链路，并记录 fallback 到 akshare/mock 的触发条件
- [x] 将根目录遗留运维/数据脚本收敛到 scripts/ 或任务队列入口
- [x] 生成新阶段验收报告与上线检查清单

## 9. 功能增强与生产部署完善

- [x] 建立生产监控与日志面板 API：运行概览、轻量指标、脱敏日志摘要
- [x] 完善用户 / 租户后台管理 API：用户列表、角色、启停、租户列表
- [x] 增强行情同步任务可视化：任务过滤、详情、失败重试或取消语义
- [x] 优化策略扫描性能路径：快速返回、任务摘要、缓存或分页优化
- [x] 接入 React 前端页面：生产监控、后台管理增强、行情同步面板
- [x] 切换前端正式构建与 nginx 部署：静态托管与 /api 反代
- [x] 完成第 9 阶段测试、Docker 验收与验收报告

## 10. 生产硬化与可观测性增强

- [x] 接入结构化日志落盘与日志轮转：统一 JSON 日志、脱敏规则、保留周期、监控面板读取真实日志文件
- [x] 增强安全响应头与 nginx 生产配置：gzip、静态缓存、HSTS 开关、server_tokens、代理超时与上传限制
- [x] 完善后台管理能力：租户创建 / 更新 / 启停、用户创建 / 密码重置 / 租户绑定
- [x] 升级任务队列可恢复性：任务持久化、重试策略、失败原因分类、任务取消状态一致性
- [x] 优化扫描与任务性能验证：批量股票分页、任务列表分页、关键 API 响应时间基线测试
- [x] 补齐生产可观测性前端：日志筛选、任务失败聚合、健康状态告警提示
- [x] 完成第 10 阶段测试、Docker 验收与验收报告

## 11. 生产可靠性与强隔离增强

- [x] 强化多租户绑定校验：用户必须绑定目标租户，disabled tenant 禁止访问，租户级角色生效
- [x] 禁止生产环境静默使用 mock 行情：fallback 可见化，扫描结果标记数据源与数据质量
- [x] 替换 Flask dev server：Docker 后端改用 gunicorn / waitress，并配置 worker、timeout、日志
- [x] 收敛 Docker Compose 生产暴露面：仅暴露前端 / 网关入口，MySQL / Redis / backend 走内部网络
- [x] 明确 HTTPS / HSTS 部署拓扑：外部网关或容器 nginx 终止 TLS 二选一
- [x] 建立 CI 流水线：pytest、frontend build、docker-compose config、镜像构建检查
- [x] 补齐 Playwright 前端 E2E：登录、租户切换、扫描、后台管理、权限拒绝

## 12. 审计日志与备份恢复

- [x] 建立后台审计日志表：记录 user_id、username、tenant_id、action、resource_type、resource_id、result、ip、user_agent、detail_json、created_at
- [x] 建立审计日志服务与脱敏策略：密码、token、cookie 等敏感字段不落明文
- [x] 覆盖关键操作审计：用户、租户、密码、扫描、行情同步、任务取消等关键操作可追溯
- [x] 建立管理员审计查询 API 与前端最近审计记录入口
- [x] 制定 legacy 下线计划：旧 Jinja 页面只读 / 跳转，根目录脚本继续迁入 scripts
- [x] 建立备份恢复演练：SQLite/data 目录备份校验、MySQL dump 命令清单、恢复验证清单
- [x] 编写备份恢复演练脚本与自动化测试

## 13. 任务队列生产化增强

- [x] 增强任务状态模型：retry_count、max_retries、idempotency_key、failure_category、heartbeat_at、duration_seconds
- [x] 建立任务事件记录：queued、running、retrying、completed、failed、cancelled、stale 等状态变化可追踪
- [x] 增加 stale running 标记/恢复能力，避免进程异常后任务长期卡住
- [x] 保持扫描、行情同步、任务取消接口兼容并补齐测试

## 14. 策略结果可解释性

- [x] 扫描结果新增 explanation：score、reasons、indicators、risk_tags、market_data_source、data_quality、fallback_used
- [x] 前端扫描页展示入选理由、指标明细、风险标签、行情源与数据质量
- [x] 旧任务/旧结果缺少解释字段时前后端优雅降级
- [x] 补齐 API 与 UI 验证，确保 A 股红涨绿跌语义不被破坏

## 15. 产品化体验收尾

- [x] 抽取轻量页面体验模式：统一卡片、空态、加载态、错误态与状态徽标
- [x] 改造后台管理页：用户/租户/审计记录形成清晰管理工作台
- [x] 改造生产监控页：健康摘要、告警解释、日志筛选和故障引导更清晰
- [x] 改造行情同步页：同步参数校验、任务进度、成功/失败反馈更明确
- [x] 统一登录页微信风格并保留安全提示
- [x] 完成后端测试、前端构建与 Playwright E2E 验证

## 16. 质量、运维、策略与合规增强

- [x] 重构前端通用组件：抽取 AppShell、NavSidebar、Topbar、PageHeader、MetricCard、StatusBadge、DataTable、EmptyState、SectionCard，并保留现有 data-testid 与微信风视觉
- [x] 完善生产部署实战 runbook：覆盖发布、验证、回滚、故障排查、备份前置检查和常见失败处置
- [x] 新增只读部署预检脚本：检查环境、Compose、Dockerfile、nginx、安全头、数据/备份目录和关键脚本完整性
- [x] 增强策略回测 API：新增 v1 回测入口，返回收益、回撤、胜率、交易次数、交易明细与解释摘要
- [x] 增强策略扫描 explanation：将 signal、note、risk_score、total_score、vol_ratio、ma25 等策略字段结构化到解释结果中
- [x] 强化审计完整性与合规说明：增加完整性哈希、敏感字段递归脱敏测试、审计保留/导出/篡改检查说明
- [x] 完成第 16 阶段测试、前端构建、Playwright E2E 验证与记录回写

## 17. 策略回测与解释 API 深化

- [x] 增强策略回测请求参数校验：支持 holding_days、max_positions_per_day、trade_limit、include_trades，并限制安全范围
- [x] 增强回测响应结构：返回风险分级、收益分布、权益曲线、分页交易明细与请求选项回显
- [x] 升级回测 explanation schema：增加 schema_version、confidence、verdict、indicator_groups、warnings、action_suggestion 与 assumptions
- [x] 增强回测历史接口：支持分页，并为历史记录补充 explanation 摘要
- [x] 升级扫描 explanation schema：增加 schema_version、confidence、risk_level、indicator_groups、warnings 与 action_suggestion，并对旧结果自动补齐
- [x] 补齐增强 API 测试：覆盖回测参数、历史分页、扫描解释结构、旧扫描结果解释补齐与审计脱敏
- [x] 完成第 17 阶段后端回归验证与记录回写

## 18. 仓库卫生与 legacy 收口

> 原则：第一轮只读盘点和 TODO 固化，不移动、不删除、不批量改名任何文件；后续清理必须先列清单、确认归属、再小批次执行。

- [x] 生成仓库卫生只读清单：识别生成物目录、依赖目录、运行缓存、日志、数据库文件、根目录遗留入口和 legacy 引用范围
- [x] 扩展 `.gitignore` 边界：补充 `venv/`、`.opencode/node_modules/`、`data/cache/`、`logs/*.log`、临时运行产物和本地工具缓存规则
- [x] 建立生成物清理清单：列出已跟踪或未跟踪的 `__pycache__`、`*.pyc`、`node_modules`、`dist`、`.pytest_cache`、Playwright 报告等，先标记归属和风险，不直接删除
- [x] 建立项目数据分层清单：区分 `data/*.db`、`data/cache/*.pkl`、`data/e2e/`、`backups/`、导入/导出文件和长期研究资产，明确哪些可缓存、哪些需备份
- [x] 收口前端工程边界：确认 `frontend/` 为唯一正式 React/Vite 工程，评估根目录 `package.json`、`package-lock.json`、`vite.config.js`、`index.html`、`dist/` 是否仅为 legacy 或可移除产物
- [x] 收口 Python 根目录入口：梳理 `add_pick.py`、`web_panel.py`、`strategy_2560.py`、`run_2560_backtest.py`、`scheduler.py` 等根目录脚本，迁入 `scripts/` 或标记兼容包装
- [ ] 移除运行时源码写入风险：改造 `app.py` 中缺失 `werkzeug_patch.py` 时自动创建补丁文件的逻辑，改为显式兼容模块或依赖版本约束
- [ ] 冻结旧 `/api` 与 Jinja 写入口：为 `backend/routes/` 中旧写路由建立只读/跳转/保留清单，新写能力只允许进入 `/api/v1`
- [ ] 剥离 SQLite 启动副作用：评估 `backend/__init__.py` 启动时调用 `ensure_schema()` 的必要性，将 SQLite schema 初始化迁移到测试 fixture 或显式维护脚本
- [ ] 建立 SQLite legacy 依赖矩阵：列出仍引用 `backend.repositories.db`、`picks_repo`、`users_repo` 等 SQLite repository 的页面、服务、API 和脚本，标记迁移目标
- [ ] 增加仓库卫生 CI 门禁：检查禁止提交 `__pycache__`、`*.pyc`、`node_modules`、大体积 pkl 缓存、日志和本地虚拟环境
- [ ] 更新 legacy 下线计划验收状态：将已被 React/API 覆盖的功能勾选，将未收口项转成可执行迁移任务
- [ ] 完成第 18 阶段回归验证：pytest、frontend build、Playwright E2E、docker compose config、deploy preflight 至少覆盖受影响链路
