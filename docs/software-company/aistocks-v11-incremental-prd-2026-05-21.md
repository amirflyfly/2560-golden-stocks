# AiStocks v1.1 增量 PRD：可信投研工作台 P0 收敛版

> 文档角色：许清楚（Xu）· 产品经理  
> 版本日期：2026-05-21  
> 项目名称：`aistocks_v11_trusted_research_workspace`  
> 适用范围：AiStocks v1.1 增量改造需求定义  
> 说明：本文仅定义产品需求和验收标准，不包含代码修改；不构成投资建议或上线完成声明。

---

## 1. 背景

AiStocks 当前已具备 A 股短线投研工作台的基本闭环：今日工作台、市场发现、策略扫描、选股池、K 线、复盘、回测、研究报表、模拟验证、生产监控与后台管理。

既有分析文档指出，系统已经形成较强工程基础：React/Vite 前端、Flask `/api/v1`、MySQL/Alembic、Redis worker、数据质量门禁、上线检查服务、部署预检与 production evidence 框架。但 v1.1 仍需把“功能存在”收敛为“每日可判断、异常可解释、数据可信、上线可证明”。

当前关键问题：

1. **首页仍需从状态聚合升级为行动指挥台**：用户应一眼知道今天是否可扫描、可复盘、可回测、可上线，以及阻断原因和下一步动作。
2. **数据质量规则需要产品化落地**：`DataQualityGateService` 已有 `data-quality-gate/v1` 决策结构，但扫描、入池、回测、报表、模拟验证等页面需要一致展示与行为。
3. **非投资建议与误用防护需要全局统一**：扫描、回测、报表、K 线、模拟交易和导出均应清晰声明“仅供研究和复盘”。
4. **上线门禁需要对管理员可见**：`LaunchCheckService` 已聚合 readiness、repository backend、live broker、production evidence、deploy preflight、repo hygiene、legacy policy 等门禁，但前端需要集中可理解地展示。
5. **导航和范围需要控制**：`App.jsx` 当前将“Trading/模拟交易”置于首组，易误导产品定位。v1.1 应突出投研主线，模拟交易降级为“模拟验证”。

---

## 2. 产品目标

v1.1 定位为：**AiStocks 可信 A 股短线投研工作台 P0 收敛版**。

### 2.1 Product Goals

1. **每日行动可判断**：用户进入首页后，必须能判断今日是否可扫描、可复盘、可回测、可上线，并看到阻断原因和下一步动作。
2. **投研结论可解释**：扫描、入池、回测、报表、模拟验证必须展示数据来源、质量等级、fallback/mock 状态和非投资建议提示。
3. **上线状态可证明**：管理员必须能集中查看 P0 上线门禁、失败项、证据路径和安全边界，避免用分散脚本人工拼接判断。

### 2.2 成功标准

- 普通研究员能从首页判断今日是否可继续投研动作。
- viewer 可读不可写，写操作禁用原因明确，后端仍返回 403。
- mock 数据在生产主流程被阻断；fallback/unknown 数据被清晰警示或要求确认。
- 管理员能看到上线门禁总状态、失败门禁、证据来源和下一步动作。
- 扫描、回测、报表、模拟验证、导出均包含非投资建议或等价风险声明。

---

## 3. 范围与不做范围

### 3.1 本轮范围（v1.1 必做）

本轮只做 P0 收敛，目标是把已有能力串成可信闭环：

1. 今日行动指挥台 v2。
2. 数据质量门禁展示与阻断规则统一。
3. 全局非投资建议与风险声明统一。
4. 管理员上线检查中心 / 上线门禁面板。
5. live broker / 模拟验证边界提示。
6. 导航优先级调整：突出工作台、市场发现、策略扫描、选股池、回测/报表；模拟交易降级为模拟验证。
7. viewer/admin/editor 权限提示与验收。
8. P0 系统测试和上线证据验收清单。

### 3.2 下一迭代准备（P1，仅设计或预留）

