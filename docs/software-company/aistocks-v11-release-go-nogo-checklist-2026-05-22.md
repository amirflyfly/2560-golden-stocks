# AiStocks v1.1 Release GO/NO-GO QA Checklist — 2026-05-22

## 1. QA 判定摘要

当前结论：**NO-GO**。

本清单仅制定发布前 QA 放行门槛，不执行测试，不修改业务代码。判定依据来自以下已落盘报告：

- `docs/software-company/aistocks-v11-e2e-smoke-report-2026-05-21.md`
- `docs/software-company/aistocks-v11-production-evidence-local-precheck-2026-05-22.md`
- `docs/software-company/aistocks-v11-git-boundary-audit-2026-05-22.md`

## 2. 当前状态总览

| 门槛项 | 当前状态 | QA 判定 | 证据 / 说明 |
| --- | --- | --- | --- |
| Clean / reviewed release commit | 工作区存在 staged / unstaged / untracked 混合状态；多处 `MM` / `AM`；Operation Score 需单独确认；运行数据需排除 | **NO-GO** | `aistocks-v11-git-boundary-audit-2026-05-22.md` 明确 Git 边界不可 GO |
| 发布相关全量 E2E | 已按当前真实存在的发布相关 specs 复跑 | **PASS** | Playwright `13 passed (1.7m)` |
| Deploy preflight | 本地 deploy preflight 已通过 | **PASS** | `deploy_preflight.py` JSON：`ok=true`，`61/61`，`failed=0` |
| Repo hygiene | 本地 repo hygiene 已通过 | **PASS** | `check_repo_hygiene.py --json`：`ok=true`，`total_paths=405`，`violation_count=0` |
| 真实 production evidence bundle | 尚未采集真实生产 / staging 目标证据；仅完成本地 precheck | **PENDING / NO-GO** | 目标环境信息、真实 API/page/log/DB/push evidence 均未提供；example evidence 校验失败属预期 |
| 回滚准备 | 未见真实备份、备份 sha256/size、恢复验证、迁移验证等完整证据 | **PENDING / NO-GO** | production evidence precheck 报告列为 evidence bundle incomplete |
| 敏感信息 / 运行数据排除 | hygiene 当前 PASS，但发布 commit 尚未 clean/reviewed；运行数据 `data/daily_selection.csv/json` 出现在工作区 | **NO-GO until final boundary clean** | Git 边界审计要求排除 `.env`、运行数据、缓存、构建产物、测试结果等 |

## 3. 发布前 GO/NO-GO QA 门槛清单

### 3.1 Clean / reviewed release commit

发布前必须满足：

- [ ] 工作区达到可审计状态：无未确认的 staged / unstaged / untracked 混合发布内容。
- [ ] 所有 `MM` / `AM` 文件完成逐文件片段审计，确认最终进入 release commit 的内容与 v1.1 P0 边界一致。
- [ ] release commit 只包含经 review 的 v1.1 P0 相关业务、测试、脚本、前端、后端、迁移、配置样例与必要文档。
- [ ] `Operation Score` 相关文件完成 release owner 单独确认；未确认前不得混入 v1.1 P0 release commit。
- [ ] 所有 `docs/software-company/aistocks-v11-*` 文档逐份确认是否属于发布包；草稿、重复、未完成证据不得自动纳入。
- [ ] release commit hash、提交范围、文件清单、review 结论可追溯。

当前判定：**NO-GO**。Git 边界审计已明确当前工作区不能直接整体提交。

### 3.2 发布相关全量 E2E

发布前必须满足：

- [x] 对当前仓库真实存在的发布相关 E2E specs 执行全量 release smoke。
- [x] E2E 结果必须为 0 failed、0 skipped、0 flaky，且报告记录真实命令与 stdout/stderr 摘要。
- [x] 不得伪造不存在 spec 的 PASS；不存在的 spec 只能记录缺失事实。
- [ ] 若后续新增、恢复或修改发布相关 spec，必须重新纳入分母复跑。

当前判定：**PASS**。

已执行并通过的发布相关 specs：

- `auth.spec.js`
- `market-sync.spec.js`
- `scans.spec.js`
- `reports.spec.js`
- `paper-trading.spec.js`
- `workflow-closure.spec.js`

真实结果：`13 passed (1.7m)`。

限制说明：`settings.spec.js` 当前不存在，未执行，未声明 PASS。

### 3.3 Deploy preflight

发布前必须满足：

- [x] `scripts/deploy_preflight.py` 可运行并返回成功。
- [x] preflight 检查项全部通过，失败数为 0。
- [ ] 最终 release commit 固化后，需要在该 clean commit 上再次执行 preflight，确保结果仍为 PASS。

当前判定：**PASS with final-commit rerun required**。

本地 precheck 结果：`ok=true`，`total=61`，`failed=0`，`summary=preflight passed`。

### 3.4 Repo hygiene

发布前必须满足：

- [x] `scripts/check_repo_hygiene.py --json` 可运行并返回成功。
- [x] hygiene violation 为 0。
- [ ] 最终 release commit 固化后，需要再次执行 repo hygiene，确保没有敏感信息、运行数据、缓存、构建产物、测试结果或本机依赖目录进入提交范围。

当前判定：**PASS with final-commit rerun required**。

本地 precheck 结果：`ok=true`，`total_paths=405`，`violation_count=0`，`violations=[]`。

### 3.5 真实 production evidence bundle

发布前必须满足：

