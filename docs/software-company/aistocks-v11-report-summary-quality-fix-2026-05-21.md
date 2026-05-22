# AiStocks v1.1 Report Summary Data Quality 修复记录

日期：2026-05-21

## 背景

发布前极简回归验证发现 1 个失败用例：

- `tests/test_api_v1.py::test_report_summary_distinguishes_market_data_quality`
- 失败断言：`data["summary"]["data_quality"]["primary"] == 1`
- 实际值：`0`

## 根因

`ReportApiService.summary()` 只统计当前报告周期窗口内的 picks。该测试固定写入 `trade_date="2026-05-11"`，但当前系统日期为 2026-05-21，`period=week` 的统计窗口已经不包含 2026-05-11，导致 summary 中没有统计到测试创建的 3 条记录。

这不是 data_quality 聚合源码将 primary 错算为 fallback，而是测试数据日期已经滑出当前周窗口。

## 修复

修改文件：

- `tests/test_api_v1.py`

修复方式：

- 将该测试中的固定 `trade_date="2026-05-11"` 改为 `date.today().isoformat()`。
- 保持测试目标不变：仍验证 1 条 primary 与 2 条 fallback 的区分统计。
- 未修改业务源码，未修改断言语义。

## 验证结果

### 单用例验证

命令：

```bash
C:/Users/amir/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/test_api_v1.py::test_report_summary_distinguishes_market_data_quality -q
```

结果：

- PASS，1 passed，1 warning

### 报告相关回归

命令：

```bash
C:/Users/amir/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/test_api_v1.py tests/test_report_api_service.py -q
```

结果：

- PASS，93 passed，74 warnings

## 结论

IS_PASS=YES

本次修复属于测试数据日期窗口修复，解决了时间滑窗导致的假失败。建议后续对所有依赖 `period=week/month` 的测试统一使用冻结日期或动态日期，避免未来再次出现日期漂移。