以下仅作为 v1.2 或上线后首轮增强准备，不阻塞 v1.1：

- 复盘中心 v1：T+1/T+5、逾期、复盘模板、质量评分。
- 策略生命周期 v1：研发/观察/启用/暂停/退役、版本、变更原因。
- 报表策略决策视图：保留/观察/停用建议，数据质量剔除前后对比。
- API 契约文档与统一错误码。
- 任务系统事件、重试、死信和 worker 可观测增强。

### 3.3 明确不做范围

- 不开放实盘自动交易。
- 不做完整移动端。
- 不做完整量化 IDE。
- 不做商业化多租户计费、套餐、策略授权。
- 不在 v1.1 中重构全部 legacy/SQLite；只要求暴露面和风险可见、写入口受控。
- 不新增复杂外部数据源或板块/题材/龙虎榜等市场发现增强。

---

## 4. 用户故事

| 编号 | 用户故事 | 优先级 | 验收摘要 |
|---|---|---:|---|
| US-01 | 作为策略研究员，我进入首页后想知道今天是否可以扫描、复盘和回测，以便决定当天操作顺序。 | P0 | 首页显示“可正常使用 / 谨慎使用 / 不可扫描 / 不可上线”及原因。 |
| US-02 | 作为策略研究员，我查看扫描和候选结果时想知道数据是否可信，以便避免基于 mock/fallback 做错误判断。 | P0 | 每个关键结果展示 provider、actual_provider、data_quality、fallback_used、gate decision。 |
| US-03 | 作为复盘用户，我希望风险声明在扫描、回测、报表和模拟验证中持续可见，以便明确系统不是投资建议。 | P0 | 关键页面和导出均包含非投资建议提示。 |
| US-04 | 作为管理员，我需要一个上线检查入口查看 readiness、preflight、evidence、repo hygiene、live broker 等门禁，以便判断能否上线。 | P0 | admin-only 面板展示总状态、失败项、原因、证据路径和建议动作。 |
| US-05 | 作为 viewer，我只能查看结果，不能创建扫描、入池、复盘、回测或触发模拟/交易动作，以便降低误操作和越权风险。 | P0 | 前端禁用写入口并说明原因，后端写 API 返回 403。 |
| US-06 | 作为管理员，我需要确认 live broker 不会在 v1.1 被误触发，以便满足上线安全边界。 | P0 | live broker 默认 disabled/dry-run，普通用户不可见或不可用，admin 只能看到禁用原因。 |
| US-07 | 作为产品负责人，我希望 v1.1 不扩大功能范围，以便优先完成可信闭环和上线证据。 | P0 | P1/P2 不作为上线阻塞项，需求和测试按 P0 优先。 |

---

## 5. Requirements Pool

### 5.1 P0：本轮必须完成

| 编号 | 需求 | 说明 |
|---|---|---|
| P0-01 | 今日行动指挥台 v2 | 首页必须输出今日可用性结论、阻断原因、下一步动作和核心入口。 |
| P0-02 | 数据质量门禁统一 | 扫描、入池、回测、报表、模拟验证统一展示 `data-quality-gate/v1` 决策。 |
| P0-03 | mock/fallback/unknown 行为规则 | mock 生产阻断；fallback/unknown 统一警示或二次确认；coverage 不足显示原因。 |
| P0-04 | 非投资建议与风险声明 | 关键页面和导出均展示一致声明，回测强调历史不代表未来。 |
| P0-05 | 管理员上线检查中心 | 聚合 LaunchCheckService 门禁：readiness、repository backend、live broker、production evidence、preflight、repo hygiene、legacy policy。 |
| P0-06 | live broker 与模拟验证边界 | v1.1 不开放实盘交易；模拟交易降级命名为“模拟验证”；live broker 默认 disabled/dry-run。 |
| P0-07 | 权限与租户验收 | admin/editor/viewer 行为清晰；viewer 前端禁用 + 后端 403；跨租户访问拒绝。 |
| P0-08 | 导航信息架构收敛 | 模拟交易不再作为首组高权重入口；投研主线优先。 |
| P0-09 | 上线证据展示与失败解释 | 任一 P0 门禁失败时显示“不可上线”或“谨慎使用”，并给出修复建议。 |
| P0-10 | P0 自动化/手工验收清单 | 明确前端 build、后端关键测试、E2E smoke、preflight、repo hygiene、production evidence、security smoke。 |

