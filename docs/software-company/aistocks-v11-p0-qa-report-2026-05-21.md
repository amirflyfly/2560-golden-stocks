# AiStocks v1.1 P0 QA Report - 2026-05-21

## 范围
- 本次仅执行本地仓库验证，不访问外部 URL 或远程服务。
- 验证命令限定为指定 pytest、前端 build、deploy preflight。

## 命令结果
1. `C:/Users/amir/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/test_data_quality_gate_service.py tests/test_launch_check_service.py tests/test_production_evidence.py tests/test_deploy_preflight.py tests/test_task_queue.py -q`
   - PASS：41 passed in 1.67s
2. `npm --prefix D:/AiStocks/frontend run build`
   - PASS：vite build 成功，49 modules transformed
3. `C:/Users/amir/AppData/Local/Programs/Python/Python312/python.exe scripts/deploy_preflight.py`
   - PASS：ok=true，total=61，failed=0，summary=preflight passed

## 结论
- PASS
- ROUTE=NoOne

## 遗留风险
- 未运行完整 E2E。
- 未采集 production evidence。
- 当前 Git 工作区仍有大量未提交变更。
