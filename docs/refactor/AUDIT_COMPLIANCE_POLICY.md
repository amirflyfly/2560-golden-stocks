# 审计日志合规策略

## 记录范围

审计日志覆盖用户、租户、密码、扫描、行情同步、任务取消、策略回测等高风险操作。每条记录包含用户、租户、动作、资源、结果、来源 IP、User-Agent、详情 JSON 和完整性哈希。

## 脱敏规则

递归脱敏以下字段名：`password`、`password_hash`、`token`、`auth_token`、`csrf_token`、`cookie`、`cookies`、`secret`、`api_key`。命中字段统一写入 `***REDACTED***`，不得保存明文。

## 完整性校验

写入审计详情时生成 `integrity_hash`。哈希基于 user_id、username、tenant_id、action、resource_type、resource_id、result 和脱敏后的 detail 计算，用于发现导出或人工核查时的异常篡改。

## 保留与导出

- 默认保留不少于 180 天；生产环境可按合规要求延长。
- 导出时必须使用脱敏后的 `detail`，不得重新拼接原始请求体。
- 批量导出应记录导出人、时间、过滤条件和用途。

## 查询与访问控制

审计查询仅允许管理员访问，并应保留 tenant 过滤、action 过滤和 result 过滤能力。普通 viewer/editor 不应访问审计明细。

## 处置流程

发现审计缺失、哈希异常或敏感字段泄漏时，应先冻结相关日志文件和数据库快照，再按故障 runbook 记录影响范围、修复动作和复盘结论。
