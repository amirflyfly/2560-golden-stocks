# Live Broker Adapter Contract

本文档定义真实券商插件接入边界。当前仓库只提供受保护的 live broker adapter 契约、`generic_http` 最小网关样例和落库/校验边界，不接入任何真实券商 SDK。真实券商 SDK、席位登录、资金密码、风控前置机、交易柜台专线等能力必须在独立插件或外部 broker gateway 内实现。

## 目标与非目标

目标：
- 固定应用层到券商适配层的最小方法和返回结构。
- 明确下单、撤单、成交回报、对账、签名、幂等、限流和落库要求。
- 约束订单状态机，避免终态订单被回滚或重复推进。
- 给出最小验收清单，便于真实券商插件上线前逐项确认。

非目标：
- 不封装真实券商 SDK。
- 不保存券商登录口令、资金密码、证书私钥明文。
- 不绕过 `LIVE_TRADING_ENABLED`、`LIVE_TRADING_DRY_RUN` 和单次请求确认。
- 不修改迁移作为接入真实券商的前置动作。

## Adapter 注册边界

插件需要实现 `backend.application.live_broker_service.BrokerAdapter`，并通过 `LiveBrokerService.register_adapter(name, factory)` 或创建服务实例时传入 `adapter_registry` 注册。

```python
from backend.application.live_broker_service import BrokerAdapter, LiveBrokerConfig


class MyBrokerAdapter(BrokerAdapter):
    name = "my_broker"

    def submit_order(self, order_intent: dict, config: LiveBrokerConfig) -> dict:
        ...

    def cancel_order(self, cancel_intent: dict, config: LiveBrokerConfig) -> dict:
        ...

    def reconcile_orders(self, account_id: str, config: LiveBrokerConfig) -> dict:
        ...
```

注册名必须为小写稳定标识，并与环境变量 `LIVE_BROKER_ADAPTER` 一致。插件工厂必须无副作用：实例化 adapter 时不得自动登录、不得自动下单、不得启动长连接写库线程。真实连接可以在方法调用内惰性创建，或由外部 broker gateway 承担。

## 配置与安全门

应用层统一读取 `LiveBrokerConfig`：
- `adapter_name`: 来自 `LIVE_BROKER_ADAPTER`，默认 `disabled`。
- `enabled`: 来自 `LIVE_TRADING_ENABLED`，默认关闭。
- `dry_run`: 只有环境变量 `LIVE_TRADING_DRY_RUN=false` 且请求 `dry_run=false` 时才关闭。
- `account_id`: 请求 `account_id` 优先，否则读取 `LIVE_BROKER_ACCOUNT_ID`。
- `order_url`、`cancel_url`、`reconcile_url`: `generic_http` 使用的外部网关 URL。
- `token`: `generic_http` 的 bearer token，只允许在请求头发送，不允许进入响应。
- `signing_secret`: `generic_http` 的 HMAC secret，只允许用于签名，不允许进入响应。
- `timeout_seconds`: HTTP 超时，限制在 0.5 到 30 秒。
- `confirmation_phrase`: 默认 `CONFIRM_LIVE_TRADING`。
- `request_confirmation`: 请求体 `live_order_ack`。

真实下单和撤单必须同时满足：
- `LIVE_TRADING_ENABLED=true`。
- `LIVE_TRADING_DRY_RUN=false`。
- 请求体 `dry_run=false`。
- 请求体 `live_order_ack` 等于 `LIVE_TRADING_CONFIRMATION` 或默认确认短语。
- adapter 已注册且配置校验无错误。
- 订单或撤单 intent 校验通过。
- 未触发应用层每租户每动作限流。

## 方法契约

### `submit_order(order_intent, config) -> dict`

`order_intent` 由应用层归一化后传入：

