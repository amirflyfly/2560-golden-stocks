# 量化交易闭环复盘与改善清单

## 闭环现状

本项目的主流程已经具备从数据同步到复盘推送的基础闭环：

1. 自动同步股票数据：`/api/v1/market-data/sync`、`/api/v1/market-data/snapshots/sync` 和 `market.auction.sync` 进入任务队列，由 `SyncApiService` 同步日线、分钟线、实时快照和 9:20-9:25 集合竞价快照。
2. 集合竞价监测：`strategy_first_limit_up.py` 优先读取 `stock_auction_snapshots`，输出 `auction_confirmed`、`preopen_watch`、`auction_rejected`，生产运行只应把 `auction_confirmed` 转成买入信号。
3. 涨停隔日自动买入：首板/涨停策略生成候选标的后，进入 picks、reports、trading 链路；纸上交易可自动下单，实盘交易必须经过 live broker 安全边界。
4. 自动买卖：`PaperTradingService` 负责生成纸上委托、成交和持仓，`evaluate-exits` 负责卖出评估；`LiveBrokerService` 默认禁用和 dry-run，必须显式配置、管理员权限和确认口令才允许实盘委托。
5. 分析复盘与推送：daily review 汇总纸上交易、策略复盘、收益归因和通知内容；外部推送现在进入 `external_push_deliveries` 队列，保留可追踪的发送审计记录。

## 已完成改善

1. 页面级闭环测试：新增 `frontend/e2e/workflow-closure.spec.js`，通过页面完成同步、快照、扫描、卖出评估、日报复盘和外部推送队列审计。
2. E2E 稳定性：`frontend/package.json` 增加 `pretest:e2e`，页面测试前自动构建前端，避免使用过期 dist。
3. 本地测试环境自愈：`frontend/playwright.config.js` 自动选择 `.venv-codex`、`.venv` 或环境变量中的 Python，并自动使用本机可用 Chromium，降低 Windows 环境下的测试失败率。
4. 复盘推送可靠性：daily review 外部推送由同步直发改为 `ExternalPushService.enqueue_dispatch()`，生成 delivery 队列和审计记录，避免复盘接口被外部 webhook 失败阻断。
5. 测试断言同步：`tests/test_daily_review.py` 已按队列化推送更新断言，验证 `queued` 状态和 delivery 写入。
6. 文档可读性：修复 `docs/quant_workflow_closure_review.md` 乱码，沉淀当前闭环、改善项和剩余风险，作为后续迭代入口。

## 验证清单

已验证的命令：

```powershell
npm --prefix frontend run build
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; .venv-codex\Scripts\python.exe -m pytest tests\test_daily_review.py tests\test_external_push_api.py
npm --prefix frontend run test:e2e
```

预期结果：

1. 前端构建通过。
2. daily review 与 external push 后端测试通过。
3. 页面 E2E 全部通过，覆盖用户可见的核心闭环。

## 剩余风险

1. 真实 Level2 集合竞价数据尚未接入：akshare/mootdx 当前只能提供 `derived_l1` 能力，不能伪造撤单、封单和盘口层级；生产级竞价确认需要真实 Level2 或券商专线 provider。
2. 实盘 broker 仍是适配契约，不是完整券商 SDK：签名、撤单回报、成交回报、对账修复和限流参数需要按具体券商插件落地。
3. 历史乱码仍存在：本轮只修复闭环复盘文档；全仓库中文乱码需要按 `scripts/encoding_audit.py` 的 plan 分批处理，避免误改业务代码。
4. `.venv-codex` 是本地验证环境：已加入 `.gitignore`，不应提交；CI 应继续使用干净依赖安装。
5. 页面测试覆盖的是安全纸上闭环：实盘买入/卖出因安全原因不能在 E2E 中真实触发，只能验证权限、dry-run 和确认边界。

## 后续改善顺序

1. 接入真实集合竞价 Level2 provider，并把 `auction_confirmed` 的入选证据写入可审计字段。
2. 给 external push 增加运营页面的筛选、重试按钮和通道 SLA 统计。
3. 增加 live broker 沙盒插件，用券商模拟环境跑通签名、下单、撤单、成交回报和对账。
4. 按文件分批治理乱码，优先修复用户可见页面、报告、文档和测试输出。
5. 把页面闭环测试加入 CI，并固定浏览器安装或缓存策略，避免依赖本机 `D:\playwright-browsers`。
