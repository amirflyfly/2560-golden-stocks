# AiStocks v1.0 真实 Production Evidence 采集 Runbook

## 目的

本文件用于在准生产/生产目标环境采集真实上线证据，补齐当前发布基线 commit `c64c72e` 之后仍缺失的生产证据门禁。

当前本地状态已经完成：

- 后端关键测试：`25 passed`
- 前端构建：PASS
- 本地 `scripts/deploy_preflight.py`：PASS，43/43
- 发布基线 commit：`c64c72e Prepare AiStocks v1 launch gates and root migration`

但完整上线 PASS 仍需要目标环境真实 evidence。禁止使用 `docs/product/PRODUCTION_EVIDENCE.example.json` 作为真实上线证据。

## 适用范围

- 环境：staging / production
- 版本：AiStocks v1.0 发布基线 `c64c72e`
- 目标：生成并验证 `docs/product/PRODUCTION_EVIDENCE.prod.json` 或等价的环境专属 evidence 文件

## 前置条件

1. 目标环境代码版本为 `c64c72e` 或其审核后的发布分支版本。
2. `.env` 已从 `.env.example` 派生，并替换真实生产配置。
3. MySQL、Redis、backend、worker、frontend 均可在目标网络中启动。
4. 外部网关/TLS 已就绪，Compose 仅发布 frontend gateway 端口。
5. `LIVE_BROKER_LAUNCH_POLICY=disabled`，v1.0 不开放实盘自动交易。
6. 已准备备份目录和备份保留策略。

## 一、确认代码版本

```bash
git log -1 --oneline
git status --short
```

期望：

```text
c64c72e Prepare AiStocks v1 launch gates and root migration
```

如果不是该版本，需要记录实际版本并由发布负责人确认。

## 二、创建真实 evidence 文件

使用模板生成目标环境 evidence 文件：

```bash
python scripts/production_evidence.py --write-template docs/product/PRODUCTION_EVIDENCE.prod.json
```

不要直接复制 example 后声称通过。example 中大量字段故意为 false/空值，用于说明结构，不是上线证据。

## 三、真实 `.env` 部署预检

在目标环境准备真实 `.env` 后运行：

```bash
python scripts/deploy_preflight.py
```

期望：

```text
ok=true
total=43
failed=0
summary=preflight passed
```

注意：本地无 `.env` 时会显示 `env-file:optional`，目标环境应实际校验 Redis / worker / repository backend / live broker policy 等真实配置。

必须确认：

| 检查项 | 期望 |
|---|---|
| `CACHE_BACKEND` | `redis` |
| `TASK_QUEUE_BACKEND` | `redis` |
| `TASK_EXECUTION_MODE` | `worker` |
| `LIVE_BROKER_LAUNCH_POLICY` | `disabled` |
| 所有 repository backend | `mysql` |
| MySQL schema revision | `0022_stock_daily_bar_timestamps` |

## 四、后端/前端回归验证

在目标环境或同版本构建环境运行：

```bash
python -m pytest tests/test_deploy_preflight.py tests/test_launch_check_service.py tests/test_production_evidence.py tests/test_live_broker_service.py -q
npm --prefix frontend run build
```

将命令、执行时间、结果写入：

```json
"regression": {
  "backend_tests_passed": true,
  "frontend_build_passed": true,
  "smoke_tests_passed": true,
  "tested_at": "<ISO8601 time>",
  "commands": [
    "python -m pytest tests/test_deploy_preflight.py tests/test_launch_check_service.py tests/test_production_evidence.py tests/test_live_broker_service.py -q",
    "npm --prefix frontend run build"
  ]
}
```

## 五、备份与恢复验证

### 5.1 生成 MySQL 备份

示例：

```bash
mysqldump --single-transaction --routines --triggers --events "$MYSQL_DATABASE" | gzip > backups/mysql-dump-YYYYMMDDHHMM.sql.gz
sha256sum backups/mysql-dump-YYYYMMDDHHMM.sql.gz
ls -l backups/mysql-dump-YYYYMMDDHHMM.sql.gz
```

记录：

- artifact 文件名
- created_at
- sha256
- size_bytes

### 5.2 隔离环境恢复验证

禁止直接覆盖生产库。应恢复到隔离库，例如：

```text
restore_check_prod_YYYYMMDD
```

恢复后执行 schema / 数据一致性抽查，并记录：

```json
"backup": {
  "artifact": "mysql-dump-YYYYMMDDHHMM.sql.gz",
  "created_at": "<ISO8601 time>",
  "sha256": "<sha256>",
  "size_bytes": 123456,
  "restore_verified": true,
  "restore_target": "restore_check_prod_YYYYMMDD",
  "restore_checked_at": "<ISO8601 time>"
}
```

## 六、迁移验证

确认 Alembic revision：

```bash
alembic current
python scripts/validate_mysql_schema.py
```

如果有 staging migration 脚本：

```bash
python scripts/staging_mysql_migration.py
```

需要填写：

```json
"migration": {
  "alembic_revision": "0022_stock_daily_bar_timestamps",
  "schema_validation_ok": true,
  "reconciliation_ok": true,
  "idempotent_rerun_ok": true,
  "rollback_drill_ok": true
}
```