```json
{
  "symbol": "000001",
  "side": "BUY",
  "quantity": 100,
  "order_type": "limit",
  "limit_price": 10.5,
  "idempotency_key": "live:strategy:20260506:000001:buy:1",
  "client_order_id": "live:strategy:20260506:000001:buy:1",
  "strategy_code": "2560",
  "reason": "signal"
}
```

要求：
- `side` 只接受 `BUY`、`SELL`。
- `order_type` 只接受 `market`、`limit`。
- `quantity` 必须为正整数。
- `limit` 单必须提供正数 `limit_price`。
- `idempotency_key` 必填，并应传递到 broker gateway 或券商插件内部幂等表。
- 插件不得修改本地数据库；应用层负责记录请求、状态、响应和幂等冲突。

推荐返回：

```json
{
  "status": "submitted",
  "order_status": "submitted",
  "adapter": "my_broker",
  "broker_order_id": "B123",
  "client_order_id": "live:strategy:20260506:000001:buy:1",
  "broker_response": {
    "broker_order_id": "B123",
    "client_order_id": "live:strategy:20260506:000001:buy:1",
    "order_status": "accepted"
  }
}
```

`status` 表示本次调用结果，`order_status` 表示券商订单状态。若只返回 `status`，应用层会尝试将其规范化为订单状态。

### `cancel_order(cancel_intent, config) -> dict`

`cancel_intent` 由应用层归一化后传入：

```json
{
  "broker_order_id": "B123",
  "client_order_id": "live:strategy:20260506:000001:buy:1",
  "symbol": "000001",
  "idempotency_key": "live:cancel:20260506:B123:1",
  "reason": "risk_exit"
}
```

要求：
- `broker_order_id` 和 `client_order_id` 至少提供一个。
- `idempotency_key` 必填。
- 撤单提交成功不等于已撤单，应返回 `cancel_submitted`、`cancel_pending`、`canceled`、`filled` 等可规范化状态。
- 如券商返回撤单时已成交，必须返回 `order_status=filled` 或在 `broker_response` 中携带等价字段。

推荐返回：

```json
{
  "status": "cancel_submitted",
  "cancel_status": "pending_cancel",
  "adapter": "my_broker",
  "broker_response": {
    "broker_order_id": "B123",
    "client_order_id": "live:strategy:20260506:000001:buy:1",
    "cancel_status": "pending_cancel"
  }
}
```

### `reconcile_orders(account_id, config) -> dict`

对账方法由应用层显式调用。插件应从券商侧读取当前委托、成交、撤单和终态订单，并与本地记录或 broker gateway 记录比对。若插件无法直接读取本地库，可以返回券商侧快照，由外部 gateway 完成差异生成。

推荐返回：

```json
{
  "status": "reconciled",
  "orders": [],
  "differences": [
    {
      "type": "quantity",
      "severity": "error",
      "broker_order_id": "B123",
      "client_order_id": "C123",
      "symbol": "000001",
      "field": "filled_quantity",
      "expected": 100,
      "actual": 80,
      "message": "broker fill quantity differs from local record"
    }
  ]
}
```

应用层会规范化为 `live-broker-reconciliation/v1`，并写入 `live_broker_reconciliations`。存在差异时整体状态为 `differences_found`。

## Generic HTTP 最小样例边界

`GenericHttpBrokerAdapter` 是 broker gateway 的 JSON over HTTP 样例，不是券商 SDK。它只做三件事：
- 将下单、撤单、对账 payload POST 到配置的 URL。
- 添加 bearer token 和可选 HMAC 签名头。
- 将 HTTP 响应体包装为 `broker_response`。

下单 payload：

```json
{
  "account_id": "acct-1",
  "order": {
    "symbol": "000001",
    "side": "BUY",
    "quantity": 100,
    "order_type": "market",
    "idempotency_key": "live:test:1",
    "client_order_id": "live:test:1"
  }
}
```

撤单 payload：

```json
{
  "account_id": "acct-1",
  "cancel": {
    "broker_order_id": "B123",
    "client_order_id": "live:test:1",
    "idempotency_key": "live:cancel:1"
  }
}
```

