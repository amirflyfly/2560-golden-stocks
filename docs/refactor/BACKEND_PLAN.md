# 后端重构规划

## 技术选择

- 近期兼容 Flask，逐步 API 化。
- 新模块按 FastAPI 风格设计，保留未来迁移空间。
- SQLAlchemy 2.x 作为 ORM。
- Alembic 管理迁移。
- MySQL 作为主库。
- Redis 作为缓存与任务状态存储。

## 新目录职责

```text
backend/api_v1/        HTTP API
backend/core/          配置、响应、错误、上下文
backend/db/            SQLAlchemy session 和 models
backend/domain/        领域对象和规则
backend/application/   业务用例编排
backend/infrastructure 第三方系统适配
```

## 第一阶段最小可用目标

- 不破坏旧 app.py。
- 新增 API blueprint。
- 暴露 /api/v1/health。
- 建立统一响应对象。
- 建立配置对象。
- 建立数据库 models 初稿。
- 建立 MarketDataProvider 抽象。
