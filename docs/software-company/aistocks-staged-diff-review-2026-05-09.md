# AiStocks staged diff 审阅报告（2026-05-09）

## 结论

当前发布索引已经收敛为一次“大规模目录迁移 + 上线门禁补强”的 staged 变更。代码侧关键验证已通过，但 commit 前仍建议人工复核迁移边界和删除项。

- 本地后端关键测试：PASS（25 passed）
- 前端 Vite build：PASS
- deploy preflight：PASS（43/43 checks，0 failed）
- Git critical files tracked：PASS
- 真实 production evidence：未提供，不能视为生产证据通过
- 建议状态：可以进入准生产/生产证据采集阶段；不建议直接宣称完整生产上线 PASS

## 暂存区规模

| 类型 | 数量 |
|---|---:|
| 总变更文件 | 437 |
| 重命名 R | 381 |
| 删除 D | 44 |
| 新增 A | 9 |
| 修改 M | 3 |
| 代码行变化 | 3996 insertions / 16618 deletions |

## 目录分布 Top

| 路径/目录 | staged 项数 |
|---|---:|
| backend | 135 |
| frontend | 51 |
| docs | 49 |
| tests | 35 |
| skills | 29 |
| templates | 25 |
| alembic | 23 |
| scripts | 20 |
| data | 5 |
| 2560_strategy | 4 |

## 新增文件

| 文件 | 说明 |
|---|---|
| `.workbuddy/memory/2026-05-08.md` | 工作记忆文件，是否纳入发布 commit 需人工确认 |
| `backend/application/launch_check_service.py` | 新增 P0 launch check 聚合服务 |
| `backups/.gitkeep` | 备份目录占位，真实备份仍应忽略 |
| `docs/product/PRODUCTION_EVIDENCE.md` | 生产证据说明文档 |
| `docs/software-company/aistocks-analysis.md` | 软件公司视角项目分析 |
| `docs/software-company/aistocks-architecture-plan.md` | 架构改造计划 |
| `docs/software-company/aistocks-improvement-prd.md` | 改进 PRD |
| `frontend/src/components/common/RiskDisclaimer.jsx` | 统一风险声明组件 |
| `tests/test_launch_check_service.py` | launch check 测试 |

## 修改文件

| 文件 | 说明 |
|---|---|
| `.gitignore` | 调整 backups 忽略规则，使 `.gitkeep` 可跟踪、真实备份继续忽略 |
| `package.json` | 根目录依赖/脚本变化，需确认与前端目录分工 |
| `package-lock.json` | 根目录 lockfile 大幅变化，需重点复核是否应保留 |

## 关键上线文件变化

| 文件 | 变更规模 | 审阅重点 |
|---|---:|---|
| `backend/application/launch_check_service.py` | +153 | P0 上线聚合门禁 |
| `backend/application/live_broker_service.py` | 大文件迁移+修改 | `LIVE_BROKER_LAUNCH_POLICY=disabled` 默认阻断实盘 adapter |
| `backend/application/monitoring_service.py` | 大文件迁移+修改 | readiness 纳入 live broker / market data 检查 |
| `backend/api_v1/routers/admin.py` | 大文件迁移+修改 | `/admin/launch-check` admin-only 路由 |
| `scripts/production_evidence.py` | 大文件迁移+修改 | 生产证据规则、expected revision、release/security/regression/soak 校验 |
| `scripts/deploy_preflight.py` | 大文件迁移+修改 | 43 项部署预检规则，含 Git critical files、backups、Redis/worker、live broker policy |
| `docker-compose.yml` | 大文件迁移+修改 | migration/seed/schema-gate、healthcheck、Redis/worker、live broker disabled |
| `.env.example` | 大文件迁移+修改 | MySQL repository backend、Redis queue/cache、live broker disabled |
| `frontend/src/components/common/RiskDisclaimer.jsx` | +12 | 统一风险声明 |
| `frontend/src/pages/DashboardPage.jsx` | 大文件迁移+修改 | 今日使用结论、readiness、上线检查入口 |
| `frontend/src/pages/MonitoringPage.jsx` | 大文件迁移+修改 | launch check 展示与复制摘要 |
| `tests/test_deploy_preflight.py` | 迁移+测试期望修复 | 无 `.env` 时接受 optional，有 `.env` 时仍要求实际 Redis/worker 检查 |
| `tests/test_launch_check_service.py` | +68 | 测试隔离，避免 production settings cache 污染 |