### 5.2 P1：下一迭代准备，不阻塞 v1.1

| 编号 | 需求 | 说明 |
|---|---|---|
| P1-01 | 复盘中心 v1 | T+1/T+5 待办、逾期、优先级、复盘模板、批量复盘。 |
| P1-02 | 策略生命周期 v1 | 策略状态、版本、上线/停用原因、最近表现、复盘反馈。 |
| P1-03 | 报表决策视图 | 策略保留/观察/停用建议，fallback/unknown 剔除对比。 |
| P1-04 | 统一状态组件 | loading、empty、error、retry、permission denied 组件化。 |
| P1-05 | API 契约和错误码 | OpenAPI 或等价文档，统一分页、错误码、字段语义。 |
| P1-06 | 任务可观测增强 | 幂等 key、worker id、retry count、failure category、task event。 |

### 5.3 P2：中期规划

| 编号 | 需求 | 说明 |
|---|---|---|
| P2-01 | 市场发现增强 | 指数、板块、题材、资金流、龙虎榜、公告新闻。 |
| P2-02 | 策略实验室 | 参数实验、样本分层、市场环境归因。 |
| P2-03 | 组合风险管理 | 多策略组合、仓位模拟、相关性、回撤预警。 |
| P2-04 | 领域事件流 | 扫描、入池、复盘、回测、模拟验证形成可追溯事件。 |
| P2-05 | 可观测性平台 | 指标、日志、trace、告警、SLO。 |
| P2-06 | Legacy/SQLite 完全退役 | production evidence 通过后分阶段退役兼容路径。 |

---

## 6. 详细验收标准

### 6.1 P0-01 今日行动指挥台 v2

**必须展示：**

- 今日使用结论：`可正常使用 / 谨慎使用 / 不可扫描 / 不可上线`。
- 阻断或降级原因：readiness failed、mock、fallback、unknown、failed tasks、stale tasks、schema/backend 不安全、evidence missing。
- 下一步动作：创建扫描、查看待复盘、运行回测、同步行情、查看监控、上线检查。
- 数据空间 / tenant id。
- 行情源、实际行情源、provider chain、fallback_used、data_quality。
- failed/running/stale task 数量。
- admin-only 上线检查入口。
- 简版非投资建议提示。

**验收标准：**

- 当 readiness `ready=false` 时，首页结论必须是“不可上线”或等价危险状态。
- 当 data_quality=`mock` 或 provider=`mock` 时，首页结论必须是“不可扫描”或等价阻断状态。
- 当 fallback_used=true、data_quality=`fallback/unknown`、failedTasks>0 或 staleTasks>0 时，首页结论必须为“谨慎使用”。
- 首页不能只依赖颜色表达状态，必须有中文文字说明。
- viewer 不显示可写快捷动作，或按钮禁用并显示“只读角色不可操作”。

### 6.2 P0-02/P0-03 数据质量门禁统一

**统一展示字段：**

```json
{
  "schema_version": "data-quality-gate/v1",
  "action": "scan|pick|backtest|report|paper_trade",
  "status": "allowed|warning|blocked",
  "blocked": false,
  "grade": "primary|fallback|unknown|mock|ok",
  "source": "mootdx|akshare|mock|unknown",
  "fallback_used": false,
  "requires_confirmation": false,
  "warnings": []
}
```

**业务规则：**

