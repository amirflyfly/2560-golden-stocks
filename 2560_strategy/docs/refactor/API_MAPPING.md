# 旧路由到新 API 映射

## 股票行情

| 当前能力 | 新 API |
|---|---|
| 股票 K 线数据 | GET /api/v1/stocks/{symbol}/daily-bars |
| 实时行情 | GET /api/v1/stocks/realtime |
| 股票列表 | GET /api/v1/stocks |

## 策略

| 当前能力 | 新 API |
|---|---|
| 策略列表 | GET /api/v1/strategies |
| 策略详情 | GET /api/v1/strategies/{id} |
| 创建策略 | POST /api/v1/strategies |
| 更新策略 | PUT /api/v1/strategies/{id} |
| 删除策略 | DELETE /api/v1/strategies/{id} |

## 扫描

| 当前能力 | 新 API |
|---|---|
| 运行所有策略扫描 | POST /api/v1/scans |
| 查询扫描任务 | GET /api/v1/scans/{id} |
| 查询扫描结果 | GET /api/v1/scans/{id}/results |
| 取消扫描 | POST /api/v1/scans/{id}/cancel |

## 选股池

| 当前能力 | 新 API |
|---|---|
| 查询选股 | GET /api/v1/picks |
| 新增选股 | POST /api/v1/picks |
| 更新选股 | PUT /api/v1/picks/{id} |
| 删除选股 | DELETE /api/v1/picks/{id} |

## 租户与用户

| 当前能力 | 新 API |
|---|---|
| 登录 | POST /api/v1/auth/login |
| 当前用户 | GET /api/v1/auth/me |
| 租户列表 | GET /api/v1/tenants |
| 切换租户 | POST /api/v1/tenants/switch |
