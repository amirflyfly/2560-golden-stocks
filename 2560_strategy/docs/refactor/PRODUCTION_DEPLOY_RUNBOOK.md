# 生产部署实战 Runbook

## 目标

为 2560 strategy 提供可复现的生产发布、验证、回滚与故障排查流程。本文默认采用当前架构：外部网关终止 TLS，frontend/nginx 暴露 5174，backend/MySQL/Redis 仅在 Compose 内部网络访问。

## 发布前检查

1. 确认 `.env` 已从 `.env.example` 派生，并替换所有生产密钥、数据库密码、管理员初始密码。
2. 确认 `MARKET_DATA_PROVIDER` 使用真实行情源，生产默认不允许静默 mock。
3. 执行只读预检：

```bash
python scripts/deploy_preflight.py
```

预检只读取配置和目录，不会启动、停止、移动或删除任何文件。

## 标准发布流程

1. 拉取代码并确认版本。
2. 执行自动化验证：后端测试、前端构建、Compose 配置检查。
3. 执行备份或确认最近备份可恢复。
4. 构建镜像并启动服务。
5. 验证：
   - frontend 首页 HTTP 200
   - `/api/v1/health` 返回 `status=ok`
   - MySQL、Redis、backend healthcheck 均 healthy
   - 管理员可登录，租户切换正常
   - 行情源 health 正常或 fallback 可见

## 回滚流程

1. 保留当前失败版本日志和镜像标签。
2. 切回上一个已验证镜像或代码版本。
3. 如涉及数据库迁移，先按迁移说明判断是否可安全 downgrade；不可 downgrade 时优先应用兼容修复。
4. 恢复服务后重复健康检查和登录/扫描烟测。
5. 在审计或运维记录中标注回滚原因、影响范围和恢复时间。

## 故障排查顺序

1. 访问失败：先查外部 TLS 网关，再查 frontend/nginx 5174。
2. API 失败：查 nginx `/api/` 反代、backend healthcheck、gunicorn 日志。
3. 登录或 CSRF 失败：查 Cookie SameSite、Origin/Referer、CSRF token。
4. 租户或权限失败：查 `X-Tenant-ID`、用户租户绑定、租户状态、角色。
5. 行情异常：查 provider、fallback_used、data_quality、errors。
6. 任务卡住：查任务 events、heartbeat_at、stale 标记和 failure_category。
7. 数据异常：先停止写入入口，再执行备份恢复 runbook 的只读校验。

## 备份前置要求

- SQLite/data 目录备份演练脚本必须可运行。
- MySQL 生产备份需保留 dump 命令、恢复命令和校验步骤。
- 任何恢复动作都必须先在隔离环境演练，不直接覆盖生产数据。

## 合规记录

每次发布至少记录：版本、执行人、时间、预检结果、测试结果、备份状态、发布结果、回滚计划。高风险动作需保留审计日志或人工变更记录。