| 场景 | mock | fallback/unknown | coverage/样本不足 |
|---|---|---|---|
| 首页结论 | 阻断扫描 | 谨慎使用 | 谨慎或阻断，取决于阈值 |
| 策略扫描 | 生产阻断 | 警告或二次确认 | 低于阈值阻断或警告 |
| 加入选股池 | 阻断 | 二次确认 | 警告并记录 |
| 回测 | 阻断 | 显示降级提示 | 样本不足强提示 |
| 报表 | 不纳入正式统计或标记 | 标记降级 | 支持剔除前后对比（P1） |
| 模拟验证 | 阻断或强确认 | 强提示 | 强提示 |

**验收标准：**

- 生产环境 `MARKET_DATA_PROVIDER=mock` 或 source 包含 mock 时，主流程必须阻断或 readiness/launch gate 失败。
- 扫描结果、入池候选、回测结果、报表聚合、模拟验证至少展示 quality/source/fallback/gate status 中的关键字段。
- fallback/unknown 状态下必须出现统一警示文案，不允许静默展示为正常数据。
- 如果允许 degraded 数据继续操作，必须记录 `requires_confirmation` 或等价审计/确认信息。
- 报表不得把 fallback/unknown 与 primary 结果混为同一可信等级。

### 6.3 P0-04 非投资建议与风险声明

**统一文案建议：**

> 本系统仅用于策略研究、模拟验证和复盘管理，不构成任何投资建议。行情数据可能延迟、缺失或降级，回测结果不代表未来收益。请勿将扫描、回测或报表结果直接作为实盘交易依据。

**展示位置：**

- 登录页或首次进入：完整声明。
- 首页：简版声明。
- 策略扫描页：结果区顶部声明“策略扫描仅供研究”。
- 回测页：指标区声明“历史回测不代表未来收益”。
- 报表页：页面和导出均包含免责声明。
- K 线页：行情延迟/缺失/复权口径提示。
- 模拟验证页：声明“模拟成交不代表真实成交”。

**验收标准：**

- E2E 或组件测试可验证关键页面存在“非投资建议”或等价中文声明。
- 报表导出包含 disclaimer 字段、页脚或说明区。
- data_quality 为 fallback/unknown/mock 时，风险提示升级。
- 页面文案不得暗示系统给出买卖建议、收益保证或实盘指令。

### 6.4 P0-05 管理员上线检查中心

**门禁来源：**

- `readiness`：服务、数据库、schema、cache、task queue、worker、repository backend。
- `repository_backends`：生产必须 MySQL 或生产安全后端。
- `live_broker_safe`：launch policy disabled，live orders not open。
- `production_evidence`：证据文件存在并校验通过。
- `deploy_preflight`：部署预检通过。
- `repo_hygiene`：仓库卫生检查通过。
- `legacy_policy_doc`：legacy 管理策略存在。

**页面必须展示：**

- 总状态：满足上线前置条件 / 谨慎试运行 / 不可上线。
- 失败门禁数量和名称。
- 每个门禁的 ok、summary、counts、checks。
- 证据路径或来源说明，尤其 production evidence。
- 失败后的建议动作，如补 production evidence、修复 repo hygiene、关闭 live broker、检查 schema revision。
- 密钥、token、数据库密码必须脱敏或不展示。

**验收标准：**

- 入口仅 admin 可见；editor/viewer 不可见或访问返回 403。
- 任一 P0 门禁失败时，总状态不能显示“可上线”。
- production evidence 缺失时显示“证据缺失 / 不可上线”。
- live broker policy 非 disabled 或 live orders ready 时显示高危失败。
- 门禁结果可复制为上线验收摘要，但不得泄露敏感配置。

### 6.5 P0-06 live broker 与模拟验证边界

**功能要求：**

- v1.1 不开放实盘自动交易。
- 导航名称从“模拟交易”建议调整为“模拟验证”。
- live broker 相关操作默认隐藏、禁用或 admin-only。
- 生产默认：`LIVE_TRADING_ENABLED=0`、`LIVE_TRADING_DRY_RUN=1` 或等价安全配置。
- 任一 live broker 尝试操作必须有审计。