说明：`rollback_drill_ok` 不一定要求真实生产降级，但必须完成发布负责人认可的回滚演练或兼容回滚方案验证。

## 七、发布证据

需要完成：

```json
"release": {
  "deploy_preflight_ok": true,
  "repo_hygiene_ok": true,
  "rollback_plan_reviewed": true,
  "release_notes_reviewed": true
}
```

建议记录：

```bash
python scripts/deploy_preflight.py
python scripts/check_repo_hygiene.py
```

并人工确认：

- 回滚方案已审阅
- 发布说明已审阅
- commit `c64c72e` 的 staged diff 审阅报告已阅读：`docs/software-company/aistocks-staged-diff-review-2026-05-09.md`

## 八、安全证据

必须确认：

```json
"security": {
  "secrets_rotated": true,
  "admin_password_rotated": true,
  "public_ports_reviewed": true,
  "csrf_headers_verified": true,
  "live_broker_policy_disabled": true
}
```

检查重点：

1. `SECRET_KEY` 是生产强随机值，不使用模板值。
2. 管理员默认密码已轮换。
3. 只有 frontend gateway 对外发布端口。
4. nginx 安全响应头存在。
5. CSRF / Cookie / Origin 策略验证通过。
6. `LIVE_BROKER_LAUNCH_POLICY=disabled`，即使 broker credentials configured 也不能开放实盘 adapter。

## 九、Soak 与 readiness 采样

至少采集两个 `/api/v1/readiness` 样本，建议间隔 30-60 分钟。

示例：

```bash
curl -sS https://<host>/api/v1/readiness | tee readiness-1.json
curl -sS https://<host>/api/v1/readiness | tee readiness-2.json
```

每个样本必须满足：

| 字段 | 期望 |
|---|---|
| ready | true |
| database_dialect | mysql |
| cache_backend | redis |
| task_queue_backend | redis |
| task_execution_mode | worker |
| repository_backends.* | mysql |
| tasks_stale | 0 |

写入 evidence：

```json
"soak": {
  "started_at": "<ISO8601 time>",
  "ended_at": "<ISO8601 time>",
  "readiness_samples": [
    {
      "at": "<ISO8601 time>",
      "ready": true,
      "database_dialect": "mysql",
      "cache_backend": "redis",
      "task_queue_backend": "redis",
      "task_execution_mode": "worker",
      "repository_backends": {
        "PICKS_REPOSITORY_BACKEND": "mysql",
        "AUTH_REPOSITORY_BACKEND": "mysql",
        "AUDIT_REPOSITORY_BACKEND": "mysql",
        "SETTINGS_REPOSITORY_BACKEND": "mysql",
        "LOGS_REPOSITORY_BACKEND": "mysql",
        "STRATEGY_POOL_REPOSITORY_BACKEND": "mysql",
        "STRATEGY_REPOSITORY_BACKEND": "mysql",
        "TRADING_REPOSITORY_BACKEND": "mysql"
      },
      "tasks_stale": 0
    }
  ],
  "errors": []
}
```

## 十、验证真实 evidence

填写完成后运行：

```bash
python scripts/production_evidence.py --evidence docs/product/PRODUCTION_EVIDENCE.prod.json
```

通过标准：

```text
ok=true
core_evidence_ok=true
```

如果 SQLite retirement 仍为 false，可以接受为 v1.0 advisory 未完成；但不能删除 SQLite 兼容分支。

## 十一、上线判定

| 条件 | 判定 |
|---|---|
| deploy preflight PASS | 必须 |
| 后端关键测试 PASS | 必须 |
| 前端 build PASS | 必须 |
| backup restore verified | 必须 |
| migration evidence PASS | 必须 |
| release evidence PASS | 必须 |
| security evidence PASS | 必须 |
| regression evidence PASS | 必须 |
| soak readiness samples PASS | 必须 |
| production evidence core PASS | 必须 |
| SQLite retirement advisory | v1.0 可不完成，但需保留兼容代码 |

只有全部核心项满足，才可宣称：

```text
AiStocks v1.0 production evidence passed; launch gate passed.
```

## 十二、失败处理

任何一项失败：

1. 不宣称上线完成。
2. 保留当前版本日志、容器状态、evidence 文件和错误输出。
3. 按 `docs/refactor/PRODUCTION_DEPLOY_RUNBOOK.md` 执行故障排查。
4. 必要时回滚到上一已验证版本。
5. 修复后重新执行本 runbook。

## 十三、实盘交易开关注意事项

v1.0 默认不开放实盘自动交易。

即使未来要启用，也必须另走审批：

1. 单独 PR 修改 `LIVE_BROKER_LAUNCH_POLICY`。
2. 完成 broker adapter 合约验收。
3. 完成小额/沙箱/人工确认链路。
4. 完成审计日志和人工 kill switch 验证。
5. 更新 production evidence 并重新通过。

未经审批，必须保持：

```text
LIVE_BROKER_LAUNCH_POLICY=disabled
```