对账 payload：

```json
{
  "account_id": "acct-1"
}
```

## 签名要求

`LiveBrokerConfig.http_headers(payload, idempotency_key=...)` 在配置 `LIVE_BROKER_HTTP_SIGNING_SECRET` 时生成：
- `X-2560-Timestamp`: Unix 秒级时间戳。
- `X-2560-Idempotency-Key`: 当前请求幂等键。
- `X-2560-Signature`: HMAC-SHA256 十六进制签名。

签名原文为：

```text
{timestamp}
{idempotency_key}
{json_body}
```

其中 `json_body` 使用 `sort_keys=True` 和紧凑分隔符序列化。broker gateway 必须：
- 校验时间戳窗口，建议不超过 300 秒。
- 校验幂等键与请求体一致。
- 使用常量时间比较签名。
- 拒绝重放、空签名和过期请求。
- 不在日志中记录 token、secret、资金账号敏感字段或完整券商原始凭证。

## 成交回报契约

成交回报不通过 adapter 方法写库，而是通过应用层 `ingest_fills` 入口接收。插件或外部 broker gateway 应将券商成交回报映射为：

```json
{
  "account_id": "acct-1",
  "fill_key": "broker-fill-001",
  "broker_order_id": "B123",
  "client_order_id": "C123",
  "symbol": "000001",
  "side": "BUY",
  "quantity": 100,
  "price": 10.5,
  "amount": 1050.0,
  "fee": 1.2,
  "currency": "CNY",
  "filled_at": "2026-05-06T09:31:02",
  "source": "callback"
}
```

必填或强约束字段：
- `account_id` 必填。
- `broker_order_id` 与 `client_order_id` 至少一个必填。
- `symbol` 必填。
- `side` 必须为 `BUY` 或 `SELL`。
- `quantity` 必须为正整数。
- `price` 必须为正数。
- `fill_key` 强烈建议由券商成交编号、执行编号或 `account_id + broker_order_id + trade_id` 生成。缺失时仓储会用 payload hash 生成，但真实接入不应依赖自动生成。

落库要求：
- `live_broker_fills` 以 `(tenant_id, fill_key)` 唯一约束去重。
- 重复成交回报必须幂等更新，不得重复计入成交。
- 插件不得直接插入该表，应调用应用层入口或等价服务方法。

## 幂等与落库要求

应用层对下单和撤单使用 `live_broker_requests`：
- 唯一键：`(tenant_id, idempotency_key)`。
- 请求哈希：对归一化 intent 做稳定 JSON hash。
- 同一幂等键、同一请求体：已成功提交的请求返回 `idempotent_replay`，不会再次调用 adapter。
- 同一幂等键、不同请求体：返回 `idempotency_key_conflict`，不会调用 adapter。
- 阻断、dry run、校验失败、券商拒绝、broker error 可再次尝试同一 intent。

真实插件或 broker gateway 也必须实现自己的幂等保护，因为应用层只能保护进入本服务的请求，不能覆盖网关重试、SDK 超时后未知提交结果、长连接重放等外部风险。

## 限流要求

应用层限流：
- 环境变量：`LIVE_BROKER_RATE_LIMIT_PER_MIN`。
- 默认：每租户每 action 每分钟 30 次。
- `0` 或负数表示关闭应用层限流。
- 命中限流时记录 `blocked/rate_limited` 请求。

插件或 broker gateway 要求：
- 遵守券商接口限频、撤单频率和交易所风控规则。
- 对超时、HTTP 429、柜台繁忙、会话失效使用有上限的退避重试。
- 重试必须绑定同一 `idempotency_key` 或券商原生 client order id。
- 达到插件侧限流时返回 `status=blocked`、`reason=rate_limited` 或更具体的可诊断原因。

## 状态机约束

应用层标准订单状态：
- `pending`
- `submitted`
- `partially_filled`
- `filled`
- `cancel_pending`
- `canceled`
- `rejected`
- `expired`
- `failed`
- `unknown`

