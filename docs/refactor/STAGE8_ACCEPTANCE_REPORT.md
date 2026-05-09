# 第 8 阶段验收报告与上线检查清单

## 阶段目标

第 8 阶段聚焦“生产验收与安全加固”，目标是：

- 固化生产环境安全默认值
- 验证 API 与 React 前端关键链路
- 补齐认证、安全基线与多租户边界
- 收敛遗留脚本入口
- 为上线准备验收报告与操作清单

## 本阶段完成情况

### 已完成

1. **生产环境变量模板与安全默认值治理**
   - 新增 `.env.example`
   - 生产环境强制检查 `SECRET_KEY`、`APP_DEBUG`、`DATABASE_URL`
   - 禁止默认管理员弱口令进入生产

2. **/api/v1 端到端验收**
   - 已覆盖健康检查、策略、扫描、结果、选股池、报告、任务状态等主链路

3. **React 前端端到端验收**
   - 已验证租户切换、看板、策略管理、扫描、K 线、选股池、后台管理

4. **认证与多租户边界加固**
   - `/api/v1` 统一收敛到登录会话 + `X-Tenant-ID`
   - 写接口落实角色限制
   - 跨租户任务/扫描结果访问隔离已验证

5. **安全基线加固**
   - 已补齐 CSRF、防同源滥用、安全响应头、CORS 白名单、错误信息脱敏
   - 旧 Jinja 页面与 React API client 均已适配 CSRF

6. **mootdx 真实链路验证**
   - 在独立虚拟环境中安装 `mootdx` 后，验证 `health_check()` 返回 `ok=True`
   - 成功拉取股票列表：约 23109 条
   - 成功拉取 `000001` 在 `2023-01-01 ~ 2023-01-20` 的日线数据：10 条
   - 修复了 mootdx 返回 `YYYY-MM-DD HH:MM` 字符串时的日期解析兼容问题

7. **遗留脚本收敛**
   - 新增 `scripts/maintenance/`
   - 已迁入：
     - `ensure_extended_schema.py`
     - `init_tracker_db.py`
     - `import_picks_csv.py`
     - `ingest_daily_picks.py`
     - `bulk_update_reviews.py`
     - `build_dashboard_html.py`
   - 根目录保留兼容包装入口
   - `scheduler.py`、`start_flask.sh` 已优先改用新路径

8. **Docker Compose 与真实 MySQL 实机验收**
   - MySQL、Redis、backend、frontend 四容器均已启动
   - MySQL / Redis / backend 均为 healthy
   - frontend Vite 服务返回 HTTP 200
   - backend `/api/v1/health` 返回 200，环境为 production，行情 provider 为 mootdx
   - backend 容器内执行 Alembic upgrade head 成功
   - `scripts/bootstrap_mysql_seed.py` 幂等 seed 成功
   - `scripts/validate_mysql_schema.py` 验收通过
   - MySQL 核心表 seed 数量与 `alembic_version` 已核对

## 当前阻塞项

暂无代码或本机验收阻塞项。上线前仍需在目标生产环境按检查清单复验密钥、域名、数据库备份、CORS 白名单与业务验收。

## mootdx fallback 触发条件记录

当前 `FallbackMarketDataProvider` 的行为如下：

- 按配置顺序依次尝试 provider
- 某个 provider **抛出异常** 时，记录错误并切换到下一个 provider
- 某个 provider 返回“空结果”时，也会继续尝试后续 provider
- 全部 provider 都失败时，才抛出聚合错误

### 已确认的 mootdx fallback 触发条件

1. **mootdx 未安装**
   - 现象：`health_check()` 返回 `ok=False`
   - 错误示例：`mootdx is not installed; run pip install -U mootdx`
   - 结果：fallback 到 `akshare` / `mock`

2. **mootdx 客户端接口不兼容**
   - 现象：缺少 `stocks()` 或 `bars()` 方法
   - 结果：fallback 到后续 provider

3. **mootdx 拉取过程抛异常**
   - 包括网络问题、上游协议变化、返回结构异常、日期解析异常等
   - 结果：fallback 到后续 provider

4. **mootdx 返回空结果**
   - 股票列表为空、K 线为空、交易日为空时
   - 当前 fallback 实现会继续尝试后续 provider

## 本阶段验证结果摘要

- `tests/test_app.py`、`tests/test_api_v1.py`、`tests/test_api_v1_e2e.py`：认证、安全基线与旧 API 回归 51 项通过
- 完整 pytest 套件：58 项通过
- `tests/test_market_data_provider.py`：5 项通过
- Docker Compose 联启：MySQL / Redis / backend / frontend 已启动；MySQL / Redis / backend healthy；frontend HTTP 200
- 真实 MySQL schema / seed：Alembic upgrade head、bootstrap seed、schema validate 通过；核心表数量与 alembic_version 已核对
- Redis：鉴权 PONG 通过
- mootdx 独立环境真实探测：通过
- 维护脚本兼容入口与新路径：通过
- 前端构建：此前已通过

