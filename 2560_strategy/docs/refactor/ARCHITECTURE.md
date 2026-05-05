# 重构架构规划

## 目标

将当前 Flask + Jinja + SQLite + 局部 React 的本地工具型项目，演进为前后端分离、多租户、MySQL、可插拔行情数据源的平台型系统。

## 架构决策

- 后端优先采用模块化单体，避免过早微服务化。
- API 层与业务层、数据层、第三方行情源隔离。
- 前端独立为 SPA，不再依赖 Jinja 页面渲染。
- 多租户采用共享 MySQL、业务表带 tenant_id。
- 行情数据通过 MarketDataProvider 抽象接入 mootdx、akshare、mock。

## 目标分层

```text
frontend SPA
  -> api/v1
    -> application services
      -> domain models / policies
      -> repositories
      -> market data providers
        -> mootdx / akshare / mock
      -> MySQL / Redis / task queue
```

## 模块边界

### api

只处理 HTTP 请求、响应、依赖注入、认证、租户上下文、错误转换。

### application

编排业务流程，例如运行扫描、创建策略、读取选股池。

### domain

承载核心领域概念和规则，不依赖 Web 框架、数据库和 mootdx。

### infrastructure

承载 MySQL、Redis、任务队列、mootdx、akshare 等外部系统适配。

## 数据源策略

业务代码禁止直接调用 mootdx 或 akshare，必须通过 MarketDataProvider。

默认顺序：

```text
mootdx -> akshare -> cache -> mock/error
```

## 多租户策略

- 用户可属于多个租户。
- 前端请求通过 X-Tenant-ID 指定当前租户。
- 后端必须校验用户是否属于该租户。
- 所有租户业务数据查询必须带 tenant_id。
- 股票基础信息和行情日线为全局公共数据，不带 tenant_id。

## API 规范

统一前缀：

```text
/api/v1
```

统一响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

统一分页：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 20
}
```