## 已收敛的 rename pairing 风险

之前 `backups/.gitkeep` 曾被识别为：

```text
R100 2560_strategy/tests/__init__.py -> backups/.gitkeep
```

这会误导审阅。当前已调整为：

```text
A     backups/.gitkeep
R100  2560_strategy/tests/__init__.py -> tests/__init__.py
```

结论：该风险已收敛，当前表达更清晰。

## 高风险删除项

以下删除项建议 commit 前人工确认：

### 1. 根目录身份/代理文件删除

```text
AGENTS.md
BOOTSTRAP.md
HEARTBEAT.md
IDENTITY.md
SOUL.md
TOOLS.md
USER.md
```

风险：这些可能是历史 agent/工作区配置文件。若它们不应随产品发布，应确认删除合理；若仍被某些工具依赖，应恢复或迁移。

### 2. 根目录 skills 删除

```text
skills/*.md
skills/*.js
```

共 29 项删除。风险：这些可能是历史技能文件。如果项目不再托管 user-level skills，删除合理；否则需迁移到 `.workbuddy/skills` 或用户级技能目录。

### 3. 根目录 memory 删除

```text
memory/2026-03-02.md
memory/2026-03-03.md
每日金股/2026-03-03_10-30.md
```

风险：包含历史记忆/业务笔记。若是非产品资产，删除合理；若仍需保留，应另行归档。

### 4. 旧脚本删除

```text
scripts/run_backup.py
```

风险：确认是否已被 `scripts/backup_restore_drill.py`、`scripts/maintenance/mysql_restore_check.sh` 或新 runbook 取代。

### 5. 旧 `2560_strategy` 内重复文件删除

```text
2560_strategy/.gitignore
2560_strategy/package.json
2560_strategy/package-lock.json
2560_strategy/docs/product/PRODUCTION_EVIDENCE.md
```

风险：这些看起来是整体迁移后旧目录内重复文件删除；若 `2560_strategy/` 目录要退役，删除合理。

## 审阅建议

### 必须复核

1. 确认 `2560_strategy/` 到仓库根目录的整体迁移是预期状态。
2. 确认 44 个删除项均不再需要。
3. 确认 `skills/` 与 `memory/` 删除不影响用户级/项目级技能和历史资料。
4. 确认根目录 `package.json` / `package-lock.json` 是否仍应存在，以及是否与 `frontend/package.json` 职责清晰。
5. 确认 `.workbuddy/memory/2026-05-08.md` 是否应进入产品发布 commit。

### 上线前仍需完成

1. 在目标准生产/生产环境生成真实 production evidence。
2. 使用真实 `.env` 重新运行 `python scripts/deploy_preflight.py`。
3. 完成备份/恢复演练、迁移顺序、回滚方案、Redis/worker/MySQL 连通性确认。
4. 确认 live broker v1.0 默认禁用策略和开关审批流程。

## 建议 commit 策略

如果人工确认迁移边界无误，建议 commit message：

```text
Prepare AiStocks v1 launch gates and root migration
```

建议 commit 前最后运行：

```bash
python -m pytest tests/test_deploy_preflight.py tests/test_launch_check_service.py tests/test_production_evidence.py tests/test_live_broker_service.py -q
npm --prefix frontend run build
python scripts/deploy_preflight.py
git diff --cached --stat
git diff --cached --name-status
```