**验收标准：**

- 普通 editor/viewer 看不到真实下单入口。
- admin 在未启用 live broker 时也不能提交真实订单，只能看到禁用原因。
- live broker 写 API 非 admin 返回 403。
- 上线检查中心展示 live broker 安全状态。

### 6.6 P0-07 权限与租户验收

**验收标准：**

- admin/editor/viewer 三类角色均有自动化或手工验收记录。
- viewer 不能创建扫描、加入选股池、更新复盘、运行高风险动作、管理用户、触发 live broker。
- 后端写操作不能仅依赖前端禁用，必须返回 403 或等价错误。
- 非绑定租户访问返回 403。
- 审计记录包含 user、tenant、action、resource、result。

### 6.7 P0-08 导航信息架构收敛

**建议导航：**

```text
今日
  - 今日行动指挥台

发现与研究
  - 市场发现
  - 策略扫描
  - 选股池
  - 股票 K 线

验证与报表
  - 策略管理 / 回测验证
  - 研究报表
  - 模拟验证

系统
  - 数据中心
  - 生产监控
  - 上线检查（admin-only）
  - 后台管理（admin-only）
```

**验收标准：**

- “Trading”不再作为首个导航分组。
- “模拟交易”更名或弱化为“模拟验证”。
- 首页、扫描、选股池、报表为主线高权重入口。
- admin-only 页面普通用户不可见或不可进入。

### 6.8 P0-10 P0 验收清单

上线前必须至少提供以下结果：

- 后端关键测试通过：data quality gate、launch check、production evidence、deploy preflight、task queue。
- 前端 production build 通过。
- Playwright smoke 覆盖登录、首页、扫描、viewer 权限、上线检查入口。
- `scripts/deploy_preflight.py` 通过。
- repo hygiene 通过。
- production evidence 在目标环境通过，或明确标记为 v1.1 内部试运行阻断项。
- security smoke：CSRF、CORS、Cookie、安全头、租户越权、viewer 写拒绝。
- release notes 记录已知风险、证据路径和 rollback plan。

---

## 7. 数据质量与非投资建议规则

### 7.1 数据质量等级

| 等级 | 用户表达 | 产品含义 | 默认行为 |
|---|---|---|---|
| primary/ok | 主数据源 / 正常 | 数据来自预期主源且未降级 | 允许操作 |
| fallback | 备用数据源 | 主源不可用或已降级 | 谨慎使用，关键动作需确认 |
| unknown | 数据质量未知 | 字段缺失或无法判断 | 谨慎使用，禁止静默当作正常 |
| mock | 模拟数据 | 仅开发链路验证 | 生产阻断 |

### 7.2 非投资建议规则

- 所有策略输出必须表达为“研究线索”“候选”“验证结果”，不得表达为“买入/卖出建议”。
- 回测结果必须附带假设条件、样本限制和“历史不代表未来”。
- 模拟验证必须说明不代表真实成交、流动性、滑点和交易限制。
- 数据质量异常时，不得给出确定性结论，应提示“需人工复核”。
- 导出文件必须保留风险声明，避免脱离系统上下文后被误用。

---

## 8. 上线门禁规则

### 8.1 总体规则

- 任何 P0 门禁失败，不允许显示“满足正式上线条件”。
- production evidence 缺失或失败时，只能标记为“内部试运行待补证据”或“不可上线”。
- live broker 不安全时必须硬阻断上线。
- repository backend 在生产非 MySQL 或非生产安全配置时必须阻断。
- readiness failed 必须阻断上线；如仅局部 warning，需展示具体影响范围。

### 8.2 门禁状态定义

| 状态 | 含义 | 用户表达 |
|---|---|---|
| passed | 所有 P0 门禁通过 | 满足上线前置条件 |
| warning | 有非阻断风险或证据不完整 | 可内部试运行，不建议正式上线 |
| blocked | 任一硬门禁失败 | 不可上线 |
| unknown | 门禁不可用或未采集 | 待补充证据，不可正式上线 |