终态：
- `filled`
- `canceled`
- `rejected`
- `expired`
- `failed`

允许推进：
- `pending` -> `submitted`、`partially_filled`、`filled`、`cancel_pending`、`canceled`、`rejected`、`expired`、`failed`
- `submitted` -> `partially_filled`、`filled`、`cancel_pending`、`canceled`、`rejected`、`expired`、`failed`
- `partially_filled` -> `filled`、`cancel_pending`、`canceled`、`failed`
- `cancel_pending` -> `canceled`、`partially_filled`、`filled`、`failed`
- `unknown` -> 任意标准状态

禁止：
- 任意终态回退到非终态。
- `filled` 后再进入 `cancel_pending` 或 `canceled`。
- `canceled` 后再进入 `submitted`。
- 未成交数量、成交数量、均价与状态互相矛盾时静默通过。

插件返回的券商原始状态可以是 `accepted`、`open`、`pending_cancel`、`cancelled` 等别名，应用层会尽量规范化。但真实接入验收时必须提供完整状态映射表，并覆盖全部券商终态和异常态。

## 错误与超时

adapter 方法应返回结构化错误，不应吞掉异常信息：

```json
{
  "status": "broker_rejected",
  "reason": "insufficient_cash",
  "adapter": "my_broker",
  "broker_response": {
    "code": "E_CASH",
    "message": "insufficient cash"
  }
}
```

约束：
- SDK 异常、网络错误、会话失效应转换为可诊断 `status` 和 `reason`，或让应用层捕获为 `broker_error`。
- 不确定是否成功提交的超时必须返回可识别原因，并要求后续对账修复。
- 不允许在返回体中包含 token、secret、cookie、私钥、资金密码或完整登录报文。

## 对账与修复

对账至少覆盖：
- 本地有、券商无。
- 券商有、本地无。
- 状态不一致。
- 成交数量不一致。
- 成交价格或均价不一致。
- 撤单结果不一致。
- 手工订单或外部系统订单识别。

对账输出只记录差异，不自动修复。自动补单、撤单、回写成交、修正持仓等动作必须作为单独流程，有人工确认、审计记录和回滚方案。

## 接入验收清单

上线真实券商插件前必须完成：

- Adapter 注册名固定，`LIVE_BROKER_ADAPTER` 能正确选择插件。
- 默认 `disabled` 和 dry run 下不会调用真实 SDK。
- 未提供 `live_order_ack` 时不能真实下单或撤单。
- `submit_order` 覆盖市价单、限价单、买入、卖出、数量和价格校验。
- `cancel_order` 覆盖按券商订单号、按 client order id、重复撤单、已成交撤单。
- `reconcile_orders` 能输出结构化 `differences`，并落库到 reconciliation 表。
- 成交回报字段映射通过 `validate_fill_mapping`。
- 重复 `fill_key` 不会重复计入成交。
- 同一 `idempotency_key` 同一请求不会重复调用 SDK。
- 同一 `idempotency_key` 不同请求会被拒绝。
- 插件侧和网关侧均有幂等保护。
- HMAC 签名校验包含 timestamp、idempotency key 和排序后的 JSON body。
- token、secret、资金密码、cookie、证书私钥不会进入响应、审计、日志和数据库明文字段。
- 限流参数明确，触发限流时有结构化原因。
- 券商状态映射表完整，终态不回退。
- SDK 超时和未知提交结果必须能通过对账闭环。
- 生产演练先使用 dry run，再使用小额白名单账户和白名单标的。
- 有人工停机开关：关闭 `LIVE_TRADING_ENABLED` 或开启 `LIVE_TRADING_DRY_RUN` 后立即阻断真实交易。

## 建议测试命令

```powershell
python -m pytest tests/test_live_broker_service.py
```

若新增真实插件测试，应优先使用 fake SDK 或 broker gateway mock，不连接真实券商环境。
