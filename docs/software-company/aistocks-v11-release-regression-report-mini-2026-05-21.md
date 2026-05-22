# AiStocks v1.1 Release Regression Report Mini - 2026-05-21

## Summary
- Overall: PASS
- ROUTE: NoOne
- Scope: 修复后极简本地发布门禁复测；未访问外部 URL；未 commit；未执行破坏性操作。
- Regression Fix Context: `tests/test_api_v1.py::test_report_summary_distinguishes_market_data_quality` 已由固定过期 trade_date 改为当天日期，保持 1 primary + 2 fallback 断言语义。

## Commands and Results

### 1. Backend extended tests
Command:
```bash
C:/Users/amir/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/test_data_quality_gate_service.py tests/test_launch_check_service.py tests/test_production_evidence.py tests/test_deploy_preflight.py tests/test_task_queue.py tests/test_api_v1.py tests/test_api_v1_e2e.py tests/test_pick_api_service.py tests/test_report_api_service.py tests/test_live_broker_service.py tests/test_tenant_repository.py -q
```
Result: PASS

Raw conclusion:
- Collected: 160 tests
- Passed: 160
- Failed: 0
- Warnings: 87
- Duration: 118.85s

Warning summary:
```text
tests/test_api_v1.py: 74 warnings
tests/test_api_v1_e2e.py: 13 warnings
D:\AiStocks\backend\services\multiuser_auth_service.py:87: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
```

ROUTE: NoOne

### 2. Frontend build
Command:
```bash
npm --prefix D:/AiStocks/frontend run build
```
Result: PASS

Raw conclusion:
```text
vite v8.0.10 building client environment for production...
✓ 49 modules transformed.
✓ built in 191ms
```

ROUTE: NoOne

### 3. Deploy preflight
Command:
```bash
C:/Users/amir/AppData/Local/Programs/Python/Python312/python.exe scripts/deploy_preflight.py
```
Result: PASS

Raw conclusion:
```json
{
  "ok": true,
  "total": 61,
  "failed": 0,
  "summary": "preflight passed"
}
```

ROUTE: NoOne

## Residual Risks
- 后端测试仍有 87 条 `datetime.utcnow()` deprecation warnings，当前不阻塞发布，但建议后续技术债处理为 timezone-aware UTC。
- 本次为本地极简门禁复测，仅覆盖指定 3 条命令；未包含外部 URL、真实线上连通性、完整端到端浏览器生产冒烟或真实券商/行情外部依赖验证。
- 测试修复使用 `date.today().isoformat()`，会随系统日期变化；当前语义是确保 `period=week` 包含测试数据日期。

## Release Recommendation
The specified local mini release gate is green after the regression test fix. From this gate's scope, release can proceed; defer only if broader production smoke, external dependency verification, or warning cleanup is required by release policy.