### 8.3 硬阻断项

- readiness failed。
- production mock provider。
- live broker policy 非 disabled 或真实下单通道打开。
- production repository backend 不安全。
- production evidence 缺失或校验失败。
- viewer/tenant 越权测试失败。
- 缺 CSRF 或跨站写请求可成功。
- repo hygiene / deploy preflight 存在 P0 失败。

---

## 9. UI Design Draft

### 9.1 首页首屏

- 顶部：今日结论卡 + 数据空间 + 行情质量 badge。
- 第二行：风险声明条。
- 指标卡：readiness、行情源、数据质量、fallback、failed tasks、stale tasks、候选池、最近扫描。
- 行动区：创建扫描、查看选股池、运行回测、查看报表、同步行情、上线检查（admin-only）。
- 系统状态区：provider chain、actual provider、readiness checks、任务状态。

### 9.2 上线检查页 / Monitoring tab

- 顶部：总状态和失败数量。
- 门禁列表：每项 gate 的 ok/status、summary、failed count、checks。
- 证据区：production evidence 路径、最近执行时间、校验结果。
- 安全区：live broker、repository backend、legacy policy。
- 操作区：复制验收摘要、查看 Runbook、刷新检查。

### 9.3 数据质量组件

建议统一组件：

- `DataQualityGateBadge`：allowed/warning/blocked。
- `RiskNotice`：非投资建议 + 数据异常升级提示。
- `ActionBlocker`：说明为什么不可点击以及如何修复。
- `LaunchGatePanel`：管理员上线门禁摘要。

---

## 10. 待确认问题

1. v1.1 是否命名为“可信投研工作台”，还是继续沿用“上线改进版”？
2. 上线检查入口放在独立页面、MonitoringPage tab，还是 Dashboard admin-only 卡片跳转？
3. production evidence 的目标环境是本机 Docker Compose staging、正式生产服务器，还是用户指定环境？
4. fallback/unknown 数据下，哪些动作允许二次确认继续，哪些必须硬阻断？
5. 导航是否本轮必须调整，还是仅先调整文案和首页入口权重？
6. viewer 禁用态是否需要统一组件化到所有页面，还是先覆盖 P0 主流程？
7. 报表导出免责声明采用字段、页脚，还是单独说明 sheet/section？
8. live broker 在 v1.1 是完全隐藏，还是 admin-only 展示禁用状态？
9. P0 验收是否要求完整 Playwright E2E，还是 smoke + 手工补充证据？
10. production evidence 缺失时，v1.1 是否允许标记为“内部试运行”，或必须视为不可发布？

---

## 11. 推荐实施顺序

1. **先做 P0-02/P0-03 数据质量门禁规则统一**：保证后续页面展示和阻断依据一致。
2. **实现 P0-01 今日行动指挥台 v2**：让用户能一眼判断今日可用性。
3. **实现 P0-04 风险声明统一**：降低投研误用风险。
4. **实现 P0-05 上线检查中心**：让管理员能看懂 LaunchCheckService 的门禁结果。
5. **收敛 P0-06/P0-08 导航与 live broker 边界**：弱化实盘联想，明确模拟验证定位。
6. **补 P0-07 权限/租户验收与 P0-10 测试证据**：确保 v1.1 可验收。

---

## 12. 本轮不应扩大内容

为控制可实施范围，v1.1 不应在 P0 完成前启动以下开发：

- 新增复杂复盘模型和迁移。
- 新增策略生命周期表和事件流。
- 引入新的任务队列框架。
- 大规模重构 `backend/__init__.py`。
- 完整删除 SQLite/legacy。
- 新增外部新闻、题材、资金流数据源。

这些内容可以进入 v1.2/P1 设计，但不应影响 v1.1 的 P0 交付。