# AiStocks v1.1 E2E Smoke Report

## 当前状态

发布相关全量 E2E 已完成复跑并全部通过。

本轮按当前仓库真实存在的 JS specs 执行发布相关全量复测，结果为 `13 passed (1.7m)`。当前可声明 release smoke 覆盖范围内 PASS；未执行不存在的 `settings.spec.js`，仅记录缺失事实，不伪造该 spec 结果。

## 覆盖范围

本轮 E2E 冒烟复测覆盖以下关键用户路径：

1. 登录
   - 未登录访问首页跳转登录页
   - admin 登录成功且刷新后会话保持
   - 错误密码展示登录失败

2. 市场同步
   - admin 可从数据中心页面触发市场同步与快照任务
   - 任务触发接口返回成功并刷新任务/数据状态

3. 扫描
   - admin 可创建扫描任务并看到数据质量字段
   - editor 可创建扫描任务
   - viewer 创建扫描任务时展示权限不足

4. 纸面交易
   - editor 可完成纸面交易闭环工作台检查
   - 覆盖信号应用、持仓/订单/成交/退出评估等主链路

5. 日报与外部推送
   - editor 可从 reports 页面生成 daily trading review
   - admin 可重试失败的外部推送投递
   - editor 可查看外部推送投递但重试受 admin 权限限制
   - viewer 可读报告且不会加载写权限相关推送审计端点

6. 工作流闭环
   - admin 可跨页面完成量化工作流闭环
   - 覆盖扫描、市场数据、纸面交易、报告等关键页面链路

## Spec 存在性确认

工作目录：`D:/AiStocks/frontend`

当前 `D:/AiStocks/frontend/e2e` 已确认存在的 spec 文件：

- `admin.spec.js`
- `auth.spec.js`
- `market-sync.spec.js`
- `operation-score.spec.js`
- `paper-trading.spec.js`
- `permissions.spec.js`
- `reports.spec.js`
- `scans.spec.js`
- `tenant-switch.spec.js`
- `workflow-closure.spec.js`

发布相关本轮实际执行 specs：

- `auth.spec.js`
- `market-sync.spec.js`
- `scans.spec.js`
- `reports.spec.js`
- `paper-trading.spec.js`
- `workflow-closure.spec.js`

`settings.spec.js`：不存在；按任务要求未硬跑，仅记录不存在。

## 实际测试时间

- 执行时间：2026-05-22 10:09-10:10 GMT+8
- 执行耗时：Playwright 汇总 `1.7m`

## 执行命令

```bash
cd D:/AiStocks/frontend && npx playwright test e2e/auth.spec.js e2e/market-sync.spec.js e2e/scans.spec.js e2e/reports.spec.js e2e/paper-trading.spec.js e2e/workflow-closure.spec.js --project=chromium
```

## 命令输出摘要

真实 stdout 摘要：

```text
Running 13 tests using 1 worker

ok  1 [chromium] › e2e\auth.spec.js:10:1 › 未登录访问首页会跳转到登录页
ok  2 [chromium] › e2e\auth.spec.js:17:1 › admin 可以登录且刷新后会话保持
ok  3 [chromium] › e2e\auth.spec.js:25:1 › 错误密码会显示登录失败
ok  4 [chromium] › e2e\market-sync.spec.js:11:1 › admin can trigger market sync and snapshot jobs from the data center page
ok  5 [chromium] › e2e\paper-trading.spec.js:11:1 › editor can review paper trading closed-loop workbench
ok  6 [chromium] › e2e\reports.spec.js:100:1 › editor can generate a daily trading review from the reports page
ok  7 [chromium] › e2e\reports.spec.js:119:1 › admin can retry failed external push deliveries from the reports page
ok  8 [chromium] › e2e\reports.spec.js:161:1 › editor can view external push deliveries but retry is admin-only
ok  9 [chromium] › e2e\reports.spec.js:177:1 › viewer can read reports without loading write-only push audit endpoints
ok 10 [chromium] › e2e\scans.spec.js:11:1 › admin 可以创建扫描任务并看到数据质量字段
ok 11 [chromium] › e2e\scans.spec.js:28:1 › editor 可以创建扫描任务
ok 12 [chromium] › e2e\scans.spec.js:35:1 › viewer 创建扫描任务会展示权限不足
ok 13 [chromium] › e2e\workflow-closure.spec.js:12:1 › admin can run the quant workflow closure through pages

13 passed (1.7m)
```

