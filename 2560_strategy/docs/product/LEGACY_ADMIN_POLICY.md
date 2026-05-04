# Legacy Admin Policy

P6 阶段不再允许 legacy admin 承接新的用户管理能力。已有能力按替代程度分层处理。

## 已迁移到 React

- `/admin/users`
- `/admin/users/create`
- `/admin/users/<id>/toggle`
- `/admin/users/<id>/password`

处理策略：

- 页面跳转 `/app?page=admin`。
- legacy 写接口返回 `410`。
- React v1 admin 负责用户列表、角色修改、启停和审计查看。

## 暂时保留

- `/admin/backups`
- `/admin/backups/<name>/download`
- `/admin/restore`
- `/admin/backup-key`
- `/admin/tradingagents-config`

保留原因：

- React admin 尚未提供备份、恢复、密钥和模型配置等运维能力。
- 这些入口仍要求 admin 角色。
- 所有 legacy admin 响应带 `X-Legacy-Page: deprecated` 和 React successor link。

后续替代标准：

- React admin 提供备份列表、创建、下载、恢复预览、恢复确认、密钥轮换和 TradingAgents 配置表单。
- v1 API 提供对应写接口、审计日志和 CSRF/tenant/admin 权限测试。
- 完成替代后，legacy POST/DELETE 写接口改为 `410`。

## 禁止事项

- 不向 legacy `/admin/*` 增加新管理能力。
- 不在 legacy admin 中绕过 v1 审计新增高风险写操作。
- 不在没有恢复预览和回滚说明的情况下扩大 restore 能力。
