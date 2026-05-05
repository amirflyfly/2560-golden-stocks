# 安全规划

## 当前风险

- 默认管理员账号风险。
- SECRET_KEY 配置风险。
- debug 模式风险。
- 多租户串数据风险。
- 模板内联脚本和 CSP 风险。

## 重构要求

- SECRET_KEY 必须来自环境变量。
- 禁止生产环境 debug。
- 密码使用 werkzeug 或 passlib 的强哈希。
- API 增加认证依赖。
- 租户接口必须校验用户和租户关系。
- 敏感接口增加权限检查。
- 操作日志记录 user_id、tenant_id、ip、user_agent。

## HTTPS / HSTS 部署拓扑

生产部署固定采用 **外部网关终止 TLS**，不在应用容器内直接管理证书。

### 选型结论

- **选择方案 A：外部网关 / 负载均衡 / Caddy / Traefik / 云厂商 SLB 终止 HTTPS。**
- 容器内 `frontend` nginx 仅监听 HTTP `5174`，负责静态资源托管和向 `backend:8765` 内部反代。
- 暂不采用方案 B“容器 nginx 终止 TLS”，因此 Compose 不发布 `443`，不挂载证书目录，也不在 `frontend/nginx.conf` 中维护 `listen 443 ssl`。

### 请求链路

```text
Browser HTTPS :443
  -> External TLS Gateway / LB / Reverse Proxy
  -> HTTP to frontend:5174 on private host/network
  -> frontend nginx /api/* proxy_pass http://backend:8765/api/*
  -> backend gunicorn app:app on internal Docker network
  -> MySQL / Redis internal Docker network only
```

### 外部网关必须配置

- 监听 `443` 并使用有效证书。
- 将 `80` 永久重定向到 `443`。
- 上游只转发到 `frontend:5174`，不得直连 `backend:8765`、MySQL 或 Redis。
- 传递代理头：`Host`、`X-Forwarded-For`、`X-Forwarded-Proto=https`、`X-Real-IP`。
- 启用 HSTS：`Strict-Transport-Security: max-age=31536000; includeSubDomains`。
- 若确认所有子域均支持 HTTPS，再考虑追加 `preload` 并提交浏览器 HSTS preload list。

### 容器侧约束

- `docker-compose.yml` 只发布 `frontend` 网关端口；`mysql`、`redis`、`backend` 只允许内部网络访问。
- `frontend/nginx.conf` 保留 HSTS 与安全响应头作为二层保护，但 TLS 证书和 HTTPS 跳转由外部网关负责。
- 后端只信任同源访问和 CSRF 保护，不把容器端口直接暴露给公网。

## 权限粒度

```text
strategy:read
strategy:write
scan:run
scan:read
pick:read
pick:write
report:read
report:write
admin:user_manage
admin:tenant_manage
```