真实 stderr 摘要：

- Playwright webServer 成功启动本地后端：`Running on http://127.0.0.1:8765`。
- 健康检查成功：`GET /health HTTP/1.1 200`。
- 测试期间后端请求日志显示登录、健康检查、设置通知、扫描、任务、市场数据、纸面交易、报告、外部推送等接口均返回预期成功或权限相关响应：例如 `GET /api/v1/me 200`、`POST /api/v1/scans 202`、`POST /api/v1/market-data/sync 202`、`POST /api/v1/market-data/snapshots/sync 202`、`POST /api/v1/trading/paper/apply-signal 200`、`POST /api/v1/reports/daily-review 200`。
- stderr 主要为 Flask/Werkzeug 开发服务器日志和进度条输出；未见 Playwright test failure stack trace。

## 通过率

- Total Tests: 13
- Passed: 13
- Failed: 0
- Skipped: 0
- Flaky: 0
- Pass Rate: 100%
- Coverage: 发布相关指定已存在 specs 全覆盖；`settings.spec.js` 不存在，未纳入执行分母。

## 失败详情

| Test / Spec | Expected | Actual | Suspected Owner | Evidence |
| --- | --- | --- | --- | --- |
| `auth.spec.js` | 登录相关 3 条用例通过 | 3 passed | NoOne | stdout `ok 1`-`ok 3` |
| `market-sync.spec.js` | 市场同步用例通过 | 1 passed | NoOne | stdout `ok 4` |
| `paper-trading.spec.js` | 纸面交易工作台用例通过 | 1 passed | NoOne | stdout `ok 5` |
| `reports.spec.js` | 报告与外部推送 4 条用例通过 | 4 passed | NoOne | stdout `ok 6`-`ok 9` |
| `scans.spec.js` | 扫描与权限 3 条用例通过 | 3 passed | NoOne | stdout `ok 10`-`ok 12` |
| `workflow-closure.spec.js` | 工作流闭环用例通过 | 1 passed | NoOne | stdout `ok 13` |
| `settings.spec.js` | 如存在则执行 | 不存在，未执行 | NoOne | spec 存在性确认未列出该文件 |

本轮无失败 spec、无失败位置、无 error stack trace。

## Trace / Report 路径

- Playwright last run metadata：`D:/AiStocks/frontend/test-results/.last-run.json`
  - 内容摘要：`{"status":"passed","failedTests":[]}`
- `D:/AiStocks/frontend/test-results` 存在。
- 未发现 `D:/AiStocks/frontend/playwright-report` 目录。
- 因本轮全部通过，未生成失败 trace 路径。

## 智能路由判定

Routing Decision: NoOne

原因：发布相关指定且存在的 E2E specs 全部通过，真实输出为 `13 passed (1.7m)`；无 source bug、无 test bug、无环境阻塞证据。

若后续新增或恢复 `settings.spec.js`，建议单独纳入下一轮 release smoke 分母复跑。

## 最终结论

- Release E2E Smoke Result: PASS
- Routing Decision: NoOne
- 是否允许进入发布下一阶段：从本轮发布相关 E2E 冒烟结果看，允许进入下一阶段。
- 限制说明：本结论仅覆盖当前仓库真实存在并实际执行的发布相关 specs；`settings.spec.js` 当前不存在，未声明其 PASS。
