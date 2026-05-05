# 测试计划

## 后端测试

- API health check
- 统一响应格式
- 配置加载
- SQLAlchemy models 导入
- MarketDataProvider 抽象与 mock provider

## 多租户测试

- tenant A 不能读取 tenant B 的 picks
- tenant A 不能读取 tenant B 的 scan_results
- tenant A 不能修改 tenant B 的 strategies
- 无 X-Tenant-ID 时拒绝访问租户业务接口

## 认证与安全回归测试

- 未登录访问 /api/v1 受保护接口返回 401
- 登录后缺失或非法 X-Tenant-ID 返回租户错误
- X-User-ID 与当前登录用户不一致时拒绝访问
- 写接口缺失 CSRF token 返回 403
- Origin、Referer、Sec-Fetch-Site 跨站写请求返回 403
- 同源写请求携带合法 CSRF token 可正常执行
- 登出、停用用户、过期 session、伪造 session token 后 API 立即失效
- viewer 角色可读但禁止写报告、扫描等受控资源
- 安全响应头、CSP、CSRF cookie、session cookie 属性必须持续返回

## 数据源测试

- mock provider 返回标准字段
- akshare provider 可导入
- mootdx 未安装时 provider 给出明确错误
- mootdx 返回带时间的 datetime 字符串时可正常解析日期
- 数据源降级路径可测试

## 前端测试

- 构建通过
- API client 正确处理统一响应
- 登录态和租户切换状态可维护
- 涨红跌绿样式符合中国市场习惯
