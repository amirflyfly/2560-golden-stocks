# AiStocks v1.1 Production Evidence 准备度极简检查

检查日期：2026-05-21

## 结论

NOT_READY。

仅根据本次允许读取的两个文件判断：当前不能确认本机可直接采集真实 production evidence。`scripts/production_evidence.py` 的采集入口只会读取当前运行进程内的 `MonitoringService().readiness()`，没有外部 production URL 参数；因此必须在目标 staging/production 环境、且真实 `.env` 与服务已启动后执行，采样才可作为真实 evidence。

## 可用采集链路

- 生成模板：`python scripts/production_evidence.py --write-template docs/product/PRODUCTION_EVIDENCE.prod.json`
- 采集当前运行环境 readiness sample：`python scripts/production_evidence.py --write-readiness-sample docs/product/readiness-1.json`
- 生成带当前 readiness 的草稿 bundle：`python scripts/production_evidence.py --write-runtime-bundle docs/product/PRODUCTION_EVIDENCE.prod.json`
- 验证 evidence：`python scripts/production_evidence.py --evidence docs/product/PRODUCTION_EVIDENCE.prod.json`

## 必需环境变量 / 服务 / 目标地址

### 环境变量与配置期望

- `.env` 必须从 `.env.example` 派生并替换真实生产配置。
- `CACHE_BACKEND=redis`
- `TASK_QUEUE_BACKEND=redis`
- `TASK_EXECUTION_MODE=worker`
- `LIVE_BROKER_LAUNCH_POLICY=disabled`
- 所有 repository backend 必须为 `mysql`：
  - `PICKS_REPOSITORY_BACKEND`
  - `AUTH_REPOSITORY_BACKEND`
  - `AUDIT_REPOSITORY_BACKEND`
  - `SETTINGS_REPOSITORY_BACKEND`
  - `LOGS_REPOSITORY_BACKEND`
  - `STRATEGY_POOL_REPOSITORY_BACKEND`
  - `STRATEGY_REPOSITORY_BACKEND`
  - `TRADING_REPOSITORY_BACKEND`
- MySQL schema revision 必须为 `0023_signal_review_links`。
- readiness sample 还必须满足：`ready=true`、`database_dialect=mysql`、`tasks_stale=0`、`signal_review_complete_rate>=1`、`signal_review_incomplete=0`。

### 服务要求

- MySQL、Redis、backend、worker、frontend 必须在目标网络中启动。
- 外部网关/TLS 必须就绪。
- 备份目录和备份保留策略必须就绪。
- 至少采集两个 internal readiness 样本，soak 时长校验默认要求 `MIN_SOAK_MINUTES=120`。

### 目标地址

`production_evidence.py` 没有提供外部 URL 参数；真实采集目标不是通过传入 URL 完成，而是要求脚本运行在目标 staging/production 环境中，使用该环境的 `.env`、数据库、Redis、worker 与内部 readiness 状态。

## 当前缺口

1. 未确认本机就是目标 staging/production 环境。
2. 未确认本机真实 `.env` 已替换为生产配置。
3. 未确认 MySQL、Redis、backend、worker、frontend 已在目标网络中启动。
4. 未确认外部网关/TLS 已就绪。
5. 未确认已完成 MySQL backup、restore drill、migration、regression、release review、security review。
6. 未确认已采集至少两个合格 internal readiness samples。
7. 未确认已生成并填写 `docs/product/PRODUCTION_EVIDENCE.prod.json`。

## 最大阻断项

缺少已确认的目标 production/staging 运行环境及其真实 `.env`、MySQL、Redis、backend、worker readiness 上下文；在普通本机环境直接运行脚本只能采集“当前进程环境”的 readiness，不能自动证明是真实 production evidence。