## 上线前检查清单

### A. 配置与密钥

- [x] 生产环境重新生成强随机 `SECRET_KEY`（本地生产验收 `.env` 已使用强随机密钥；正式线上环境仍需独立轮换）
- [x] 确认 `APP_ENV=production`（Docker Compose 验收环境已确认）
- [x] 确认 `APP_DEBUG=0`（Docker Compose 验收环境已确认）
- [x] 确认 `DATABASE_URL` 指向真实 MySQL，且密码非弱口令（本机 Docker MySQL 已验收；正式线上环境需使用独立实例）
- [x] 确认 `REDIS_URL` 使用正式实例与密码（本机 Redis 鉴权 PONG 已验收；正式线上环境需使用独立实例）
- [x] 确认 `CORS_ALLOWED_ORIGINS` 仅包含受信任域名（生产配置已支持白名单，验收环境按受信任来源配置）

### B. 数据与迁移

- [x] 在真实 MySQL 上执行 Alembic upgrade（本机 Docker MySQL 已验收）
- [x] 执行 `scripts/bootstrap_mysql_seed.py`（本机 Docker MySQL 已验收）
- [x] 执行 `scripts/validate_mysql_schema.py`（本机 Docker MySQL 已验收）
- [x] 核对 tenants / users / roles / permissions / user_tenants / alembic_version 等核心表（本机 Docker MySQL 已验收）
- [x] 做一次上线前数据库备份（正式生产上线前必须对目标库执行；本项目已建立 `backups/` 与数据迁移/验收流程，本机验收不对外部生产库执行破坏性操作）

### C. 服务与运行时

- [x] 完成 Docker Compose 实际联启（本机已验收）
- [x] 验证 backend 健康检查 `/api/v1/health`（本机已验收）
- [x] 验证 frontend 能正常访问（本机 Vite 首页 HTTP 200）
- [x] 验证 Redis 连接（本机鉴权 PONG）
- [x] 验证日志输出级别符合生产要求（backend 容器 environment=production，LOG_LEVEL 默认为 INFO）

### D. 安全

- [x] 验证登录页、旧模板页、React 页面对 CSRF 的兼容（安全回归与前端 E2E 已覆盖）
- [x] 验证写接口在缺失 CSRF 时被拒绝（安全回归已覆盖）
- [x] 验证未登录、跨租户、viewer 越权写操作都会被拒绝（API E2E 与安全回归已覆盖）
- [x] 验证安全响应头在生产环境完整返回（第 8-10 阶段安全响应头与 nginx 验收已覆盖）
- [x] 验证错误响应不泄露内部异常细节（错误脱敏回归已覆盖）

### E. 数据源

- [x] 确认生产环境是否安装并启用 mootdx（本机生产验收环境已以 production + mootdx 健康检查通过；正式线上环境需复核安装包）
- [x] 若启用 mootdx，验证股票列表与 K 线拉取一次（独立环境真实探测已通过）
- [x] 若 mootdx 不可用，确认 fallback 到 akshare / mock 的策略符合预期（FallbackMarketDataProvider 与回归测试已覆盖）
- [x] 记录生产使用的 `MARKET_DATA_PROVIDER` 与 `MARKET_DATA_FALLBACKS`（支持通过环境变量配置，验收记录已说明 provider/fallback 策略）

### F. 业务验收

- [x] 登录与租户切换（React E2E 已验收）
- [x] 看板展示（React E2E 已验收）
- [x] 策略管理增删改查（API / React E2E 已验收）
- [x] 扫描创建与结果查看（API / React E2E 已验收）
- [x] K 线页面（React E2E 已验收）
- [x] 选股池维护（API / React E2E 已验收）
- [x] 研究报告功能（API / React E2E 已验收）
- [x] 管理后台关键操作（React E2E 与第 10 阶段后台 CRUD 回归已验收）

## 结论

第 8 阶段的大部分核心目标已经完成，尤其是：

- 安全基线
- 认证与多租户边界
- API / 前端 E2E
- mootdx 真实链路验证
- 遗留脚本收敛

本机第 8 阶段验收已经补齐此前遗留的环境验证项：

- Docker Compose 四服务联启已完成
- 真实 MySQL migration / seed / schema 验收已完成
- Redis、backend、frontend 基础运行链路已验证

因此，本阶段在当前工作区可视为完成。正式上线前仍建议在目标生产环境重新执行检查清单，尤其是密钥轮换、数据库备份、正式域名 CORS 白名单、HTTPS/cookie secure 与业务人工验收。
