"""Strategy API routes."""

from __future__ import annotations

from flask import Blueprint, request

from backend.application.audit_log_service import audit_log_service
from backend.application.backtest_api_service import backtest_api_service
from backend.application.pagination import normalize_pagination
from backend.application.strategy_api_service import StrategyApiService
from backend.core.errors import NotFoundError
from backend.core.responses import success
from backend.core.tenant_context import get_authenticated_tenant_context, require_role

bp = Blueprint("api_v1_strategies", __name__)
service = StrategyApiService()


@bp.get("/strategies")
def list_strategies():
    context = get_authenticated_tenant_context()
    pagination = normalize_pagination(request.args.get("page"), request.args.get("page_size"))
    return success(service.list_strategies(context.tenant_id, pagination))


@bp.get("/strategies/<int:strategy_id>")
def get_strategy(strategy_id: int):
    context = get_authenticated_tenant_context()
    item = service.get_strategy(context.tenant_id, strategy_id)
    if item is None:
        raise NotFoundError("strategy not found")
    return success(item)


@bp.post("/strategies/<strategy_code>/backtest")
def run_strategy_backtest(strategy_code: str):
    context = get_authenticated_tenant_context()
    require_role(context, "admin", "editor")
    payload = request.get_json(silent=True) or {}
    item = backtest_api_service.run(context.tenant_id, strategy_code, payload)
    audit_log_service.record(
        context=context,
        action="strategy.backtest.create",
        resource_type="strategy",
        resource_id=strategy_code,
        detail={"strategy_code": strategy_code, "params": payload, "summary": item.get("summary", {})},
    )
    return success(item, status_code=202)


@bp.get("/strategies/<strategy_code>/backtests")
def list_strategy_backtests(strategy_code: str):
    context = get_authenticated_tenant_context()
    pagination = normalize_pagination(request.args.get("page"), request.args.get("page_size"))
    return success(backtest_api_service.history(context.tenant_id, strategy_code, page=pagination.page, page_size=pagination.page_size))


@bp.get("/strategies/<strategy_code>/backtests/<int:backtest_id>")
def get_strategy_backtest_detail(strategy_code: str, backtest_id: int):
    context = get_authenticated_tenant_context()
    return success(backtest_api_service.detail(context.tenant_id, strategy_code, backtest_id))
