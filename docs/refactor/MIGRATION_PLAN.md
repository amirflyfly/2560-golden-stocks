# 迁移实施计划

## 原则

- 采用绞杀者模式，逐步替换旧模块。
- 每完成一项即更新 TODO 勾选。
- 未完成项不对外宣称完成。
- 每阶段必须有可验证结果。

## 阶段 1：规划与基础骨架

验收标准：

- TODO 清单存在并可持续勾选。
- 架构、数据库、迁移规划文档存在。
- 新 API、数据库、数据源目录骨架存在。

## 阶段 2：后端 API 基础

验收标准：

- `/api/v1/health` 可用。
- 有统一响应结构。
- 有统一配置加载。
- 不影响旧 Flask 应用启动。

## 阶段 3：MySQL 多租户基础

验收标准：

- SQLAlchemy models 可导入。
- Alembic 可生成迁移。
- tenants/users/roles/user_tenants 基础模型存在。
- repository 查询约定包含 tenant_id。

## 阶段 4：行情数据源重构

验收标准：

- MarketDataProvider 抽象存在。
- Mock/AkShare/Mootdx provider 至少可导入。
- 策略扫描可通过 provider 获取数据。
- mootdx 不污染业务层。

## 阶段 5：前端独立化

验收标准：

- frontend 独立构建。
- 登录、首页、策略、扫描、股票详情页面逐步迁移。
- Jinja 页面逐步冻结。

## 阶段 6：任务队列与生产化

验收标准：

- 扫描任务异步执行。
- Redis 任务状态可查。
- Docker Compose 可启动 MySQL、Redis、API、worker、frontend。

## 回滚策略

- 保留旧 SQLite 和旧 Flask/Jinja 入口，直到新模块完成验收。
- 新 API 使用 `/api/v1` 前缀，不覆盖旧接口。
- 数据迁移采用复制式迁移，验证后再切换读写。
- mootdx 接入失败时回退 akshare 或缓存。