- [ ] 提供真实 production 或 staging 目标环境信息，包括 base URL、租户 / 测试账号、只读日志入口、只读 DB/查询方式、外部推送测试通道或可验证替代路径。
- [ ] 采集真实页面 evidence：登录、关键页面访问、市场同步、扫描、纸面交易、日报与外部推送相关页面。
- [ ] 采集真实 API evidence：健康检查、认证、市场同步、扫描创建、纸面交易 `apply-signal` / `evaluate-exits`、daily review、外部推送查询 / 重试权限等。
- [ ] 采集真实日志 evidence：请求链路、关键任务、外部推送、错误率、权限拒绝等必须可追溯。
- [ ] 采集真实 DB / 数据 evidence：关键表记录、任务状态、报告记录、外部推送记录、数据质量字段等必须可验证。
- [ ] evidence bundle 必须通过 `scripts/production_evidence.py --evidence <real_bundle>` 校验。
- [ ] 不得使用 `PRODUCTION_EVIDENCE.example.json` 或任何示例 / 模板文件冒充真实 production evidence。

当前判定：**PENDING / NO-GO**。

依据：本地 precheck 明确“Real production evidence is still pending”；example evidence 校验失败是预期结果，不可作为生产放行证据。

### 3.6 回滚准备

发布前必须满足：

- [ ] 发布包 / release commit 可定位，可回退到上一稳定版本。
- [ ] 数据库迁移具备回滚或恢复策略，包含 migration validation 证据。
- [ ] 备份文件、备份大小、sha256、存储位置与权限均有记录。
- [ ] 恢复验证完成，并记录恢复命令、耗时、结果与操作者。
- [ ] 回滚触发条件明确，包括 E2E 失败、production evidence 失败、关键 API 错误率异常、外部推送异常、数据质量门禁失败等。
- [ ] 回滚责任人、审批人、沟通渠道与恢复后验证步骤明确。

当前判定：**PENDING / NO-GO**。

依据：production evidence precheck 报告指出当前 evidence bundle 缺少 backup sha256/size、restore verification、migration validation、release/security/regression approvals 等内容。

### 3.7 敏感信息 / 运行数据排除

发布前必须满足：

- [ ] `.env`、真实 token、真实账号密码、生产地址、密钥、cookie、session、证书等不得进入 release commit。
- [ ] `data/daily_selection.csv`、`data/daily_selection.json` 等本地运行数据不得进入 release commit，除非 release owner 明确确认其为必要、脱敏、稳定样本。
- [ ] `node_modules/`、`frontend/node_modules/`、Playwright 浏览器缓存、本机工具缓存不得进入 release commit。
- [ ] `.pytest_cache/`、`__pycache__/`、logs、frontend test-results、playwright-report、构建产物、`.workbuddy/` 等运行 / 缓存 / 临时产物不得进入 release commit。
- [ ] `.env.example` 如纳入发布，必须确认仅包含脱敏占位符，不含真实密钥、token、账号或生产内部地址。
- [ ] 最终 release commit 前后均需保留 repo hygiene 0 violation 证据。

当前判定：**NO-GO until final boundary clean**。

依据：repo hygiene 本地检查当前 PASS，但 Git 边界仍 NO-GO，且运行数据已出现在工作区，必须在 release commit 边界清理完成后重新确认。

## 4. GO 条件

只有同时满足以下条件，QA 才可将总体状态从 NO-GO 改为 GO：

1. Git 边界变为 clean / reviewed release commit，且 release commit hash 固化。
2. 当前发布相关全量 E2E 在最终 release commit 上仍为 PASS。
3. Deploy preflight 在最终 release commit 上仍为 PASS。
4. Repo hygiene 在最终 release commit 上仍为 PASS，且敏感信息 / 运行数据 / 缓存 / 构建产物均已排除。
5. 真实 production 或 staging evidence bundle 已采集，且通过 `production_evidence.py` 校验。
6. 回滚准备完成，包括备份、校验、恢复验证、迁移验证、责任人与触发条件。
7. 所有 release owner 单独确认项已关闭，包括 Operation Score 是否进入 v1.1 P0 边界。

## 5. NO-GO 触发条件

任一条件满足即维持或切换为 NO-GO：

- Git 工作区仍存在未审计的 staged / unstaged / untracked 混合状态。
- release commit 混入未确认功能、运行数据、敏感信息、缓存、构建产物或本机依赖目录。
- 发布相关 E2E 出现 failed / flaky / skipped 且未完成原因确认与修复。
- deploy preflight 或 repo hygiene 任一失败。
- 未提供真实 production/staging 目标，或未采集真实 evidence bundle。
- 使用 example/template evidence 冒充真实 production evidence。
- 缺少备份、恢复验证、迁移验证或回滚责任人。

## 6. 最终 QA 判定

- E2E：**PASS** — `13 passed (1.7m)`。
- Deploy preflight：**PASS** — `61/61`。
- Repo hygiene：**PASS** — `405` paths checked，`0` violations。
- Git 边界：**NO-GO** — 当前工作区不能直接整体提交。
- 真实 production evidence：**PENDING / NO-GO** — 未采集真实生产 / staging evidence bundle。
- 回滚准备：**PENDING / NO-GO** — 缺少备份、恢复验证、迁移验证等完整证据。

总体结论：**NO-GO**。

QA 不建议发布，直到 Git 边界清理为 clean/reviewed release commit，并完成真实 production evidence bundle 与回滚准备验证。
